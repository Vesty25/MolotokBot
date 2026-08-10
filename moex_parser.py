# moex_parser.py
import requests
import pandas as pd
import logging
from config import MIN_DAYS_HISTORY

logger = logging.getLogger(__name__)

def get_filtered_tickers():
    """
    Получает список ВСЕХ инструментов из TQBR с типом бумаги.
    Возвращает DataFrame с колонками: ticker, short_name, lot_size, sec_type
    """
    url = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"
    params = {
        "iss.meta": "off",
        "iss.only": "securities",
        "securities.columns": "SECID,SHORTNAME,LOTSIZE,SECTYPE"
    }
    
    try:
        logger.info("Загрузка списка инструментов TQBR...")
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        df = pd.DataFrame(
            data['securities']['data'],
            columns=data['securities']['columns']
        )
        
        df = df.rename(columns={
            'SECID': 'ticker',
            'SHORTNAME': 'short_name',
            'LOTSIZE': 'lot_size',
            'SECTYPE': 'sec_type'
        })
        
        logger.info(f"Загружено {len(df)} инструментов из TQBR")
        return df[['ticker', 'short_name', 'lot_size', 'sec_type']]
        
    except Exception as e:
        logger.error(f"Ошибка загрузки инструментов: {e}")
        raise

def is_valid_share_type(sec_type):
    """
    Проверяет, является ли бумага обыкновенной или привилегированной акцией.
    Отсекает ETF, ПИФы, облигации, ноты, валюту.
    """
    if not sec_type:
        return False
    
    sec_type_lower = str(sec_type).lower()
    valid_types = ['common_share', 'preferred_share']
    return sec_type_lower in valid_types

def get_daily_candles(ticker, days=MIN_DAYS_HISTORY):
    """
    Загружает дневные свечи для указанного тикера.
    """
    url = f"https://iss.moex.com/iss/engines/stock/markets/shares/securities/{ticker}/candles.json"
    params = {
        "interval": 24,
        "iss.meta": "off",
        "iss.only": "candles",
        "candles.columns": "open,close,high,low,volume,begin"
    }
    
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        if 'candles' not in data or len(data['candles']['data']) == 0:
            return None
            
        df = pd.DataFrame(
            data['candles']['data'],
            columns=data['candles']['columns']
        )
        
        df['date'] = pd.to_datetime(df['begin'])
        df = df.sort_values('date', ascending=True)
        
        return df.tail(days)
        
    except Exception as e:
        logger.error(f"Ошибка загрузки свечей для {ticker}: {e}")
        return None

def calculate_average_volume_rub(ticker_data, lot_size):
    """
    Рассчитывает средний дневной объем в рублях за 20 дней.
    Объем в рублях = volume (лоты) * lot_size * close_price
    """
    if ticker_data is None or len(ticker_data) < 20:
        return 0
        
    last_20 = ticker_data.tail(20)
    
    # Объем каждой свечи в рублях
    daily_volumes_rub = last_20['volume'] * lot_size * last_20['close']
    avg_volume_rub = daily_volumes_rub.mean()
    
    return avg_volume_rub
