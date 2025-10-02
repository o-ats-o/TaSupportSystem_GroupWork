import pyaudio
import wave
import sys
import json
import shutil
import os
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, lfilter
from local_settings import *
import requests
import logging
import time
import threading
import queue
import subprocess
import tempfile
from pathlib import Path
import socket
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from os import fspath


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
RECORD_SECONDS = 299.8  # 録音時間

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

# Worker API ベースURL（local_settings または環境変数から取得）
try:
    WORKER_API_BASE_URL = WORKER_API_BASE_URL  # type: ignore[name-defined]
except NameError:
    WORKER_API_BASE_URL = os.getenv("WORKER_API_BASE_URL", "http://localhost:8787")

# 末尾スラッシュは除去して正規化
if WORKER_API_BASE_URL.endswith('/'):
    WORKER_API_BASE_URL = WORKER_API_BASE_URL[:-1]

def _convert_to_flac(input_path: str) -> tuple[str, str]:
    """ffmpegでFLACに変換し、(flac_path, content_type) を返す。
    失敗時は (input_path, 推定content_type) を返す。
    """
    src = Path(input_path)
    out_path = src.parent / f"{src.stem}.flac"
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", str(src), "-c:a", "flac", "-compression_level", "12", str(out_path)
    ]
    try:
        subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)
        logging.info(f"FLAC変換完了: {out_path}")
        return str(out_path), "audio/flac"
    except FileNotFoundError:
        logging.error("'ffmpeg' が見つかりません。FLAC出力には ffmpeg が必要です。WAVのまま続行します。")
        # WAVのままアップロード
        return str(src), "audio/wav"
    except subprocess.CalledProcessError as e:
        logging.error("ffmpeg によるFLAC変換に失敗しました: %s", e.stderr)
        return str(src), "audio/wav"


# session_id 生成（GROUP_IDを含める・安全な文字に正規化）
def generate_session_id(group_id: str) -> str:
    safe_group = re.sub(r"[^A-Za-z0-9_-]", "-", str(group_id))
    host = socket.gethostname()
    safe_host = re.sub(r"[^A-Za-z0-9_-]", "-", host)
    epoch = int(time.time())
    return f"{safe_group}-{safe_host}-{epoch}"

# アップロード用の署名URLを取得
def get_signed_upload_url(content_type: str):
    url = f"{WORKER_API_BASE_URL}/api/generate-upload-url"
    try:
        resp = requests.post(url, json={"contentType": content_type}, timeout=60)
        resp.raise_for_status()
        body = resp.json()
        upload_url = body.get("uploadUrl")
        object_key = body.get("objectKey")
        if not upload_url or not object_key:
            raise ValueError("署名URLレスポンスに uploadUrl/objectKey がありません")
        logging.info("署名付きURLを取得しました")
        return upload_url, object_key
    except Exception as e:
        logging.error(f"署名付きURL取得に失敗: {e}")
        raise

# 署名URLに対して音声をPUTでアップロード
def upload_to_r2(upload_url: str, file_path: str, content_type: str):
    try:
        with open(file_path, "rb") as f:
            headers = {"Content-Type": content_type}
            resp = requests.put(upload_url, data=f, headers=headers, timeout=300)
        if not (200 <= resp.status_code < 300):
            raise RuntimeError(f"R2アップロード失敗: status={resp.status_code} body={resp.text[:200]}")
        logging.info("R2へアップロード完了")
    except Exception as e:
        logging.error(f"R2アップロード中にエラー: {e}")
        raise

