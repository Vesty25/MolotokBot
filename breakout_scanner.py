# breakout_scanner.py
import logging
import random
import numpy as np
import pandas as pd
from config import BREAKOUT_RANGE_PCT, BREAKOUT_VOLUME_RATIO, BREAKOUT_LOOKBACK, TOP_LIMIT

logger = logging.getLogger(__name__)

def scan_breakout(market_data):
    """
    Стратегия «Пробой тишины» — выход из боковика.
    С подробным логированием по каждому фильтру.
    """
    candidates = []
    stats = {
        'total': len(market_data),
        'no_data': 0,
        'no_trend': 0,
        'no_range': 0,
        'no_breakout': 0,
        'no_green': 0,
        'no_volume': 0,
        'passed': 0,
        'errors': 0
    }
    
    # Для диагностики случайной бумаги
    debug_ticker = None
    debug_data = {}
    
    # Выбираем случайную бумагу для детальной диагностики
    if len(market_data) > 0:
        debug_item = random.choice(market_data)
        debug_ticker = debug_item['ticker']
        logger.info(f"🔍 ДИАГНОСТИКА ПРОБОЯ: случайная бумага {debug_ticker} ({debug_item['short_name']})")
    
    for item in market_data:
        ticker = item['ticker']
        
        try:
            df = item['data']
            if df is None or len(df) < BREAKOUT_LOOKBACK + 1:
                stats['no_data'] += 1
                if ticker == debug_ticker:
                    logger.info(f"   {ticker}: ❌ нет данных (<{BREAKOUT_LOOKBACK+1} свечей)")
                continue
            
            last = df.iloc[-1]
            close_p = float(last['close'])
            open_p = float(last['open'])
            volume = float(last['volume'])
            ema_50 = float(last['ema_50'])
            
            # Данные за последние 15 дней (без сегодня)
            prev_15 = df.iloc[-(BREAKOUT_LOOKBACK+1):-1]
            if len(prev_15) < BREAKOUT_LOOKBACK:
                stats['no_data'] += 1
                continue
            
            max_high_15 = float(prev_15['high'].max())
            avg_vol_15 = float(prev_15['volume'].mean())
            amplitudes = (prev_15['high'] - prev_15['low']) / prev_15['close']
            avg_amplitude = float(amplitudes.mean()) * 100
            
            # Собираем диагностику для случайной бумаги
            if ticker == debug_ticker:
                debug_data = {
                    'ticker': ticker,
                    'close': close_p,
                    'open': open_p,
                    'ema_50': ema_50,
                    'max_high_15': max_high_15,
                    'avg_amplitude': avg_amplitude,
                    'amplitude_threshold': BREAKOUT_RANGE_PCT,
                    'volume': volume,
                    'avg_vol_15': avg_vol_15,
                    'volume_threshold': BREAKOUT_VOLUME_RATIO * avg_vol_15,
                    'filters': {}
                }
            
            # Фильтр 1: Тренд (close > EMA 50)
            if pd.isna(ema_50) or close_p <= ema_50:
                stats['no_trend'] += 1
                if ticker == debug_ticker:
                    debug_data['filters']['1_trend'] = False
                    logger.info(f"   {ticker}: ❌ тренд (close={close_p:.2f} <= EMA50={ema_50:.2f})")
                continue
            elif ticker == debug_ticker:
                debug_data['filters']['1_trend'] = True
            
            # Фильтр 2: Сужение диапазона (амплитуда < порога)
            if avg_amplitude > BREAKOUT_RANGE_PCT:
                stats['no_range'] += 1
                if ticker == debug_ticker:
                    debug_data['filters']['2_range'] = False
                    logger.info(f"   {ticker}: ❌ диапазон (ампл={avg_amplitude:.1f}% > {BREAKOUT_RANGE_PCT}%)")
                continue
            elif ticker == debug_ticker:
                debug_data['filters']['2_range'] = True
            
            # Фильтр 3: Пробой (close > max_high_15)
            if close_p <= max_high_15:
                stats['no_breakout'] += 1
                if ticker == debug_ticker:
                    debug_data['filters']['3_breakout'] = False
                    logger.info(f"   {ticker}: ❌ пробой (close={close_p:.2f} <= max_high_15={max_high_15:.2f})")
                continue
            elif ticker == debug_ticker:
                debug_data['filters']['3_breakout'] = True
            
            # Фильтр 4: Зелёная свеча
            if close_p <= open_p:
                stats['no_green'] += 1
                if ticker == debug_ticker:
                    debug_data['filters']['4_green'] = False
                    logger.info(f"   {ticker}: ❌ не зелёная (close={close_p:.2f} <= open={open_p:.2f})")
                continue
            elif ticker == debug_ticker:
                debug_data['filters']['4_green'] = True
            
            # Фильтр 5: Объём (volume > порог * avg_vol_15)
            vol_threshold = BREAKOUT_VOLUME_RATIO * avg_vol_15
            if avg_vol_15 == 0 or volume < vol_threshold:
                stats['no_volume'] += 1
                if ticker == debug_ticker:
                    debug_data['filters']['5_volume'] = False
                    logger.info(f"   {ticker}: ❌ объём ({volume:.0f} < {vol_threshold:.0f})")
                continue
            elif ticker == debug_ticker:
                debug_data['filters']['5_volume'] = True
            
            # Все фильтры пройдены!
            breakout_pct = (close_p / max_high_15 - 1) * 100
            score = round(breakout_pct * (volume / avg_vol_15), 2)
            
            candidates.append({
                'ticker': item['ticker'],
                'short_name': item['short_name'],
                'score': score,
                'close': round(close_p, 2),
                'breakout_level': round(max_high_15, 2),
                'breakout_pct': round(breakout_pct, 1),
                'range_low': round(float(prev_15['low'].min()), 2),
                'range_high': round(max_high_15, 2),
                'amplitude': round(avg_amplitude, 1),
                'volume_ratio': round(volume / avg_vol_15, 1),
                'trend_ok': True
            })
            
            stats['passed'] += 1
            
            if ticker == debug_ticker:
                debug_data['filters']['6_passed'] = True
                debug_data['score'] = score
                logger.info(f"   {ticker}: ✅ ПРОШЁЛ! Score={score}")
            
        except Exception as e:
            stats['errors'] += 1
            logger.error(f"Ошибка Пробой {ticker}: {e}")
            continue
    
    # Вывод детальной диагностики по случайной бумаге
    if debug_ticker and debug_data:
        logger.info(f"\n📊 Детальный разбор {debug_ticker}:")
        logger.info(f"   Цена: {debug_data.get('close', 'N/A')}")
        logger.info(f"   EMA 50: {debug_data.get('ema_50', 'N/A')}")
        logger.info(f"   Max High 15: {debug_data.get('max_high_15', 'N/A')}")
        logger.info(f"   Средняя амплитуда: {debug_data.get('avg_amplitude', 'N/A')}% (порог: {BREAKOUT_RANGE_PCT}%)")
        logger.info(f"   Объём сегодня: {debug_data.get('volume', 'N/A')}")
        logger.info(f"   Средний объём 15: {debug_data.get('avg_vol_15', 'N/A')}")
        logger.info(f"   Порог объёма: {debug_data.get('volume_threshold', 'N/A')}")
        logger.info(f"   Результаты фильтров:")
        for filter_name, result in debug_data.get('filters', {}).items():
            status = "✅" if result else "❌"
            logger.info(f"      {status} {filter_name}")
    
    # Итоговая статистика
    total_checked = stats['total'] - stats['no_data'] - stats['errors']
    sum_filters = stats['no_trend'] + stats['no_range'] + stats['no_breakout'] + stats['no_green'] + stats['no_volume'] + stats['passed']
    
    logger.info(f"\n📊 ИТОГИ ПРОБОЙ ТИШИНЫ:")
    logger.info(f"   Всего бумаг: {stats['total']}")
    logger.info(f"   Проверено: {total_checked}")
    logger.info(f"   Отсев по фильтрам:")
    logger.info(f"      ❌ Нет тренда (close ≤ EMA50): {stats['no_trend']}")
    logger.info(f"      ❌ Не сузился (ампл > {BREAKOUT_RANGE_PCT}%): {stats['no_range']}")
    logger.info(f"      ❌ Нет пробоя (close ≤ max_high_15): {stats['no_breakout']}")
    logger.info(f"      ❌ Не зелёная свеча: {stats['no_green']}")
    logger.info(f"      ❌ Нет объёма: {stats['no_volume']}")
    logger.info(f"      ✅ Прошли все фильтры: {stats['passed']}")
    logger.info(f"   Сумма проверок: {sum_filters} (должна совпадать с {total_checked})")
    logger.info(f"   Ошибок: {stats['errors']}")
    
    # Проверка сходимости
    if sum_filters != total_checked:
        logger.warning(f"⚠️ Расхождение в подсчётах! Сумма={sum_filters}, проверено={total_checked}")
    
    # Сортировка и ограничение
    candidates.sort(key=lambda x: x['score'], reverse=True)
    top_candidates = candidates[:TOP_LIMIT]
    
    logger.info(f"   Бумаг после всех фильтров: {len(candidates)}")
    logger.info(f"   Отсортировано по Score. Отправлено в Telegram: {len(top_candidates)}")
    
    return top_candidates, stats


