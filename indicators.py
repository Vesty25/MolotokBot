# indicators.py
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

def add_all_indicators(df):
    """
    Добавляет все технические индикаторы к DataFrame со свечами.
    """
    if df is None or len(df) == 0:
        return None
    
    df = df.copy()
    
    # EMA
    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # RSI 14
    df['rsi_14'] = calculate_rsi(df['close'], period=14)
    
    # Bollinger Bands (20, 2)
    df['bb_middle'] = df['close'].rolling(window=20).mean()
    bb_std = df['close'].rolling(window=20).std()
    df['bb_upper'] = df['bb_middle'] + 2 * bb_std
    df['bb_lower'] = df['bb_middle'] - 2 * bb_std
    
    # Bandwidth (ширина полосы)
    df['bandwidth'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
    
    # Средний объём за 20 дней
    df['avg_volume_20'] = df['volume'].rolling(window=20).mean()
    
    return df


def calculate_rsi(series, period=14):
    """Рассчитывает RSI без сторонних библиотек."""
    delta = series.diff()
    
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    
    for i in range(period, len(avg_gain)):
        avg_gain.iloc[i] = (avg_gain.iloc[i-1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i-1] * (period - 1) + loss.iloc[i]) / period
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def get_support_level(df, days=60):
    """Возвращает минимальную цену low за последние N дней."""
    if df is None or len(df) < days:
        return None
    return float(df['low'].tail(days).min())
