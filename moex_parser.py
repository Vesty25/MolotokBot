# moex_parser.py
import requests
import pandas as pd
import logging
from config import MIN_DAYS_HISTORY

logger = logging.getLogger(__name__)

def get_filtered_tickers():
    """
    Получает список ВСЕХ инструментов из TQBR с типом бумаги.
    С подробной диагностикой каждого этапа.
    """
    url = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"
    params = {
        "iss.meta": "off",
        "iss.only": "securities",
        "securities.columns": "SECID,SHORTNAME,LOTSIZE,SECTYPE"
    }
    
    try:
        logger.info("=" * 60)
        logger.info("🔍 ДИАГНОСТИКА: Загрузка списка инструментов TQBR")
        logger.info(f"URL: {url}")
        
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        if 'securities' not in data or 'data' not in data['securities']:
            logger.error("❌ Ошибка: Нет данных 'securities' в ответе API")
            logger.error(f"Ключи в ответе: {list(data.keys())}")
            return pd.DataFrame()
        
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
        
        # ДИАГНОСТИКА 1: Общая информация
        total_tickers = len(df)
        logger.info(f"📊 ВСЕГО получено инструментов: {total_tickers}")
        
        # Показываем распределение по типам
        if 'sec_type' in df.columns:
            type_counts = df['sec_type'].value_counts()
            logger.info(f"📋 Распределение по типам:")
            for sec_type, count in type_counts.head(10).items():
                logger.info(f"   {sec_type}: {count}")
        
        # Показываем первые 5 SECID
        first_5 = df['ticker'].head(5).tolist()
        first_5_names = df['short_name'].head(5).tolist()
        logger.info(f"🔝 Первые 5 SECID: {first_5}")
        logger.info(f"🔝 Их названия: {first_5_names}")
        
        # Ищем SBER в списке
        sber_row = df[df['ticker'] == 'SBER']
        if not sber_row.empty:
            sber_type = sber_row.iloc[0]['sec_type']
            logger.info(f"🔍 SBER найден в списке. Тип: {sber_type}")
        else:
            logger.warning("⚠️ SBER не найден в списке TQBR!")
        
        # ДИАГНОСТИКА 2: Фильтр по типу
        valid_types = ['common_share', 'preferred_share']
        mask_valid = df['sec_type'].str.lower().isin(valid_types)
        df_filtered = df[mask_valid].copy()
        
        removed_by_type = total_tickers - len(df_filtered)
        logger.info(f"\n🔍 ФИЛЬТР ПО ТИПУ (common_share, preferred_share):")
        logger.info(f"   До фильтра: {total_tickers}")
        logger.info(f"   После фильтра: {len(df_filtered)}")
        logger.info(f"   Удалено (не акции): {removed_by_type}")
        
        # Показываем примеры удаленных
        removed = df[~mask_valid]
        if len(removed) > 0:
            removed_types = removed['sec_type'].value_counts()
            logger.info(f"   Типы удаленных инструментов:")
            for rtype, count in removed_types.head(5).items():
                logger.info(f"      {rtype}: {count}")
        
        logger.info(f"✅ ИТОГО после фильтра типа: {len(df_filtered)} бумаг")
        logger.info("=" * 60)
        
        return df_filtered[['ticker', 'short_name', 'lot_size', 'sec_type']]
        
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Ошибка сети при загрузке инструментов: {e}")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {e}", exc_info=True)
        return pd.DataFrame()


def diagnose_sber_candles():
    """
    ДИАГНОСТИКА: Загружает свечи SBER и выводит подробную информацию.
    """
    logger.info("\n" + "=" * 60)
    logger.info("🔍 ДИАГНОСТИКА: Загрузка свечей SBER")
    
    ticker = "SBER"
    url = f"https://iss.moex.com/iss/engines/stock/markets/shares/securities/{ticker}/candles.json"
    params = {
        "interval": 24,
        "iss.meta": "off",
        "iss.only": "candles",
        "candles.columns": "open,close,high,low,volume,begin"
    }
    
    logger.info(f"URL запроса: {url}")
    logger.info(f"Параметры: {params}")
    
    try:
        resp = requests.get(url, params=params, timeout=15)
        logger.info(f"HTTP статус: {resp.status_code}")
        
        if resp.status_code != 200:
            logger.error(f"❌ Ошибка HTTP: {resp.status_code}")
            logger.error(f"Тело ответа: {resp.text[:500]}")
            return
        
        data = resp.json()
        
        # Проверяем структуру ответа
        if 'candles' not in data:
            logger.error("❌ Ключ 'candles' отсутствует в ответе")
            logger.error(f"Ключи в ответе: {list(data.keys())}")
            return
        
        candles_data = data['candles']
        logger.info(f"Ключи в candles: {list(candles_data.keys())}")
        
        if 'data' not in candles_data or len(candles_data['data']) == 0:
            logger.error("❌ Нет данных свечей (пустой массив data)")
            return
        
        # Преобразуем в DataFrame
        df = pd.DataFrame(
            candles_data['data'],
            columns=candles_data['columns']
        )
        
        total_candles = len(df)
        logger.info(f"📊 Всего получено свечей: {total_candles}")
        
        if total_candles > 0:
            # Первая и последняя даты
            first_date = df['begin'].iloc[0] if 'begin' in df.columns else "Н/Д"
            last_date = df['begin'].iloc[-1] if 'begin' in df.columns else "Н/Д"
            
            logger.info(f"📅 Первая свеча: {first_date}")
            logger.info(f"📅 Последняя свеча: {last_date}")
            
            # Последняя свеча подробно
            last = df.iloc[-1]
            logger.info(f"📈 Последняя свеча SBER:")
            logger.info(f"   Open: {last.get('open', 'Н/Д')}")
            logger.info(f"   Close: {last.get('close', 'Н/Д')}")
            logger.info(f"   High: {last.get('high', 'Н/Д')}")
            logger.info(f"   Low: {last.get('low', 'Н/Д')}")
            logger.info(f"   Volume: {last.get('volume', 'Н/Д')}")
            
            # Проверяем, что последняя свеча не старше 3 дней
            from datetime import datetime, timedelta
            try:
                last_date_dt = pd.to_datetime(last_date)
                days_ago = (datetime.now() - last_date_dt).days
                if days_ago > 3:
                    logger.warning(f"⚠️ Последняя свеча {days_ago} дней назад. Возможно, данные не обновляются!")
                else:
                    logger.info(f"✅ Свежая свеча ({days_ago} дн. назад)")
            except:
                pass
        
        # Проверяем, хватает ли данных для анализа
        if total_candles < 60:
            logger.warning(f"⚠️ Недостаточно свечей для анализа! Нужно 60, есть {total_candles}")
        else:
            logger.info(f"✅ Достаточно свечей для анализа (60+): {total_candles}")
        
        logger.info("=" * 60 + "\n")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Ошибка сети при загрузке свечей SBER: {e}")
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при загрузке SBER: {e}", exc_info=True)


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


def is_valid_share_type(sec_type):
    """
    Проверяет, является ли бумага обыкновенной или привилегированной акцией.
    """
    if not sec_type:
        return False
    
    sec_type_lower = str(sec_type).lower()
    valid_types = ['common_share', 'preferred_share']
    return sec_type_lower in valid_types
