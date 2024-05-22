import pyaudio
import wave
import sys
from deepgram import Deepgram
import asyncio, json
import shutil
import os
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, lfilter
from local_settings import *
from google.cloud import language_v1

GROUP_ID = "group_0"

# 録音のパラメータ設定
FORMAT = pyaudio.paInt16 # 音声のフォーマット
CHANNELS = 1             # モノラル
RATE = 44100             # サンプルレート
CHUNK = 1024             # データの読み込みサイズ
RECORD_SECONDS = 30      # 録音時間
WAVE_OUTPUT_FILENAME = "output.wav" # 出力ファイル名

# バターワースフィルタ
def butter_bandpass(lowcut, highcut, fs, order=5):
    nyq = 0.5 * fs
    low = lowcut / nyq
    high = highcut / nyq
    b, a = butter(order, [low, high], btype='band')
    return b, a

def butter_bandpass_filter(data, lowcut, highcut, fs, order=5):
    b, a = butter_bandpass(lowcut, highcut, fs, order=order)
    y = lfilter(b, a, data)
    return y

def record_audio(filename, record_seconds):
    audio = pyaudio.PyAudio()

    # 録音設定
    stream = audio.open(format=FORMAT, channels=CHANNELS,
                        rate=RATE, input=True,
                        frames_per_buffer=CHUNK)
    print("録音開始")

    frames = []

    # 録音
    for i in range(0, int(RATE / CHUNK * record_seconds)):
        data = stream.read(CHUNK)
        frames.append(data)

    print("録音終了")

    # 録音終了処理
    stream.stop_stream()
    stream.close()
    audio.terminate()

    # ファイルに保存
    waveFile = wave.open(filename, 'wb')
    waveFile.setnchannels(CHANNELS)
    waveFile.setsampwidth(audio.get_sample_size(FORMAT))
    waveFile.setframerate(RATE)
    waveFile.writeframes(b''.join(frames))
    waveFile.close()

# 録音を開始
record_audio(WAVE_OUTPUT_FILENAME, RECORD_SECONDS)

# ノイズ除去
fs, data = wavfile.read(WAVE_OUTPUT_FILENAME)
lowcut = 100.0
highcut = 4000.0
y = butter_bandpass_filter(data, lowcut, highcut, fs, order=6)
# ノイズ除去後の音声ファイルを保存
wavfile.write(WAVE_OUTPUT_FILENAME, fs, y.astype(np.int16))

FILE = WAVE_OUTPUT_FILENAME
MIMETYPE = "audio/wav"

# 音声ファイルをダウンロードフォルダに移動
def move_file():
    source = FILE
    destination = FOLDER_PATH
    
    # 移動先のディレクトリで同じ名前のファイルが存在する場合、ファイル名を変更
    if os.path.exists(os.path.join(destination, os.path.basename(FILE))):
        base, ext = os.path.splitext(os.path.basename(FILE))
        i = 1
        while os.path.exists(os.path.join(destination, f"{base}_{i}{ext}")):
            i += 1
        destination = os.path.join(destination, f"{base}_{i}{ext}")
   
    shutil.move(source, destination)

# テキストの感情分析
def analyze_sentiment(text_content):
  
    client = language_v1.LanguageServiceClient()
    
    type_ = language_v1.Document.Type.PLAIN_TEXT
    
    language = "ja"
    document = {"content": text_content, "type_": type_, "language": language}

    # Available values: NONE, UTF8, UTF16, UTF32
    encoding_type = language_v1.EncodingType.UTF8

    response = client.analyze_sentiment(request = {'document': document, 'encoding_type': encoding_type})

    return response.document_sentiment.score

async def main():

  deepgram = Deepgram(DEEPGRAM_API_KEY)

  if FILE.startswith('http'):
    # リモートファイル
    source = {
      'url': FILE
    }
  else:
    # ローカルファイル
    audio = open(FILE, 'rb')

    source = {
      'buffer': audio,
      'mimetype': MIMETYPE
    }

  response = await asyncio.create_task(
    deepgram.transcription.prerecorded(
      source,
      {
        "model": "nova-2", 
        "language": "ja", 
        "smart_format": True, 
        "punctuate": True, 
        "utterances": False, 
        "diarize": True, 
      }
    )
  )
  
  move_file()

  transcript = response["results"]["channels"][0]["alternatives"][0]["transcript"]
  transcript_diarize = response["results"]["channels"][0]["alternatives"][0]["paragraphs"]["transcript"]
  utterance_count = transcript_diarize.count("Speaker")
  sentiment_value = analyze_sentiment(transcript)
  
  print(GROUP_ID)
  print(transcript_diarize)
  print(f"発話回数: {utterance_count}")
  print(f"感情スコア: {sentiment_value}")


try:
  asyncio.run(main())
except Exception as e:
  exception_type, exception_object, exception_traceback = sys.exc_info()
  line_number = exception_traceback.tb_lineno
  print(f'line {line_number}: {exception_type} - {e}')