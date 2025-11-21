from flask import Flask, request, abort

from linebot import WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, FollowEvent, TextMessage
from linebot import LineBotApi
import requests   # ← これを上の方に追加！

app = Flask(__name__)

import os # 👈 これがコードの先頭付近（例：8行目）にあるか確認
# ...
# Line Botの機密情報を安全にシークレットから読み込む
CHANNEL_SECRET = os.environ['CHANNEL_SECRET']
CHANNEL_ACCESS_TOKEN = os.environ['CHANNEL_ACCESS_TOKEN']
# 👈 CHANNEL_ACCESS_TOKENの読み込み行をここに追加（もしos.environで挿入済みならそのまま）
# ...
handler = WebhookHandler(CHANNEL_SECRET) # 👈 os.environから読み込んだ変数を使用
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN) # 👈 os.environから読み込んだ変数を使用

@app.route("/webhook", methods=['POST'])
def webhook():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# 友だち追加されたら挨拶！
@handler.add(FollowEvent)
def handle_follow(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextMessage(text="あなたの街のお天気ボットだよ✨\n街のお名前を教えてね！(例：藤沢)")
    )

# ★ここだけ残す！（天気教えてくれる本体）
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    city = event.message.text.strip()
    
        # 未来の空を完璧に覗く魔法（これで本当に完璧！）
    import requests
    
    # 今日の天気
    today_url = f"http://wttr.in/{city}?format=%l+%c+%t&lang=ja&m"
    today = requests.get(today_url).text.strip()
    
    # 明日の天気（絵文字と温度を確実に抜き出す！）
    tomorrow_full = requests.get(f"http://wttr.in/{city}?0&lang=ja&m").text
    tomorrow = "情報取得中…"
    for line in tomorrow_full.split('\n'):
        if "°C" in line:
            # 場所名 + 絵文字 + 温度だけにする
            parts = line.split()
            if len(parts) >= 3 and '+' in parts[-1]:
                tomorrow = f"{city} {parts[-2]} {parts[-1]}"
            break
    
    # 週末予報（土日を綺麗に改行）
    weekend_full = requests.get(f"http://wttr.in/{city}?format=土曜日: %c+%t 日曜日: %c+%t&lang=ja&m").text
    weekend = weekend_full.strip().replace("土曜日:", "\n土曜日:").replace("日曜日:", "\n日曜日:")

    reply_text = f"{city}の空だよ✨\n\n" \
                 f"今日： {today}\n" \
                 f"明日： {tomorrow}\n" \
                 f"週末予想： {weekend}\n\n" \
                 f"素敵な1日になりますように✨"
    
    line_bot_api.reply_message(
        event.reply_token,
        TextMessage(text=reply_text)
    )
if __name__ == "__main__":
    print("サーバー起動中…")
    app.run(host="0.0.0.0", port=10000)   # ← これに変更！！