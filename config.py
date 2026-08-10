# config.py
import os

# Токен Telegram бота
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# URL приложения
APP_URL = os.getenv("APP_URL", "https://molotok-bot.onrender.com")

# Порт для веб-сервера
PORT = int(os.getenv("PORT", 8080))

# Время рассылок МСК
MORNING_SCAN_HOUR = 10
MORNING_SCAN_MINUTE = 30
EVENING_SCAN_HOUR = 19
EVENING_SCAN_MINUTE = 30

# Параметры анализа рынка
MIN_DAYS_HISTORY = 60
SUPPORT_ZONE_PERCENT = 0.03    # 3% от уровня поддержки
VOLUME_SMA_PERIOD = 20
MIN_AVG_VOLUME_RUB = 10_000_000  # Минимальный средний объем
TOP_LIMIT = 10

# Новые фильтры
MIN_PRICE = 10.0                # Минимальная цена закрытия (руб)
MIN_BODY_PCT = 0.005            # Минимальное тело 0.5%
MIN_SHADOW_PCT = 0.02           # Минимальная тень 2%

# Параметры паттерна "Молот"
MIN_SHADOW_BODY_RATIO = 2.0    # Нижняя тень минимум в 2 раза больше тела
MAX_UPPER_SHADOW_RATIO = 0.2   # Верхняя тень не более 20% от тела
