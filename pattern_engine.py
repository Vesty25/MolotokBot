# pattern_engine.py
import logging
from config import (
    SUPPORT_ZONE_PERCENT,
    MIN_SHADOW_BODY_RATIO,
    MAX_UPPER_SHADOW_RATIO,
    VOLUME_SMA_PERIOD,
    MIN_PRICE,
    MIN_BODY_PCT,
    MIN_SHADOW_PCT
)

logger = logging.getLogger(__name__)

def find_hammer(ticker_data):
    """
    Ищет паттерн "Бычий молот" по цепочке проверок из ТЗ.
    
    Порядок проверок:
    4. Минимальный размер тела >= 0.5% от цены
    5. Минимальная тень >= 2% от цены
    6. Зеленая свеча (Close > Open)
    7. Геометрия «Молота»: нижняя_тень > 2.0 * тело_свечи
    8. Маленькая верхняя тень: <= 20% от тела
    9. Уровень поддержки: close <= 1.03 * min_60
    10. Объемный всплеск: объем > средний_объем_за_20_дней
    
    Возвращает словарь с параметрами паттерна или None
    """
    if ticker_data is None or len(ticker_data) < 60:
        return None
    
    # Берем последние 60 свечей
    hist_60 = ticker_data.tail(60)
    last_candle = hist_60.iloc[-1]
    
    open_p = float(last_candle['open'])
    close_p = float(last_candle['close'])
    high_p = float(last_candle['high'])
    low_p = float(last_candle['low'])
    volume = float(last_candle['volume'])
    
    # Проверка 4: Минимальный размер тела >= 0.5% от цены
    body = abs(close_p - open_p)
    if body == 0:
        return None
    
    body_pct = (body / close_p) * 100
    if body_pct < MIN_BODY_PCT * 100:  # MIN_BODY_PCT = 0.005 (0.5%)
        return None
    
    # Проверка 5: Минимальная нижняя тень >= 2% от цены
    lower_shadow = min(open_p, close_p) - low_p
    shadow_pct = (lower_shadow / close_p) * 100
    if shadow_pct < MIN_SHADOW_PCT * 100:  # MIN_SHADOW_PCT = 0.02 (2%)
        return None
    
    # Проверка 6: Зеленая свеча (Close > Open)
    if close_p <= open_p:
        return None
    
    # Проверка 7: Геометрия «Молота» — нижняя тень > 2 * тело
    if lower_shadow <= MIN_SHADOW_BODY_RATIO * body:
        return None
    
    # Проверка 8: Маленькая верхняя тень — <= 20% от тела
    upper_shadow = high_p - max(open_p, close_p)
    if upper_shadow > MAX_UPPER_SHADOW_RATIO * body:
        return None
    
    # Проверка 9: Уровень поддержки — цена не выше +3% от 60-дневного минимума
    min_60_low = float(hist_60['low'].min())
    support_upper_bound = min_60_low * (1 + SUPPORT_ZONE_PERCENT)
    
    if close_p > support_upper_bound:
        return None
    
    # Проверка 10: Объемный всплеск — сегодняшний объем > среднего за 20 дней
    if len(hist_60) >= VOLUME_SMA_PERIOD:
        avg_volume_20 = float(hist_60['volume'].tail(VOLUME_SMA_PERIOD).mean())
        if avg_volume_20 == 0 or volume <= avg_volume_20:
            return None
        volume_ratio = volume / avg_volume_20
    else:
        return None
    
    # Расчет Score
    score = (lower_shadow / body) * volume_ratio
    
    result = {
        "score": round(score, 2),
        "close": round(close_p, 2),
        "support": round(min_60_low, 2),
        "body_pct": round(body_pct, 1),
        "shadow_pct": round(shadow_pct, 1),
        "volume_ratio": round(volume_ratio, 1)
    }
    
    logger.info(f"✅ Найден Молот! {result['ticker'] if 'ticker' in result else 'N/A'} Score: {score:.2f}")
    return result
