# 起動メモ
- brew services start mysql@8.4
- python manage.py makemigrations
- python manage.py migrate
- python manage.py runserver 

# データ入力メモ(main.py)
- Python 3.11以下で動作
- local_settings.pyをmain.pyと同じ階層に作成
  - FOLDER_PATH = 'YOUR_FOLDER_PATH'
  - GROUP_ID = アルファベット小文字
  - WORKER_API_BASE_URL = "<デプロイしたURL>"
