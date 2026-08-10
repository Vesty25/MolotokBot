# moex_parser.py
import requests
import pandas as pd
import time
import datetime
from config import MIN_DAYS_HISTORY, MIN_AVG_VOLUME_RUB

def get_all_tickers():
    """
    Получает список всех акций, торгующихся в основном режиме TQBR.
    Возвращает DataFrame с колонками: 'ticker' (SECID), 'short_name', 'lot_size'.
    """
    url = "https://iss.moex.com/iss/engines/stock/markets/shares/securities.json"
    params = {
        "marketdata_board": "TQBR",
        "iss.meta": "off",
        "iss.only": "securities",
        "securities.columns": "SECID,SHORTNAME,LOTSIZE"
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    
    df = pd.DataFrame(data['securities']['data'], columns=data['securities']['columns'])
    # Фильтруем явно не акции (облигации, фонды). Обычно достаточно убрать явные префиксы, но здесь проще взять все из TQBR
    # TQBR сам отдает только акции и паи. Дополнительно можно вычистить паи, если их SECID содержит '_ETF' или '_FUND', но это редко.
    return df[['SECID', 'SHORTNAME', 'LOTSIZE']].rename(columns={'SECID': 'ticker', 'SHORTNAME': 'short_name', 'LOTSIZE': 'lot_size'})

def get_daily_candles(ticker, days=MIN_DAYS_HISTORY):
    """
    Загружает дневные свечи для тикера.
    ISS API отдает свечи с датой в формате "YYYY-MM-DD".
    Возвращает DataFrame с колонками: 'open', 'close', 'high', 'low', 'volume', 'date'.
    """
    url = f"https://iss.moex.com/iss/engines/stock/markets/shares/securities/{ticker}/candles.json"
    params = {
        "interval": 24, # Дневной таймфрейм
        "iss.meta": "off",
        "iss.only": "candles",
        "candles.columns": "open,close,high,low,volume,begin"
    }
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        
        if 'candles' not in data or len(data['candles']['data']) == 0:
            return None
            
        df = pd.DataFrame(data['candles']['data'], columns=data['candles']['columns'])
        df['date'] = pd.to_datetime(df['begin'])
        df = df.sort_values('date', ascending=True)
        
        # Оставляем последние N дней, но если история меньше, берем всю
        return df.tail(days)
    except Exception as e:
        print(f"Error fetching candles for {ticker}: {e}")
        return None

def calculate_average_volume_rub(ticker_data, lot_size):
    """
    Рассчитывает средний объем в рублях за последние 20 дней.
    ticker_data: DataFrame с колонкой 'volume' (в лотах).
    lot_size: размер лота.
    """
    if ticker_data is None or len(ticker_data) < 20:
        return 0
    # Берем последние 20 свечей (исключая последнюю, которая может быть сегодняшней незавершенной, но API отдает только завершенные)
    last_20 = ticker_data.tail(20)
    avg_volume_lots = last_20['volume'].mean()
    # Цена закрытия для расчета объема в деньгах (берем среднюю за период)
    avg_close = last_20['close'].mean()
    avg_volume_rub = avg_volume_lots * lot_size * avg_close
    return avg_volume_rub