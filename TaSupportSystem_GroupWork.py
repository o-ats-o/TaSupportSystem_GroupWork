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

# 録音のパラメータ設定
FORMAT = pyaudio.paInt16 # 音声のフォーマット
CHANNELS = 1             # モノラル
RATE = 44100             # サンプルレート
CHUNK = 1024             # データの読み込みサイズ
RECORD_SECONDS = 30      # 録音時間
WAVE_OUTPUT_FILENAME = "output.wav" # 出力ファイル名

audio = pyaudio.PyAudio()

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

# 録音開始
stream = audio.open(format=FORMAT, channels=CHANNELS,
                    rate=RATE, input=True,
                    frames_per_buffer=CHUNK)
print("録音を開始します。")

frames = []

for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
    data = stream.read(CHUNK)
    frames.append(data)

print("録音が終了しました。")

# 録音終了
stream.stop_stream()
stream.close()
audio.terminate()

# ファイルに保存
wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
wf.setnchannels(CHANNELS)
wf.setsampwidth(audio.get_sample_size(FORMAT))
wf.setframerate(RATE)
wf.writeframes(b''.join(frames))
wf.close()

# ノイズ除去
fs, data = wavfile.read(WAVE_OUTPUT_FILENAME)
lowcut = 600
highcut = 3000.0
y = butter_bandpass_filter(data, lowcut, highcut, fs, order=6)
# ノイズ除去後の音声ファイルを保存
wavfile.write(WAVE_OUTPUT_FILENAME, fs, y.astype(np.int16))

# ノイズ除去後の音声ファイルをFILEに代入
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

async def main():

  # Initialize the Deepgram SDK
  deepgram = Deepgram(DEEPGRAM_API_KEY)

  # Check whether requested file is local or remote, and prepare source
  if FILE.startswith('http'):
    # file is remote
    # Set the source
    source = {
      'url': FILE
    }
  else:
    # file is local
    # Open the audio file
    audio = open(FILE, 'rb')

    # Set the source
    source = {
      'buffer': audio,
      'mimetype': MIMETYPE
    }

  # Send the audio to Deepgram and get the response
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

  # Write the response to the console
  # Write only the transcript to the console
  #print(json.dumps(response, indent=4))

  transcript = response["results"]["channels"][0]["alternatives"][0]["paragraphs"]["transcript"]
  speakerall = transcript.count("Speaker")

  print(transcript)
  print(f"発話量：" + str(speakerall) + "回")
  
  move_file()


try:
  # If running in a Jupyter notebook, Jupyter is already running an event loop, so run main with this line instead:
  #await main()
  asyncio.run(main())
except Exception as e:
  exception_type, exception_object, exception_traceback = sys.exc_info()
  line_number = exception_traceback.tb_lineno
  print(f'line {line_number}: {exception_type} - {e}')