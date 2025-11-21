from flask import Flask, request, abort
from linebot import WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, FollowEvent, TextMessage
from linebot import LineBotApi
import requests   # HTTPリクエスト用
import os         # 環境変数読み込み用

app = Flask(__name__)

# --- 認証情報の読み込み (Canvas環境用) ---
# Line Botの機密情報を安全にシークレットから読み込む
# 実行環境に合わせて適宜修正してください
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
    # wttr.inから天気情報を取得
    # formatパラメータを使って必要な情報をピンポイントで取得します。
    # %l: 場所, %c: 天気アイコン, %t: 気温
    # @1: 明日の情報
    # &lang=ja: 日本語, &m: 摂氏(Metric)
    # ----------------------------------------------------
    
    # 今日の天気（場所名、アイコン、気温）
    # 元のコードのURLをそのまま使用
    today_url = f"http://wttr.in/{city}?format=%l+%c+%t&lang=ja&m"
    today = requests.get(today_url).text.strip()
    
    # ★明日の天気★
    # format=%c@1+%t@1で「明日のアイコンと気温」を確実に取得します。
    tomorrow_url = f"http://wttr.in/{city}?format=%c@1+%t@1&lang=ja&m"
    tomorrow_raw = requests.get(tomorrow_url).text.strip()
    
    # wttr.inが失敗すると'Unknown location'などを返すため、結果をチェック
    if tomorrow_raw and 'Unknown location' not in tomorrow_raw:
        tomorrow = f"{city} {tomorrow_raw}"
    else:
        tomorrow = "明日の情報が見つかりませんでした"
    
    # 週末予報（土日を綺麗に）
    # この部分は元のコードのままでもフォーマット指定があるので機能します。
    weekend_url = f"http://wttr.in/{city}?format=土曜日: %c+%t 日曜日: %c+%t&lang=ja&m"
    weekend_full = requests.get(weekend_url).text
    weekend = weekend_full.strip().replace("土曜日:", "\n土曜日:").replace("日曜日:", "\n日曜日:")
    
    # 返信メッセージの構築
    reply_text = f"【{city}の空だよ✨】\n\n" \
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
    # これはCanvas環境で動作させるための設定です。
    app.run(host="0.0.0.0", port=10000)