# config.py
import os

# === Telegram ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
APP_URL = os.getenv("APP_URL", "https://molotok-bot.onrender.com")
PORT = int(os.getenv("PORT", 8080))

# === Время рассылок (МСК) ===
MORNING_SCAN_HOUR = 10
MORNING_SCAN_MINUTE = 30
EVENING_SCAN_HOUR = 19
EVENING_SCAN_MINUTE = 30

# === Общие фильтры ===
MIN_AVG_VOLUME_RUB = 10_000_000  # Мин. среднедневной объём в рублях
MIN_PRICE = 10                    # Мин. цена закрытия
MIN_DAYS_HISTORY = 365            # Глубина загрузки свечей
SUPPORT_LOOKBACK = 60             # Дней для поиска поддержки
TOP_LIMIT = 10                    # Макс. сигналов в отчёте

# === Задержки и ретраи ===
API_REQUEST_DELAY = 0.2           # Задержка между запросами к API (сек)
API_RETRY_DELAY = 5               # Задержка перед повтором при ошибке
API_MAX_RETRIES = 1               # Количество повторов

# === Стратегия 1: Молот ===
HAMMER_SHADOW_BODY_RATIO = 2.0    # Нижняя тень / тело
HAMMER_MAX_UPPER_SHADOW = 0.2     # Верхняя тень ≤ 20% от тела
HAMMER_SUPPORT_PCT = 3            # Макс. % выше 60-дневного минимума
HAMMER_MIN_BODY_PCT = 0.5         # Минимальное тело (% от цены)
HAMMER_MIN_SHADOW_PCT = 2.0       # Минимальная тень (% от цены)

# === Стратегия 2: Пробой тишины ===
BREAKOUT_RANGE_PCT = 2            # Макс. средняя амплитуда за 15 дней (%)
BREAKOUT_VOLUME_RATIO = 1.5       # Объём / Средний объём за 15 дней
BREAKOUT_LOOKBACK = 15            # Период для поиска боковика

# === Стратегия 3: Отскок от EMA 50 ===
EMA50_TOUCH_PCT = 1               # Допуск касания (% выше EMA 50)
EMA50_RSI_MIN = 35                # Минимальный RSI

# === Параметры индикаторов ===
EMA_PERIODS = [20, 50, 200]
RSI_PERIOD = 14
BB_PERIOD = 20
BB_STD = 2
