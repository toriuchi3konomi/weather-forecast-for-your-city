from flask import Flask, request, abort
from linebot import WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, FollowEvent, TextMessage
from linebot import LineBotApi
import requests # HTTPリクエスト用
import os # 環境変数読み込み用

app = Flask(__name__)

# --- 認証情報の読み込み (Canvas環境用) ---
# Line Botの機密情報を安全にシークレットから読み込む
try:
    CHANNEL_SECRET = os.environ['CHANNEL_SECRET']
    CHANNEL_ACCESS_TOKEN = os.environ['CHANNEL_ACCESS_TOKEN']
except KeyError:
    # 開発用（実際には安全な方法で読み込むべきです）
    print("Warning: LINE secret/token not found in environment variables.")
    CHANNEL_SECRET = "YOUR_CHANNEL_SECRET"
    CHANNEL_ACCESS_TOKEN = "YOUR_CHANNEL_ACCESS_TOKEN"

handler = WebhookHandler(CHANNEL_SECRET)
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)

@app.route("/webhook", methods=['POST'])
def webhook():
    """LINEプラットフォームからのWebhookを受信するエンドポイント"""
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Check your channel secret.")
        abort(400)
    return 'OK'

# 友だち追加されたら挨拶！
@handler.add(FollowEvent)
def handle_follow(event):
    """友だち追加されたときの処理"""
    line_bot_api.reply_message(
        event.reply_token,
        TextMessage(text="あなたの街のお天気ボットだよ✨\n街のお名前を教えてね！(例：藤沢)")
    )

# ユーザーからのメッセージに対応する本体
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """ユーザーからのテキストメッセージを受け取って、天気予報を返す"""
    city = event.message.text.strip()
    
    # ----------------------------------------------------
    # wttr.inから天気情報を取得 (クリーンな情報を得るため、場所名(%l)はURLから除外)
    # %c: 天気アイコン, %h: 最高気温, %l: 最低気温
    # @1/@2: 明日/明後日の情報
    # ----------------------------------------------------
    
    # 1. 今日の天気: 天気アイコン + 最高/最低気温
    # 応答例: "☀️ +15°C/+5°C"
    today_url = f"http://wttr.in/{city}?format=%c+%h/%l&lang=ja&m"
    today_raw = requests.get(today_url).text.strip()
    today = f"{city} {today_raw}" # Python側で場所名を付加
    
    # 2. 明日の天気: 天気アイコン + 最高/最低気温
    # 応答例: "☀️ +16°C/+7°C"
    tomorrow_url = f"http://wttr.in/{city}?format=%c@1+%h@1/%l@1&lang=ja&m"
    tomorrow_raw = requests.get(tomorrow_url).text.strip()
    
    # 不要な"@1"を削除し、さらに前後の余分な空白も除去
    tomorrow_clean = tomorrow_raw.replace('@1', '').strip()
    
    if tomorrow_clean and 'Unknown location' not in tomorrow_clean:
        tomorrow = f"{city} {tomorrow_clean}" # Python側で場所名を付加
    else:
        tomorrow = "明日の情報が見つかりませんでした"

    # 3. 週末予報（土日を綺麗に）: 天気アイコン + 最高/最低気温
    # 応答例: "土曜日: ☀️ +14°C/+6°C 日曜日: ☁️ +13°C/+8°C"
    weekend_format = "土曜日: %c@1+%h@1/%l@1 日曜日: %c@2+%h@2/%l@2"
    weekend_url = f"http://wttr.in/{city}?format={weekend_format}&lang=ja&m"
    weekend_full = requests.get(weekend_url).text
    
    # 不要な"@1"や"@2"を削除
    weekend_clean = weekend_full.replace('@1', '').replace('@2', '').strip()

    # 表示を整形: 改行と日付指定子をクリーンアップ
    weekend = weekend_clean.replace("土曜日:", "\n土曜日:").replace("日曜日:", "\n日曜日:")
    
    # 返信メッセージの構築
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
    # Flaskサーバーをホスト0.0.0.0とポート10000で起動
    app.run(host="0.0.0.0", port=10000)