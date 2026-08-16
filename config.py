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

# === Стратегия 4: Сжатая пружина ===
SQUEEZE_BWINDOW = 60             # Окно поиска минимума ширины BB
SQUEEZE_BW_THRESHOLD = 1.05     # Порог: сегодняшняя ширина ≤ мин * 1.05
SQUEEZE_RSI_MAX = 65             # Максимальный RSI для входа
SQUEEZE_BB_PERIOD = 20           # Период Bollinger Bands
SQUEEZE_BB_STD = 2               # Стандартное отклонение BB

# === Стратегия 5: Двойное дно ===
DB_LOOKBACK = 30                 # Глубина поиска первого дна
DB_SECOND_BOTTOM_WINDOW = 5     # Окно поиска второго дна
DB_LEVEL_TOLERANCE = 0.03       # Допуск совпадения уровней (±3%)
DB_MIN_REBOUND = 0.03           # Минимальный отскок от первого дна (+3%)
DB_MID_PEAK_MIN = 0.05          # Минимальная высота промежуточного пика (+5%)

# === Параметры индикаторов ===
EMA_PERIODS = [20, 50, 200]
RSI_PERIOD = 14
BB_PERIOD = 20
BB_STD = 2

# === Список голубых фишек ===
BLUE_CHIPS = [
    'SBER', 'SBERP', 'LKOH', 'GAZP', 'GMKN', 'ROSN', 'TATN', 'TATNP',
    'NVTK', 'SNGS', 'SNGSP', 'MTSS', 'AFKS', 'VTBR', 'PLZL', 'YNDX',
    'OZON', 'MAGN', 'NLMK', 'CHMF', 'MOEX', 'AFLT', 'ALRS', 'PIKK',
    'RUAL', 'TRNFP', 'SIBN', 'FIVE', 'MVID', 'IRAO', 'MGNT', 'GCHE',
]

# === Глобальный фильтр паники ===
PANIC_THRESHOLD_PCT = 3.0  # Порог паники: падение IMOEX за день, %

BLOCKED_IN_PANIC = [
    'hammer',
    'double_bottom',
    'ema50_bounce',
    'breakout',
    'mean_reversion',
    'bullish_engulfing',
    'squeeze',
]

# === Стратегия 6: Сильная бумага ===
RS_MIN_MARKET_DROP = 2.0          # IMOEX должен упасть минимум на 2%
RS_MIN_OUTPERFORM_PCT = 2.0       # Акция должна быть лучше рынка на 2 п.п.
RS_MAX_DROP_ACT = -0.5            # Акция не должна падать сильнее -0.5%
RS_BLUE_CHIP_ONLY = True          # Только голубые фишки

# === Стратегия 7: Возврат к EMA 20 ===
MR_MIN_DEVIATION_PCT = 7.0        # Отклонение от EMA 20, %
MR_RSI_MAX = 35                   # Максимальный RSI
MR_BLUE_CHIP_ONLY = True

# === Стратегия 8: Бычье поглощение ===
BE_BLUE_CHIP_ONLY = True
BE_MIN_BODY_RATIO = 1.0           # Тело сегодня >= тела вчера

# === Стратегия 9: Дивидендный разрыв ===
DG_DAYS_SINCE_CUTOFF = 10         # Дней после отсечки
DG_MIN_GAP_PCT = 3.0              # Минимальный гэп, %
DG_MIN_RECOVERY_PCT = 2.0         # Минимальное восстановление, %
DG_BLUE_CHIP_ONLY = True

# === Дивидендные отсечки (ручная таблица для ТОП-30) ===
# Формат: {'ticker': 'YYYY-MM-DD'}
DIVIDEND_CUTOFF_DATES = {
    # Примеры — замените на актуальные даты
    # 'SNGS': '2026-07-15',
    # 'SNGSP': '2026-07-15',
    # 'SBER': '2026-06-10',
    # 'SBERP': '2026-06-10',
}