# 文字起こしの処理依頼
def request_transcription(object_key: str, session_id: str, group_id: str):
    url = f"{WORKER_API_BASE_URL}/api/process-request"
    payload = {"objectKey": object_key, "sessionId": session_id, "groupId": group_id}
    try:
        resp = requests.post(url, json=payload, timeout=60)
        if resp.status_code not in (200, 201, 202):
            raise RuntimeError(f"処理依頼失敗: status={resp.status_code} body={resp.text[:200]}")
        body = resp.json() if resp.content else {}
        job_id = body.get("jobId")
        if job_id:
            logging.info(f"処理依頼を受理: jobId={job_id}")
        else:
            logging.info("処理依頼を受理（jobId未返却）")
    except Exception as e:
        logging.error(f"処理依頼中にエラー: {e}")
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
        ts = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d-%H%M%S")
        filename = f"output_{ts}.wav"
        waveFile = wave.open(filename, 'wb')
        waveFile.setnchannels(CHANNELS)
        waveFile.setsampwidth(audio.get_sample_size(FORMAT))
        waveFile.setframerate(RATE)
        waveFile.writeframes(b''.join(frames))
        waveFile.close()

        # キューにファイル名を追加
        q.put(filename)

        # 次の録音開始までの待機時間を調整（録音時間299.8秒 + 待機0.2秒 = 5分間隔）
        time.sleep(0.2)

# データ処理関数
def process_data(q):
    while True:
        filename = q.get()  # キューからファイル名を取得

        if filename is None:
            break

        start_time = time.time()
        logging.info(f"{filename} のデータ処理を開始")

        try:
            # バンドパスフィルタ適用後の音声ファイルパス
            bandpassed_file_path = filename

            # ノイズ除去（バンドパスフィルタ）
            fs, data = wavfile.read(filename)
            lowcut = 100.0
            highcut = 4000.0
            y = butter_bandpass_filter(data, lowcut, highcut, fs, order=6)
            
            # メモリ上のデータを一時ファイルに書き出し、元のファイル(filename)を上書きしない
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_f:
                bandpassed_file_path = temp_f.name
                wavfile.write(bandpassed_file_path, fs, y.astype(np.int16))

            # バンドパス後の音源をFLACへ変換
            FILE, CONTENT_TYPE = _convert_to_flac(bandpassed_file_path)

            # R2 にアップロードし、処理依頼を送る
            upload_url, object_key = get_signed_upload_url(CONTENT_TYPE)
            upload_to_r2(upload_url, FILE, CONTENT_TYPE)

            # セッションID生成（GROUP_ID + ホスト名 + タイムスタンプ）
            session_id = generate_session_id(GROUP_ID)
            request_transcription(object_key, session_id, GROUP_ID)

            # ファイルを移動（デノイズ後のファイルを優先して移動し、元ファイルも退避）
            try:
                if os.path.exists(FILE):
                    move_file(FILE)
                if FILE!= filename and os.path.exists(filename):
                    move_file(filename)
            except Exception as e:
                logging.error(f"ファイル移動エラー: {e}")

        except Exception as e:
            exception_type, exception_object, exception_traceback = sys.exc_info()
            line_number = exception_traceback.tb_lineno if exception_traceback else -1
            logging.error(f'line {line_number}: {exception_type} - {e}')
        finally:
            # 一時ファイルをクリーンアップ
            if 'bandpassed_file_path' in locals() and bandpassed_file_path!= filename and os.path.exists(bandpassed_file_path):
                try:
                    os.remove(bandpassed_file_path)
                except OSError as e:
                    logging.error(f"一時ファイルの削除に失敗: {e}")

            elapsed_time = time.time() - start_time
            logging.info(f"{filename} のデータ処理時間: {elapsed_time:.2f} 秒")
            q.task_done()
            
# 音声ファイルを指定のフォルダに移動
def move_file(FILE):
    source = FILE
    destination = FOLDER_PATH

    # 移動先ディレクトリが存在しなければ作成
    try:
        os.makedirs(destination, exist_ok=True)
    except Exception as e:
        logging.error(f"移動先ディレクトリの作成に失敗: {e}")
        raise

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
        # スレッドの終了を待つ
        process_thread.join()
        # record_threadはdaemonなので、メインスレッドが終了すれば自動的に終了する

if __name__ == "__main__":
    main()