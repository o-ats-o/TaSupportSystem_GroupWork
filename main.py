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
import requests
import logging
import time

# ログの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("processing.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

# 録音のパラメータ設定
FORMAT = pyaudio.paInt16 # 音声のフォーマット
CHANNELS = 1             # モノラル
RATE = 44100             # サンプルレート
CHUNK = 1024             # データの読み込みサイズ
RECORD_SECONDS = 299     # 録音時間

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

# 録音関数
def record_audio(q, record_seconds):
    while True:
        audio = pyaudio.PyAudio()

        # 録音設定
        stream = audio.open(format=FORMAT, channels=CHANNELS,
                            rate=RATE, input=True,
                            frames_per_buffer=CHUNK)
        logging.info("録音開始")

        frames = []

        # 録音
        for i in range(0, int(RATE / CHUNK * record_seconds)):
            data = stream.read(CHUNK, exception_on_overflow=False)
            frames.append(data)

        logging.info("録音終了")

        # 録音終了処理
        stream.stop_stream()
        stream.close()
        audio.terminate()

        # ファイルに保存
        filename = f"output_{int(time.time())}.wav"
        waveFile = wave.open(filename, 'wb')
        waveFile.setnchannels(CHANNELS)
        waveFile.setsampwidth(audio.get_sample_size(FORMAT))
        waveFile.setframerate(RATE)
        waveFile.writeframes(b''.join(frames))
        waveFile.close()

        # キューにファイル名を追加
        q.put(filename)

        # 次の録音開始までの待機時間を調整（録音時間299秒 + 待機1秒 = 5分間隔）
        time.sleep(1)

# データ処理関数
def process_data(q):
    while True:
        filename = q.get()  # キューからファイル名を取得

        if filename is None:
            break

        start_time = time.time()
        logging.info(f"{filename} のデータ処理を開始")

        try:
            # ノイズ除去
            fs, data = wavfile.read(filename)
            lowcut = 100.0
            highcut = 4000.0
            y = butter_bandpass_filter(data, lowcut, highcut, fs, order=6)
            # ノイズ除去後の音声ファイルを保存
            wavfile.write(filename, fs, y.astype(np.int16))

            FILE = filename
            MIMETYPE = "audio/wav"

            # 音声認識とデータ送信
            asyncio.run(process_audio(FILE, MIMETYPE))

            # ファイルを移動
            move_file(filename)

        except Exception as e:
            exception_type, exception_object, exception_traceback = sys.exc_info()
            line_number = exception_traceback.tb_lineno
            logging.error(f'line {line_number}: {exception_type} - {e}')
        finally:
            elapsed_time = time.time() - start_time
            logging.info(f"{filename} のデータ処理時間: {elapsed_time:.2f} 秒")
            q.task_done()
            
# 音声認識とデータ送信を行う関数
async def process_audio(FILE, MIMETYPE):
    deepgram = Deepgram(DEEPGRAM_API_KEY)
    source = {'url': FILE} if FILE.startswith('http') else {'buffer': open(FILE, 'rb'), 'mimetype': MIMETYPE}
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

    transcript = response["results"]["channels"][0]["alternatives"][0]["transcript"]
    transcript_diarize = response["results"]["channels"][0]["alternatives"][0]["paragraphs"]["transcript"]
    utterance_count = transcript_diarize.count("Speaker")
    sentiment_value = analyze_sentiment(transcript)

    logging.info(f"グループID: {GROUP_ID}")
    logging.info(f"テキスト: {transcript_diarize}")
    logging.info(f"発話回数: {utterance_count}")
    logging.info(f"感情スコア: {sentiment_value}")

    data = {
        'group_id': GROUP_ID,
        'transcript': transcript,
        'transcript_diarize': transcript_diarize,
        'utterance_count': utterance_count,
        'sentiment_value': sentiment_value
    }
    send_post_request(data)

# 音声ファイルを指定のフォルダに移動
def move_file(FILE):
    source = FILE
    destination = FOLDER_PATH

    # 移動先のディレクトリで同じ名前のファイルが存在する場合、ファイル名を変更
    if os.path.exists(os.path.join(destination, os.path.basename(FILE))):
        base, ext = os.path.splitext(os.path.basename(FILE))
        i = 1
        while os.path.exists(os.path.join(destination, f"{base}_{i}{ext}")):
            i += 1
        destination_path = os.path.join(destination, f"{base}_{i}{ext}")
    else:
        destination_path = os.path.join(destination, os.path.basename(FILE))

    shutil.move(source, destination_path)
    logging.info(f"ファイルを移動: {destination_path}")

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

# データをPOSTリクエストで送信
def send_post_request(data):
    try:
        response = requests.post(DJANGO_API_URL, json=data, timeout=240)
        logging.info(f"データ送信ステータスコード: {response.status_code}")
        logging.info(f"サーバからの応答: {response.json()}")
        if response.status_code == 400:
            data['transcript'] = None
            data['transcript_diarize'] = None
            response = requests.post(DJANGO_API_URL, json=data, timeout=240)
    except Exception as e:
        logging.error(f"データ送信エラー: {e}")

async def main():
  move_file()

try:
  asyncio.run(main())
except Exception as e:
  exception_type, exception_object, exception_traceback = sys.exc_info()
  line_number = exception_traceback.tb_lineno
  print(f'line {line_number}: {exception_type} - {e}')