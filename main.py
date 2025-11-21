from flask import Flask, request, abort
from linebot import WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, FollowEvent, TextMessage
from linebot import LineBotApi
import requests   # APIリクエスト用
import os         # 環境変数読み込み用
from datetime import datetime, timedelta

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
    """
    地名から緯度と経度を取得する (Open-Meteo GeoCoding APIを使用)
    """
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
            # 取得した地名情報 (例: 藤沢市) を使用
            return result['latitude'], result['longitude'], result['name'] 
        return None, None, None
    except requests.exceptions.RequestException as e:
        print(f"GeoCoding API Error: {e}")
        return None, None, None

def get_weather_data(latitude, longitude):
    """
    緯度と経度から天気データを取得する (Open-Meteo Weather APIを使用)
    """
    WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        # 必要なデータを日別で取得
        "daily": ["weather_code", "temperature_2m_max", "temperature_2m_min"],
        "timezone": "Asia/Tokyo",
        "forecast_days": 7 # 7日分の予報を取得
    }
    try:
        response = requests.get(WEATHER_URL, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Weather API Error: {e}")
        return None

# Weather Code (WMOコード)を日本語と絵文字に変換する辞書
# スペースをすべて半角で打ち直しました
WEATHER_CODES = {
    0: ("快晴", "☀️"),      # Clear sky
    1: ("快晴", "☀️"),      # Mainly clear
    2: ("一部曇り", "🌤️"), # Partly cloudy
    3: ("曇り", "☁️"),      # Overcast
    45: ("霧", "🌫️"),       # Fog
    51: ("弱い霧雨", "🌧️"),  # Drizzle light
    61: ("弱い雨", "☔️"),    # Rain slight
    63: ("雨", "☔️"),       # Rain moderate
    65: ("激しい雨", "☔️"), # Rain heavy
    71: ("弱い雪", "❄️"),    # Snow fall slight
    80: ("弱いにわか雨", "🌦️"), # Rain showers slight
    81: ("にわか雨", "🌦️"),  # Rain showers moderate
    95: ("雷雨", "⛈️"),      # Thunderstorm
    # その他はここでは省略
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
    
    if not weather_data or 'daily' not in weather_data or len(weather_data['daily']['time']) < 7:
        reply_text = f"ごめんね、{city_name} の天気予報データが不足しているよ😥"
        line_bot_api.reply_message(event.reply_token, TextMessage(text=reply_text))
        return

    daily = weather_data['daily']
    
    # ----------------------------------------------------
    # 3. 曜日を計算し、必要な日のインデックスを取得する
    # ----------------------------------------------------
    
    # 曜日のリスト (月:0, 火:1, ..., 土:5, 日:6)
    TODAY_INDEX = 0
    TOMORROW_INDEX = 1

    # 土曜日と日曜日のインデックスを初期化
    saturday_index = -1
    sunday_index = -1

    # 取得した7日間の日付をチェックし、土曜日と日曜日のインデックスを探す
    for i, date_str in enumerate(daily['time']):
        # date_strは 'YYYY-MM-DD' 形式
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        weekday = date_obj.weekday() # 0=月曜日, 6=日曜日

        if weekday == 5 and saturday_index == -1: # 土曜日 (5)
            saturday_index = i
        elif weekday == 6 and sunday_index == -1: # 日曜日 (6)
            sunday_index = i
        
        # 土曜日と日曜日が見つかったら終了（不要な検索を避ける）
        if saturday_index != -1 and sunday_index != -1:
            break

    # ----------------------------------------------------
    # 4. データを使って予報メッセージを作成する
    # ----------------------------------------------------
    
    # 今日 (インデックス 0)
    today_code = daily['weather_code'][TODAY_INDEX]
    today_max = daily['temperature_2m_max'][TODAY_INDEX]
    today_min = daily['temperature_2m_min'][TODAY_INDEX]
    today_display = get_weather_display(today_code, today_max, today_min)
    
    # 明日 (インデックス 1)
    tomorrow_code = daily['weather_code'][TOMORROW_INDEX]
    tomorrow_max = daily['temperature_2m_max'][TOMORROW_INDEX]
    tomorrow_min = daily['temperature_2m_min'][TOMORROW_INDEX]
    tomorrow_display = get_weather_display(tomorrow_code, tomorrow_max, tomorrow_min)
    
    # 週末 (インデックスが見つかった場合のみ使用)
    saturday_display = "情報なし"
    if saturday_index != -1 and saturday_index < len(daily['weather_code']):
        saturday_code = daily['weather_code'][saturday_index]
        saturday_max = daily['temperature_2m_max'][saturday_index]
        saturday_min = daily['temperature_2m_min'][saturday_index]
        saturday_display = get_weather_display(saturday_code, saturday_max, saturday_min)
    
    sunday_display = "情報なし"
    if sunday_index != -1 and sunday_index < len(daily['weather_code']):
        sunday_code = daily['weather_code'][sunday_index]
        sunday_max = daily['temperature_2m_max'][sunday_index]
        sunday_min = daily['temperature_2m_min'][sunday_index]
        sunday_display = get_weather_display(sunday_code, sunday_max, sunday_min)

    # 明日と土曜日が同じ日の場合、表示を統合
    if TOMORROW_INDEX == saturday_index:
        saturday_label = "（明日）"
    else:
        saturday_label = ""
    
    # 返信メッセージの構築
    # 最後のコードでは city_name が今日と明日の表示に入っていなかったので追加します
    reply_text = f"{city_name} の空だよ✨\n\n" \
                 f"今日： {city_name} {today_display}\n" \
                 f"明日： {city_name} {tomorrow_display}\n" \
                 f"\n週末予想：\n" \
                 f"土曜日{saturday_label}: {saturday_display}\n" \
                 f"日曜日: {sunday_display}\n\n" \
                 f"素敵な1日になりますように✨"
    
    line_bot_api.reply_message(
        event.reply_token,
        TextMessage(text=reply_text)
    )

if __name__ == "__main__":
    print("サーバー起動中…")
    # Flaskサーバーをホスト0.0.0.0とポート10000で起動
    app.run(host="0.0.0.0", port=10000)