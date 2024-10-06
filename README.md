# 起動メモ
- brew services start mysql@8.4
- python manage.py makemigrations
- python manage.py migrate
- python manage.py runserver 

# データ入力メモ(main.py)
- deepgram-sdk==2.12.0 で動作（最新の入れると動かないかも）
- local_settings.pyをmain.pyと同じ階層に作成
  - DEEPGRAM_API_KEY = 'YOUR_API_KEY'
  - FOLDER_PATH = 'YOUR_FOLDER_PATH'
  - DJANGO_API_URL = "http://YOUR_LOCAL_IP_ADDRESS/api/data/"
  - GROUP_ID = アルファベット小文字
