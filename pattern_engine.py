# pattern_engine.py
import pandas as pd
import numpy as np
from config import SUPPORT_ZONE_PERCENT, MIN_SHADOW_BODY_RATIO, MAX_UPPER_SHADOW_RATIO, VOLUME_SMA_PERIOD

def find_hammer(ticker_data):
    """
    Проверяет последнюю свечу на соответствие паттерну "Молот".
    Возвращает словарь с деталями, если паттерн найден, иначе None.
    """
    if ticker_data is None or len(ticker_data) < 60:
        return None

    # Берем всю историю (60 дней) и отдельно последнюю свечу
    hist_60 = ticker_data.tail(60)
    last_candle = hist_60.iloc[-1]

    open_p, close_p, high_p, low_p, volume = last_candle[['open', 'close', 'high', 'low', 'volume']]
    
    # Условие 1: Бычий молот — тело зеленое (Close > Open)
    if close_p <= open_p:
        return None

    # Геометрия свечи
    body = close_p - open_p
    if body == 0:
        return None
        
    lower_shadow = min(open_p, close_p) - low_p
    upper_shadow = high_p - max(open_p, close_p)

    # Условие 2: Нижняя тень минимум в 2 раза больше тела
    if lower_shadow < MIN_SHADOW_BODY_RATIO * body:
        return None

    # Условие 3: Верхняя тень не более 20% от тела
    if upper_shadow > MAX_UPPER_SHADOW_RATIO * body:
        return None

    # Проверка уровня поддержки
    min_60_low = hist_60['low'].min()
    # Цена закрытия должна быть не выше min_60_low + 3%
    support_upper_bound = min_60_low * (1 + SUPPORT_ZONE_PERCENT)
    if close_p > support_upper_bound:
        return None

    # Проверка объема: объем сегодня выше среднего за 20 дней
    if len(hist_60) >= VOLUME_SMA_PERIOD:
        avg_volume_20 = hist_60['volume'].tail(VOLUME_SMA_PERIOD).mean()
        if volume <= avg_volume_20:
            return None
        volume_ratio = volume / avg_volume_20
    else:
        return None

    # Расчет Score
    shadow_body_ratio = lower_shadow / body
    score = shadow_body_ratio * volume_ratio

    # Дополнительные метрики для отчета
    body_pct = (body / open_p) * 100
    shadow_pct = (lower_shadow / open_p) * 100

    return {
        "score": round(score, 2),
        "close": close_p,
        "support": round(min_60_low, 2),
        "body_pct": round(body_pct, 2),
        "shadow_pct": round(shadow_pct, 2),
        "volume_ratio": round(volume_ratio, 2)
    }