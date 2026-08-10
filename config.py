# config.py
import os

# Токен Telegram бота (Render будет передавать через переменные окружения)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TOKEN_HERE")

# URL вашего приложения на Render (важно для UptimeRobot)
# Формат: https://ваш-нейм.onrender.com
APP_URL = os.getenv("APP_URL", "https://molotok-bot.onrender.com")

# Порт для веб-сервера (Render требует слушать порт из переменной PORT)
PORT = int(os.getenv("PORT", 8080))

# Время рассылок (МСК)
MORNING_SCAN_HOUR = 10
MORNING_SCAN_MINUTE = 30
EVENING_SCAN_HOUR = 19
EVENING_SCAN_MINUTE = 30

# Параметры фильтрации
MIN_DAYS_HISTORY = 60
SUPPORT_ZONE_PERCENT = 0.03
VOLUME_SMA_PERIOD = 20
MIN_AVG_VOLUME_RUB = 10_000_000
TOP_LIMIT = 10

# Параметры паттерна "Молот"
MIN_SHADOW_BODY_RATIO = 2.0
MAX_UPPER_SHADOW_RATIO = 0.2