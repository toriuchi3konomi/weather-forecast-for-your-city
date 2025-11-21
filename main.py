from flask import Flask, request, abort
from linebot import WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, FollowEvent, TextMessage
from linebot import LineBotApi
import requests # APIリクエスト用
import os # 環境変数読み込み用

app = Flask(__name__)

# --- 認証情報の読み込み (Canvas環境用) ---
try:
    CHANNEL_SECRET = os.environ['CHANNEL_SECRET']
    CHANNEL_ACCESS_TOKEN = os.environ['CHANNEL_ACCESS_TOKEN']
except KeyError:
    print("Warning: LINE secret/token not found in environment variables.")
    CHANNEL_SECRET = "YOUR_CHANNEL_SECRET"
    CHANNEL_ACCESS_TOKEN = "YOUR_CHANNEL_ACCESS_TOKEN"

handler = WebhookHandler(CHANNEL_SECRET)
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)

# ----------------------------------------------------
# 外部APIとの連携関数
# ----------------------------------------------------

def get_coordinates(city_name):
    """地名から緯度と経度を取得する (Open-Meteo GeoCoding APIを使用)"""
    GEOCoding_URL = "https://geocoding-api.open-meteo.com/v1/search"
    params = {
        "name": city_name,
        "count": 1,
        "language": "ja",
        "format": "json"
    }
    try:
        response = requests.get(GEOCoding_URL, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data.get('results'):
            result = data['results'][0]
            return result['latitude'], result['longitude'], result['name'] 
        return None, None, None
    except requests.exceptions.RequestException as e:
        print(f"GeoCoding API Error: {e}")
        return None, None, None

def get_weather_data(latitude, longitude):
    """緯度と経度から天気データを取得する (Open-Meteo Weather APIを使用)"""
    WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        # 今日と明日分の日別データのみを取得
        "daily": ["weather_code", "temperature_2m_max", "temperature_2m_min"],
        "timezone": "Asia/Tokyo",
        "forecast_days": 2 # 2日分（今日と明日）のみ
    }
    try:
        response = requests.get(WEATHER_URL, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Weather API Error: {e}")
        return None

# Weather Code (WMOコード)を日本語と絵文字に変換する辞書
WEATHER_CODES = {
    0: ("快晴", "☀️"), 
    1: ("快晴", "☀️"), 
    2: ("一部曇り", "🌤️"), 
    3: ("曇り", "☁️"), 
    45: ("霧", "🌫️"), 
    51: ("弱い霧雨", "🌧️"), 
    61: ("弱い雨", "☔️"), 
    63: ("雨", "☔️"), 
    65: ("激しい雨", "☔️"), 
    71: ("弱い雪", "❄️"), 
    80: ("弱いにわか雨", "🌦️"), 
    81: ("にわか雨", "🌦️"), 
    95: ("雷雨", "⛈️"), 
    }

def get_weather_display(code, max_temp, min_temp):
    """WMOコードと気温から表示文字列を生成する"""
    description, emoji = WEATHER_CODES.get(code, ("不明", "❓"))
    # 小数点以下を切り捨てて表示
    return f"{emoji} {description} {int(max_temp)}°C / {int(min_temp)}°C"

# ----------------------------------------------------
# LINE Botのイベントハンドラ
# ----------------------------------------------------

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

@handler.add(FollowEvent)
def handle_follow(event):
    """友だち追加されたときの処理"""
    line_bot_api.reply_message(
        event.reply_token,
        TextMessage(text="あなたの街のお天気ボットだよ✨\n街のお名前を教えてね！(例：藤沢)")
    )

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """ユーザーからのテキストメッセージを受け取って、天気予報を返す"""
    city_input = event.message.text.strip()
    
    # 1. 地名から緯度・経度を取得
    latitude, longitude, city_name = get_coordinates(city_input)
    
    if not latitude or not longitude:
        reply_text = f"ごめんね、'{city_input}' の場所情報が見つからなかったよ😥\n別の地名で試してみてね！"
        line_bot_api.reply_message(event.reply_token, TextMessage(text=reply_text))
        return
        
    # 2. 緯度・経度から天気データを取得
    weather_data = get_weather_data(latitude, longitude)
    
    # 2日分のデータ（今日[0]と明日[1]）があることを確認
    if not weather_data or 'daily' not in weather_data or len(weather_data['daily']['time']) < 2:
        reply_text = f"ごめんね、{city_name} の天気予報データが不足しているよ😥"
        line_bot_api.reply_message(event.reply_token, TextMessage(text=reply_text))
        return

    daily = weather_data['daily']
    
    # ----------------------------------------------------
    # 3. データを使って予報メッセージを作成する
    # ----------------------------------------------------
    
    # 今日 (インデックス 0)
    TODAY_INDEX = 0
    today_code = daily['weather_code'][TODAY_INDEX]
    today_max = daily['temperature_2m_max'][TODAY_INDEX]
    today_min = daily['temperature_2m_min'][TODAY_INDEX]
    today_display = get_weather_display(today_code, today_max, today_min)
    
    # 明日 (インデックス 1)
    TOMORROW_INDEX = 1
    tomorrow_code = daily['weather_code'][TOMORROW_INDEX]
    tomorrow_max = daily['temperature_2m_max'][TOMORROW_INDEX]
    tomorrow_min = daily['temperature_2m_min'][TOMORROW_INDEX]
    tomorrow_display = get_weather_display(tomorrow_code, tomorrow_max, tomorrow_min)
    
    # 返信メッセージの構築
    reply_text = f"{city_name} の空だよ✨\n\n" \
                 f"今日： {city_name} {today_display}\n" \
                 f"明日： {city_name} {tomorrow_display}\n" \
                 f"\n素敵な1日になりますように✨"
    
    line_bot_api.reply_message(
        event.reply_token,
        TextMessage(text=reply_text)
    )

if __name__ == "__main__":
    print("サーバー起動中…")
    # Flaskサーバーをホスト0.0.0.0とポート10000で起動
    app.run(host="0.0.0.0", port=10000)