# 起動メモ
- brew services start mysql@8.4
- python manage.py makemigrations
- python manage.py migrate
- python manage.py runserver

## `main.py` の実行方法

### 事前準備
- Python 3.11 系の実行環境を用意する（`python3.11 --version` で確認）。
- `main.py` と同じディレクトリに `local_settings.py` を作成し、以下の値を設定する。
  ```python
  FOLDER_PATH = "YOUR_FOLDER_PATH"  # 処理済みファイルの移動先
  GROUP_ID = "your_group_id"        # アルファベット大文字推奨
  WORKER_API_BASE_URL = "https://example.com"  # Worker API のベースURL
  ```
- 必要に応じて `ffmpeg` をインストール（FLAC変換が可能になります）。

### すぐに処理を開始する
```bash
cd /Users/codepro/TaSupportSystem_GroupWork
python3.11 main.py
```

### 指定時刻から処理を開始する（sleep方式）
`--start-at` オプションで処理開始時刻を指定できます。時刻は Asia/Tokyo を基準に解釈され、指定時刻がすでに過ぎている場合は翌日同時刻まで待機します。

```bash
# 時刻のみ指定（例: 10:40 開始）
python3.11 main.py --start-at "10:40"

# 秒まで指定
python3.11 main.py --start-at "10:40:00"

# 日付と時刻を指定
python3.11 main.py --start-at "2025-10-04 10:40"
```

不正な形式や過去日時（日時指定）を渡すとエラーで終了します。ログは `processing.log` に追記され、待機中は残り時間が出力されます。
