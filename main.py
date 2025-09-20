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
import threading
import queue
import subprocess
import tempfile
from pathlib import Path

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

# resemble-enhance を使った追加のデノイズ（出力は必ずFLAC）
def denoise_with_resemble(input_file, device="mps"):
    try:
        src_path = Path(input_file)
        if not src_path.is_file():
            logging.error(f"入力ファイルが見つかりません: {input_file}")
            raise FileNotFoundError(f"入力ファイルが見つかりません: {input_file}")

        with tempfile.TemporaryDirectory() as temp_in_dir, tempfile.TemporaryDirectory() as temp_out_dir:
            temp_in_path = Path(temp_in_dir)
            temp_out_path = Path(temp_out_dir)

            # 入力を一時ディレクトリへコピー
            shutil.copy(src_path, temp_in_path)

            command = [
                "resemble-enhance",
                str(temp_in_path),
                str(temp_out_path),
                "--denoise_only",
                "--device",
                device,
            ]

            logging.info("resemble-enhance によるデノイズを開始します")
            try:
                subprocess.run(command, check=True, capture_output=True, text=True)
            except FileNotFoundError:
                logging.error("'resemble-enhance' コマンドが見つかりません。'pip install resemble-enhance' でインストールし、PATHに含めてください。")
                raise
            except subprocess.CalledProcessError as e:
                logging.error("resemble-enhance の実行に失敗しました: %s", e.stderr)
                raise

            # 出力ファイル探索
            processed_files = list(temp_out_path.glob(f"*{src_path.name}"))
            if not processed_files:
                logging.error("resemble-enhance の出力が見つかりませんでした。")
                # デバッグ用に出力ディレクトリの内容を記録
                try:
                    contents = [str(p) for p in temp_out_path.iterdir()]
                    logging.error(f"出力ディレクトリ内容: {contents}")
                except Exception:
                    pass
                raise RuntimeError("resemble-enhance の出力が見つかりませんでした")

            intermediate_file = processed_files[0]

            # 出力は常にFLACに変換
            out_path = src_path.parent / f"{src_path.stem}_resemble_enhance_denoised.flac"
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", str(intermediate_file), "-c:a", "flac", "-compression_level", "12", str(out_path)
            ]
            try:
                subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)
                logging.info(f"デノイズ完了(FLAC): {out_path}")
                return str(out_path)
            except FileNotFoundError:
                logging.error("'ffmpeg' が見つかりません。FLAC出力には ffmpeg が必要です。")
                raise
            except subprocess.CalledProcessError as e:
                logging.error("ffmpeg によるFLAC変換に失敗しました: %s", e.stderr)
                raise
    except Exception as e:
        logging.error(f"denoise_with_resemble 内で予期しないエラー: {e}")
        raise

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
            # ノイズ除去（バンドパスフィルタ）
            fs, data = wavfile.read(filename)
            lowcut = 100.0
            highcut = 4000.0
            y = butter_bandpass_filter(data, lowcut, highcut, fs, order=6)
            # ノイズ除去後の音声ファイルを保存
            wavfile.write(filename, fs, y.astype(np.int16))

            # resemble-enhance による追加のデノイズ処理（FLAC固定）
            denoised_file = denoise_with_resemble(filename, device="mps")

            FILE = denoised_file
            MIMETYPE = "audio/flac"

            # 音声認識とデータ送信
            asyncio.run(process_audio(FILE, MIMETYPE))

            # ファイルを移動（デノイズ後のファイルを優先して移動し、元ファイルも退避）
            try:
                if os.path.exists(FILE):
                    move_file(FILE)
                if FILE != filename and os.path.exists(filename):
                    move_file(filename)
            except Exception as e:
                logging.error(f"ファイル移動エラー: {e}")

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

def main():
    q = queue.Queue()

    # 録音スレッドを作成
    record_thread = threading.Thread(target=record_audio, args=(q, RECORD_SECONDS))
    record_thread.daemon = True
    record_thread.start()

    # データ処理スレッドを作成
    process_thread = threading.Thread(target=process_data, args=(q,))
    process_thread.daemon = True
    process_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("プログラムを終了します")
        q.put(None)
        record_thread.join()
        process_thread.join()

if __name__ == "__main__":
    main()
