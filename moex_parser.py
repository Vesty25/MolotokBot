# moex_parser.py
import requests
import pandas as pd
import logging
from datetime import datetime, timedelta
from config import MIN_DAYS_HISTORY

logger = logging.getLogger(__name__)

# Коды типов инструментов ISS API
VALID_SEC_TYPES = [1, 2]  # 1 = обыкновенная акция, 2 = привилегированная

def get_filtered_tickers():
    """
    Получает список ВСЕХ инструментов из TQBR с типом бумаги.
    Фильтрует по type=1 или type=2 (обыкновенные и привилегированные акции).
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
        
        # Показываем распределение по типам (цифровые коды)
        if 'sec_type' in df.columns:
            type_counts = df['sec_type'].value_counts().sort_index()
            logger.info(f"📋 Распределение по кодам типа (SECTYPE):")
            for sec_type, count in type_counts.items():
                type_name = get_type_name(sec_type)
                logger.info(f"   Код {sec_type} ({type_name}): {count}")
        
        # Показываем первые 10 SECID с их типами
        logger.info(f"\n🔝 Первые 10 SECID в списке:")
        for i, row in df.head(10).iterrows():
            type_name = get_type_name(row['sec_type'])
            logger.info(f"   {i+1}. {row['ticker']} ({row['short_name']}) | type={row['sec_type']} ({type_name})")
        
        # Ищем SBER в списке
        sber_row = df[df['ticker'] == 'SBER']
        if not sber_row.empty:
            sber_type = sber_row.iloc[0]['sec_type']
            sber_type_name = get_type_name(sber_type)
            logger.info(f"\n🔍 SBER найден в списке. Тип: {sber_type} ({sber_type_name})")
            
            # Проверяем, пройдет ли SBER фильтр
            if sber_type in VALID_SEC_TYPES:
                logger.info(f"✅ SBER ПРОЙДЕТ фильтр (тип {sber_type} входит в {VALID_SEC_TYPES})")
            else:
                logger.warning(f"⚠️ SBER НЕ ПРОЙДЕТ фильтр (тип {sber_type} не входит в {VALID_SEC_TYPES})")
        else:
            logger.warning("⚠️ SBER не найден в списке TQBR!")
        
        # ДИАГНОСТИКА 2: Фильтр по типу (только коды 1 и 2)
        mask_valid = df['sec_type'].isin(VALID_SEC_TYPES)
        df_filtered = df[mask_valid].copy()
        df_removed = df[~mask_valid]
        
        removed_by_type = len(df_removed)
        passed_filter = len(df_filtered)
        
        logger.info(f"\n🔍 ФИЛЬТР ПО ТИПУ (только коды {VALID_SEC_TYPES}):")
        logger.info(f"   До фильтра: {total_tickers}")
        logger.info(f"   Прошло фильтр: {passed_filter}")
        logger.info(f"   Удалено: {removed_by_type}")
        
        # Показываем примеры удаленных
        if len(df_removed) > 0:
            removed_types = df_removed['sec_type'].value_counts().sort_index()
            logger.info(f"   Типы удаленных инструментов:")
            for rtype, count in removed_types.items():
                type_name = get_type_name(rtype)
                logger.info(f"      Код {rtype} ({type_name}): {count}")
            
            # Примеры удаленных
            removed_examples = df_removed.head(5)[['ticker', 'short_name', 'sec_type']]
            logger.info(f"   Примеры удаленных:")
            for _, row in removed_examples.iterrows():
                type_name = get_type_name(row['sec_type'])
                logger.info(f"      {row['ticker']} ({row['short_name']}) | type={row['sec_type']} ({type_name})")
        
        # ДИАГНОСТИКА 3: Примеры ПРОШЕДШИХ фильтр
        if passed_filter > 0:
            passed_examples = df_filtered.head(5)[['ticker', 'short_name', 'sec_type']]
            logger.info(f"\n✅ Примеры ПРОШЕДШИХ фильтр (первые 5):")
            for _, row in passed_examples.iterrows():
                type_name = get_type_name(row['sec_type'])
                logger.info(f"   {row['ticker']} ({row['short_name']}) | type={row['sec_type']} ({type_name})")
            
            # Проверяем наличие ключевых тикеров
            key_tickers = ['SBER', 'LKOH', 'GAZP', 'VTBR', 'ROSN']
            found_key = df_filtered[df_filtered['ticker'].isin(key_tickers)]
            if not found_key.empty:
                logger.info(f"\n🔑 Ключевые тикеры, прошедшие фильтр:")
                for _, row in found_key.iterrows():
                    logger.info(f"   {row['ticker']} ({row['short_name']})")
        else:
            logger.error("❌ НИ ОДНА БУМАГА НЕ ПРОШЛА ФИЛЬТР ПО ТИПУ!")
            logger.error("❌ Проверьте коды SECTYPE в ответе API")
        
        logger.info(f"\n✅ ИТОГО после фильтра типа: {passed_filter} бумаг")
        logger.info("=" * 60)
        
        return df_filtered[['ticker', 'short_name', 'lot_size', 'sec_type']]
        
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Ошибка сети при загрузке инструментов: {e}")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {e}", exc_info=True)
        return pd.DataFrame()


def get_type_name(sec_type):
    """
    Возвращает человекочитаемое название типа инструмента по коду.
    """
    type_names = {
        1: 'Обыкновенная акция',
        2: 'Привилегированная акция',
        'A': 'ETF/БПИФ',
        'B': 'Облигация',
        'J': 'Нота',
        '9': 'ПИФ',
        'D': 'Депозитарная расписка'
    }
    
    # Обработка разных типов данных
    try:
        code = int(sec_type)
        return type_names.get(code, f'Неизвестный тип ({sec_type})')
    except (ValueError, TypeError):
        return type_names.get(str(sec_type), f'Неизвестный тип ({sec_type})')


def diagnose_sber_candles():
    """
    ДИАГНОСТИКА: Загружает свечи SBER и выводит подробную информацию.
    """
    logger.info("\n" + "=" * 60)
    logger.info("🔍 ДИАГНОСТИКА: Загрузка свечей SBER")
    
    ticker = "SBER"
    
    # Устанавливаем даты: за год до сегодня и сегодня
    today = datetime.now()
    one_year_ago = today - timedelta(days=365)
    
    url = f"https://iss.moex.com/iss/engines/stock/markets/shares/securities/{ticker}/candles.json"
    params = {
        "interval": 24,
        "iss.meta": "off",
        "iss.only": "candles",
        "candles.columns": "open,close,high,low,volume,begin",
        "from": one_year_ago.strftime("%Y-%m-%d"),
        "till": today.strftime("%Y-%m-%d")
    }
    
    logger.info(f"URL запроса: {url}")
    logger.info(f"Параметры: interval=24, from={params['from']}, till={params['till']}")
    
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
            
            # Проверяем, сколько свечей будет доступно для анализа
            recent_candles = df.tail(60)
            logger.info(f"📊 Свечей за последние 60 дней: {len(recent_candles)}")
            
            # Последняя свеча подробно
            last = df.iloc[-1]
            logger.info(f"\n📈 Последняя свеча SBER:")
            logger.info(f"   Дата: {last.get('begin', 'Н/Д')}")
            logger.info(f"   Open: {last.get('open', 'Н/Д')}")
            logger.info(f"   Close: {last.get('close', 'Н/Д')}")
            logger.info(f"   High: {last.get('high', 'Н/Д')}")
            logger.info(f"   Low: {last.get('low', 'Н/Д')}")
            logger.info(f"   Volume (лоты): {last.get('volume', 'Н/Д')}")
            
            # Проверяем актуальность данных
            try:
                last_date_dt = pd.to_datetime(last_date)
                days_ago = (datetime.now() - last_date_dt).days
                if days_ago > 3:
                    logger.warning(f"⚠️ Последняя свеча {days_ago} дней назад!")
                else:
                    logger.info(f"✅ Свежая свеча ({days_ago} дн. назад)")
            except:
                pass
        
        # Проверяем, хватает ли данных для анализа
        if total_candles < 60:
            logger.warning(f"⚠️ Недостаточно свечей для анализа! Нужно 60, есть {total_candles}")
        else:
            logger.info(f"✅ Достаточно свечей для анализа (60+): {total_candles}")
        
        # Анализ объемов
        if total_candles >= 20:
            last_20 = df.tail(20)
            avg_close = last_20['close'].astype(float).mean()
            avg_volume_lots = last_20['volume'].astype(float).mean()
            
            # Размер лота SBER = 10
            sber_lot = 10
            avg_volume_rub = avg_volume_lots * sber_lot * avg_close
            
            logger.info(f"\n💰 Анализ ликвидности SBER:")
            logger.info(f"   Средняя цена за 20 дней: {avg_close:.2f} ₽")
            logger.info(f"   Средний объем: {avg_volume_lots:,.0f} лотов")
            logger.info(f"   Средний объем в рублях: {avg_volume_rub:,.0f} ₽")
            logger.info(f"   Порог ликвидности: 10,000,000 ₽")
            
            if avg_volume_rub >= 10_000_000:
                logger.info(f"   ✅ SBER ликвиден и пройдет фильтр")
            else:
                logger.warning(f"   ⚠️ SBER НЕ пройдет фильтр объема!")
        
        logger.info("=" * 60 + "\n")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Ошибка сети при загрузке свечей SBER: {e}")
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при загрузке SBER: {e}", exc_info=True)


def get_daily_candles(ticker, days=MIN_DAYS_HISTORY):
    """
    Загружает дневные свечи для указанного тикера.
    Запрашивает данные за последний год, но возвращает только последние N дней.
    """
    today = datetime.now()
    one_year_ago = today - timedelta(days=365)
    
    url = f"https://iss.moex.com/iss/engines/stock/markets/shares/securities/{ticker}/candles.json"
    params = {
        "interval": 24,
        "iss.meta": "off",
        "iss.only": "candles",
        "candles.columns": "open,close,high,low,volume,begin",
        "from": one_year_ago.strftime("%Y-%m-%d"),
        "till": today.strftime("%Y-%m-%d")
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
        
        # Возвращаем последние N дней (60 по умолчанию)
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
    daily_volumes_rub = last_20['volume'].astype(float) * lot_size * last_20['close'].astype(float)
    avg_volume_rub = daily_volumes_rub.mean()
    
    return avg_volume_rub


def is_valid_share_type(sec_type):
    """
    Проверяет, является ли бумага обыкновенной (1) или привилегированной (2) акцией.
    """
    try:
        code = int(sec_type)
        return code in VALID_SEC_TYPES
    except (ValueError, TypeError):
        return False