def format_breakout_report(candidates, stats, date_str, time_str):
    """Форматирует отчёт по стратегии Пробой тишины."""
    lines = [
        "🚀 *ПРОБОЙ ТИШИНЫ — выход из боковика*",
        f"📅 {date_str} | {time_str}",
        f"📊 Проанализировано: {stats['total']} | Найдено: {stats['passed']}",
        ""
    ]
    
    if candidates:
        medals = ["🥇", "🥈", "🥉"] + ["  "] * 7
        for i, c in enumerate(candidates):
            lines.extend([
                f"{medals[i]} *{i+1}. {c['ticker']}* ({c['short_name']}) | Score: *{c['score']}*",
                f"   💰 {c['close']} ₽ | Пробой: {c['breakout_level']} ₽ (+{c['breakout_pct']}%)",
                f"   📊 Диапазон 15 дн: {c['range_low']} – {c['range_high']} (ампл. {c['amplitude']}%)",
                f"   📈 Объем: {c['volume_ratio']}x | Тренд (EMA 50): ✅",
                ""
            ])
        lines.append("💡 *Вход: лимитная заявка у уровня пробоя. Стоп: под середину бывшего боковика (-1.5%). Цель: +5–8%.*")
    else:
        lines.append("🚀 *ПРОБОЙ ТИШИНЫ*: сигналов не найдено.")
        lines.append(f"   (отсев: нет тренда={stats['no_trend']}, не сузился={stats['no_range']}, нет пробоя={stats['no_breakout']}, нет зелёной={stats['no_green']}, нет объёма={stats['no_volume']})")
    
    return "\n".join(lines)
