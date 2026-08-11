# squeeze_scanner.py
import logging
import pandas as pd
from config import (
    SQUEEZE_BWINDOW, SQUEEZE_BW_THRESHOLD, SQUEEZE_RSI_MAX,
    SQUEEZE_BB_PERIOD, SQUEEZE_BB_STD, TOP_LIMIT
)

logger = logging.getLogger(__name__)

def scan_squeeze(market_data):
    """
    Стратегия «Сжатая пружина» — сжатие Bollinger Bands.
    """
    candidates = []
    stats = {
        'total': len(market_data),
        'no_data': 0,
        'no_squeeze': 0,
        'no_direction': 0,
        'no_rsi': 0,
        'no_volume': 0,
        'no_green': 0,
        'passed': 0,
        'errors': 0
    }
    
    for item in market_data:
        ticker = item['ticker']
        
        try:
            df = item['data']
            if df is None or len(df) < SQUEEZE_BWINDOW:
                stats['no_data'] += 1
                continue
            
            last = df.iloc[-1]
            
            close_p = float(last['close'])
            open_p = float(last['open'])
            volume = float(last['volume'])
            
            bb_middle = float(last['bb_middle'])
            bb_upper = float(last['bb_upper'])
            bb_lower = float(last['bb_lower'])
            bandwidth = float(last['bandwidth'])
            rsi = float(last['rsi_14'])
            avg_vol = float(last['avg_volume_20'])
            
            # Проверка наличия данных
            if pd.isna(bb_middle) or pd.isna(bandwidth):
                stats['no_data'] += 1
                continue
            
            # Фильтр 1: Сжатие (bandwidth сегодня ≤ min_bandwidth_60 * порог)
            bandwidth_60 = df['bandwidth'].tail(SQUEEZE_BWINDOW)
            min_bandwidth_60 = float(bandwidth_60.min())
            
            if pd.isna(min_bandwidth_60) or bandwidth > min_bandwidth_60 * SQUEEZE_BW_THRESHOLD:
                stats['no_squeeze'] += 1
                continue
            
            # Фильтр 2: Направление (close > BB_middle)
            if close_p <= bb_middle:
                stats['no_direction'] += 1
                continue
            
            # Фильтр 3: Не перекуплен (RSI < 65)
            if pd.isna(rsi) or rsi >= SQUEEZE_RSI_MAX:
                stats['no_rsi'] += 1
                continue
            
            # Фильтр 4: Объём
            if pd.isna(avg_vol) or avg_vol == 0 or volume <= avg_vol:
                stats['no_volume'] += 1
                continue
            
            # Фильтр 5: Зелёная свеча
            if close_p <= open_p:
                stats['no_green'] += 1
                continue
            
            # Все фильтры пройдены!
            bb_range = bb_upper - bb_middle
            if bb_range > 0:
                position = (close_p - bb_middle) / bb_range
            else:
                position = 0
            
            volume_ratio = volume / avg_vol
            score = round(position * volume_ratio * 10, 2)
            
            # Ширина в процентах
            bandwidth_pct = round(bandwidth * 100, 1)
            min_bandwidth_pct = round(min_bandwidth_60 * 100, 1)
            
            candidates.append({
                'ticker': item['ticker'],
                'short_name': item['short_name'],
                'score': score,
                'close': round(close_p, 2),
                'bb_upper': round(bb_upper, 2),
                'bb_lower': round(bb_lower, 2),
                'bandwidth_pct': bandwidth_pct,
                'min_bandwidth_pct': min_bandwidth_pct,
                'rsi': round(rsi, 1),
                'volume_ratio': round(volume_ratio, 1)
            })
            
            stats['passed'] += 1
            
        except Exception as e:
            stats['errors'] += 1
            logger.error(f"Ошибка Сжатая пружина {ticker}: {e}")
            continue
    
    # Итоговая статистика
    total_checked = stats['total'] - stats['no_data'] - stats['errors']
    sum_filters = (stats['no_squeeze'] + stats['no_direction'] + stats['no_rsi'] + 
                   stats['no_volume'] + stats['no_green'] + stats['passed'])
    
    logger.info(f"\n📊 ИТОГИ СЖАТАЯ ПРУЖИНА:")
    logger.info(f"   Всего: {stats['total']}, Проверено: {total_checked}")
    logger.info(f"   ❌ Нет сжатия: {stats['no_squeeze']}")
    logger.info(f"   ❌ Цена ниже SMA: {stats['no_direction']}")
    logger.info(f"   ❌ RSI высокий: {stats['no_rsi']}")
    logger.info(f"   ❌ Нет объёма: {stats['no_volume']}")
    logger.info(f"   ❌ Не зелёная: {stats['no_green']}")
    logger.info(f"   ✅ Прошли: {stats['passed']}")
    logger.info(f"   Ошибок: {stats['errors']}")
    
    if sum_filters != total_checked:
        logger.warning(f"⚠️ Расхождение: сумма={sum_filters}, проверено={total_checked}")
    
    candidates.sort(key=lambda x: x['score'], reverse=True)
    top_candidates = candidates[:TOP_LIMIT]
    
    logger.info(f"   Бумаг после фильтров: {len(candidates)}. В Telegram: {len(top_candidates)}")
    
    return top_candidates, stats


def format_squeeze_report(candidates, stats, date_str, time_str):
    """Форматирует отчёт по стратегии Сжатая пружина."""
    lines = [
        "🌀 *СЖАТАЯ ПРУЖИНА — сжатие Bollinger Bands*",
        f"📅 {date_str} | {time_str}",
        f"📊 Проанализировано: {stats['total']} | Найдено: {stats['passed']}",
        ""
    ]
    
    if candidates:
        medals = ["🥇", "🥈", "🥉"] + ["  "] * 7
        for i, c in enumerate(candidates):
            lines.extend([
                f"{medals[i]} *{i+1}. {c['ticker']}* ({c['short_name']}) | Score: *{c['score']}*",
                f"   💰 {c['close']} ₽ | BB: {c['bb_lower']} – {c['bb_upper']} (ширина {c['bandwidth_pct']}%, мин. {c['min_bandwidth_pct']}%)",
                f"   📈 RSI: {c['rsi']} | Объем: {c['volume_ratio']}x | Цена > SMA 20 ✅",
                ""
            ])
        lines.append("💡 *Вход: лимитная заявка у цены закрытия. Стоп: под BB_lower (-2%). Цель: BB_upper (+4–7%).*")
    else:
        lines.append("🌀 *СЖАТАЯ ПРУЖИНА*: сигналов не найдено.")
        lines.append(f"   (отсев: нет сжатия={stats['no_squeeze']}, цена ниже SMA={stats['no_direction']}, RSI высокий={stats['no_rsi']}, нет объёма={stats['no_volume']}, не зелёная={stats['no_green']})")
    
    return "\n".join(lines)
