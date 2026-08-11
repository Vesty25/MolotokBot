# moex_api.py
import requests
import pandas as pd
import logging
import time
from datetime import datetime, timedelta

from config import (
    MIN_DAYS_HISTORY, API_REQUEST_DELAY, API_RETRY_DELAY, API_MAX_RETRIES,
    MIN_PRICE, MIN_AVG_VOLUME_RUB
)
from indicators import add_all_indicators

logger = logging.getLogger(__name__)

# Строковые коды типов акций
VALID_SEC_TYPES = ["1", "2"]


def get_all_tickers_tqbr():
    """
    Загружает список всех инструментов из TQBR.
    Возвращает DataFrame с колонками: ticker, short_name, lot_size, sec_type
    """
    url = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"
    params = {
        "iss.meta": "off",
        "iss.only": "securities",
        "securities.columns": "SECID,SHORTNAME,LOTSIZE,SECTYPE"
    }
    
    try:
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
        
        # Фильтр по типу: только обыкновенные и привилегированные акции
        df['sec_type_str'] = df['sec_type'].astype(str)
        df = df[df['sec_type_str'].isin(VALID_SEC_TYPES)].copy()
        
        logger.info(f"Загружено {len(df)} акций из TQBR")
        return df[['ticker', 'short_name', 'lot_size', 'sec_type']]
        
    except Exception as e:
        logger.error(f"Ошибка загрузки списка TQBR: {e}")
        return pd.DataFrame()


def fetch_candles_with_retry(ticker, days=MIN_DAYS_HISTORY):
    """
    Загружает дневные свечи с повторными попытками при ошибках.
    """
    today = datetime.now()
    one_year_ago = today - timedelta(days=days)
    
    url = f"https://iss.moex.com/iss/engines/stock/markets/shares/securities/{ticker}/candles.json"
    params = {
        "interval": 24,
        "iss.meta": "off",
        "iss.only": "candles",
        "candles.columns": "open,close,high,low,volume,begin",
        "from": one_year_ago.strftime("%Y-%m-%d"),
        "till": today.strftime("%Y-%m-%d")
    }
    
    for attempt in range(API_MAX_RETRIES + 1):
        try:
            if attempt > 0:
                logger.info(f"Повторная попытка {attempt} для {ticker}")
                time.sleep(API_RETRY_DELAY)
            
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
            
            # Конвертируем числовые колонки
            for col in ['open', 'close', 'high', 'low', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            return df
            
        except Exception as e:
            logger.error(f"Ошибка загрузки {ticker} (попытка {attempt+1}): {e}")
            if attempt >= API_MAX_RETRIES:
                return None
    
    return None


def load_market_data():
    """
    Загружает и подготавливает данные по всем акциям.
    
    Возвращает список словарей:
    [
        {
            'ticker': 'SBER',
            'short_name': 'Сбербанк',
            'lot_size': 10,
            'data': DataFrame с индикаторами,
            'support_60': float (минимум за 60 дней)
        },
        ...
    ]
    """
    tickers_df = get_all_tickers_tqbr()
    if tickers_df.empty:
        logger.error("Не удалось загрузить список акций")
        return []
    
    logger.info(f"Начинаю загрузку свечей для {len(tickers_df)} акций...")
    
    market_data = []
    loaded = 0
    skipped_no_data = 0
    skipped_low_price = 0
    skipped_low_volume = 0
    skipped_errors = 0
    
    for _, row in tickers_df.iterrows():
        try:
            ticker = row['ticker']
            lot_size = int(row['lot_size'])
            short_name = row['short_name']
            
            # Загружаем свечи
            df = fetch_candles_with_retry(ticker)
            if df is None or len(df) < 60:
                skipped_no_data += 1
                continue
            
            # Последняя цена
            last_close = float(df['close'].iloc[-1])
            
            # Фильтр минимальной цены
            if last_close <= MIN_PRICE:
                skipped_low_price += 1
                continue
            
            # Фильтр ликвидности
            last_20 = df.tail(20)
            avg_vol_rub = (last_20['volume'].mean() * lot_size * last_20['close'].mean())
            if avg_vol_rub < MIN_AVG_VOLUME_RUB:
                skipped_low_volume += 1
                continue
            
            # Добавляем индикаторы
            df = add_all_indicators(df)
            
            # Уровень поддержки (минимум за 60 дней)
            support_60 = float(df['low'].tail(60).min())
            
            market_data.append({
                'ticker': ticker,
                'short_name': short_name,
                'lot_size': lot_size,
                'data': df,
                'support_60': support_60
            })
            
            loaded += 1
            
            if loaded % 50 == 0:
                logger.info(f"Загружено: {loaded}...")
            
            # Задержка между запросами
            time.sleep(API_REQUEST_DELAY)
            
        except Exception as e:
            skipped_errors += 1
            if skipped_errors <= 3:
                logger.error(f"Ошибка обработки {row.get('ticker', '?')}: {e}")
            continue
    
    logger.info("=" * 60)
    logger.info(f"ИТОГО загружено: {loaded}")
    logger.info(f"Пропущено: нет данных={skipped_no_data}, цена={skipped_low_price}, объём={skipped_low_volume}, ошибки={skipped_errors}")
    logger.info("=" * 60)
    
    return market_data
