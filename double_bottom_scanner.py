# double_bottom_scanner.py
import logging
import numpy as np
import pandas as pd
from config import (
    DB_LOOKBACK, DB_SECOND_BOTTOM_WINDOW, DB_LEVEL_TOLERANCE,
    DB_MIN_REBOUND, DB_MID_PEAK_MIN, TOP_LIMIT
)

logger = logging.getLogger(__name__)

def scan_double_bottom(market_data):
    """
    Стратегия «Двойное дно» — разворотный паттерн.
    """
    candidates = []
    stats = {
        'total': len(market_data),
        'no_data': 0,
        'no_downtrend': 0,
        'no_first_bottom': 0,
        'no_mid_peak': 0,
        'no_second_bottom': 0,
        'no_level_match': 0,
        'no_reversal': 0,
        'no_volume': 0,
        'passed': 0,
        'errors': 0
    }
    
    for item in market_data:
        ticker = item['ticker']
        
        try:
            df = item['data']
            if df is None or len(df) < DB_LOOKBACK + 10:
                stats['no_data'] += 1
                continue
            
            last = df.iloc[-1]
            close_p = float(last['close'])
            open_p = float(last['open'])
            low_p = float(last['low'])
            volume = float(last['volume'])
            avg_vol = float(last['avg_volume_20'])
            
            # Фильтр 1: Нисходящий тренд (цена 20 дней назад > сегодня)
            if len(df) >= 21:
                close_20_ago = float(df['close'].iloc[-21])
                if close_20_ago <= close_p:
                    stats['no_downtrend'] += 1
                    continue
            else:
                stats['no_data'] += 1
                continue
            
            # Поиск первого дна (low_1) в диапазоне [-30, -10]
            first_bottom_window = df.iloc[-(DB_LOOKBACK+1):-11]
            if len(first_bottom_window) < 5:
                stats['no_first_bottom'] += 1
                continue
            
            low_1_idx = first_bottom_window['low'].idxmin()
            low_1 = float(df.loc[low_1_idx, 'low'])
            low_1_pos = len(df) - df.index.get_loc(low_1_idx) - 1  # Дней назад
            
            # Проверка отскока от первого дна: должен быть high > low_1 * 1.03 между low_1 и low_2
            after_first = df.loc[low_1_idx:].iloc[1:]  # После первого дна
            if len(after_first) < 3:
                stats['no_first_bottom'] += 1
                continue
            
            max_after_first = float(after_first['high'].max())
            if max_after_first < low_1 * (1 + DB_MIN_REBOUND):
                stats['no_first_bottom'] += 1
                continue
            
            # Поиск второго дна (low_2) в последние 5 дней
            second_bottom_window = df.tail(DB_SECOND_BOTTOM_WINDOW)
            low_2_idx = second_bottom_window['low'].idxmin()
            low_2 = float(df.loc[low_2_idx, 'low'])
            low_2_pos = len(df) - df.index.get_loc(low_2_idx) - 1
            
            # low_2 должен быть после low_1 (очевидно)
            if low_2_idx <= low_1_idx:
                stats['no_second_bottom'] += 1
                continue
            
            # Промежуточный пик между low_1 и low_2
            mid_section = df.loc[low_1_idx:low_2_idx]
            if len(mid_section) < 3:
                stats['no_mid_peak'] += 1
                continue
            
            high_mid = float(mid_section['high'].max())
            
            # Пик должен быть выше обоих минимумов на ≥5%
            if high_mid < low_1 * (1 + DB_MID_PEAK_MIN) or high_mid < low_2 * (1 + DB_MID_PEAK_MIN):
                stats['no_mid_peak'] += 1
                continue
            
            # Фильтр 2: Уровни совпадают (±3%)
            level_diff = abs(low_2 - low_1) / low_1
            if level_diff > DB_LEVEL_TOLERANCE:
                stats['no_level_match'] += 1
                continue
            
            # Фильтр 3: Второе дно выше или равно первому
            if low_2 < low_1:
                stats['no_second_bottom'] += 1
                continue
            
            # Фильтр 4: Разворотная свеча (зелёная, закрытие выше вчера)
            if close_p <= open_p:
                stats['no_reversal'] += 1
                continue
            
            if len(df) >= 2:
                prev_close = float(df['close'].iloc[-2])
                if close_p <= prev_close:
                    stats['no_reversal'] += 1
                    continue
            
            # Фильтр 5: Объём
            if pd.isna(avg_vol) or avg_vol == 0 or volume <= avg_vol:
                stats['no_volume'] += 1
                continue
            
            # Все фильтры пройдены!
            price_range = high_mid - low_2
            if price_range > 0:
                position = (close_p - low_2) / price_range
            else:
                position = 0
            
            volume_ratio = volume / avg_vol
            score = round(position * volume_ratio * 10, 2)
            
            candidates.append({
                'ticker': item['ticker'],
                'short_name': item['short_name'],
                'score': score,
                'close': round(close_p, 2),
                'low_1': round(low_1, 2),
                'low_1_days': low_1_pos,
                'low_2': round(low_2, 2),
                'low_2_days': low_2_pos,
                'level_match_pct': round(level_diff * 100, 1),
                'high_mid': round(high_mid, 2),
                'volume_ratio': round(volume_ratio, 1)
            })
            
            stats['passed'] += 1
            
        except Exception as e:
            stats['errors'] += 1
            logger.error(f"Ошибка Двойное дно {ticker}: {e}")
            continue
    
    # Итоговая статистика
    total_checked = stats['total'] - stats['no_data'] - stats['errors']
    sum_filters = (stats['no_downtrend'] + stats['no_first_bottom'] + stats['no_mid_peak'] + 
                   stats['no_second_bottom'] + stats['no_level_match'] + stats['no_reversal'] + 
                   stats['no_volume'] + stats['passed'])
    
    logger.info(f"\n📊 ИТОГИ ДВОЙНОЕ ДНО:")
    logger.info(f"   Всего: {stats['total']}, Проверено: {total_checked}")
    logger.info(f"   ❌ Нет тренда вниз: {stats['no_downtrend']}")
    logger.info(f"   ❌ Нет первого дна: {stats['no_first_bottom']}")
    logger.info(f"   ❌ Нет промежуточного пика: {stats['no_mid_peak']}")
    logger.info(f"   ❌ Нет второго дна: {stats['no_second_bottom']}")
    logger.info(f"   ❌ Уровни не совпали: {stats['no_level_match']}")
    logger.info(f"   ❌ Нет разворота: {stats['no_reversal']}")
    logger.info(f"   ❌ Нет объёма: {stats['no_volume']}")
    logger.info(f"   ✅ Прошли: {stats['passed']}")
    logger.info(f"   Ошибок: {stats['errors']}")
    
    if sum_filters != total_checked:
        logger.warning(f"⚠️ Расхождение: сумма={sum_filters}, проверено={total_checked}")
    
    candidates.sort(key=lambda x: x['score'], reverse=True)
    top_candidates = candidates[:TOP_LIMIT]
    
    logger.info(f"   Бумаг после фильтров: {len(candidates)}. В Telegram: {len(top_candidates)}")
    
    return top_candidates, stats


def format_double_bottom_report(candidates, stats, date_str, time_str):
    """Форматирует отчёт по стратегии Двойное дно."""
    lines = [
        "🏔️ *ДВОЙНОЕ ДНО — разворотный паттерн*",
        f"📅 {date_str} | {time_str}",
        f"📊 Проанализировано: {stats['total']} | Найдено: {stats['passed']}",
        ""
    ]
    
    if candidates:
        medals = ["🥇", "🥈", "🥉"] + ["  "] * 7
        for i, c in enumerate(candidates):
            lines.extend([
                f"{medals[i]} *{i+1}. {c['ticker']}* ({c['short_name']}) | Score: *{c['score']}*",
                f"   💰 {c['close']} ₽ | Дно 1: {c['low_1']} ({c['low_1_days']} дн. назад)",
                f"   📉 Дно 2: {c['low_2']} ({c['low_2_days']} дн. назад) | Совпадение: +{c['level_match_pct']}% ✅",
                f"   📈 Промежуточный пик: {c['high_mid']} | Объем: {c['volume_ratio']}x",
                ""
            ])
        lines.append("💡 *Вход: лимитная заявка у цены закрытия. Стоп: -2% под low_2. Цель: high_mid (+5–8%).*")
    else:
        lines.append("🏔️ *ДВОЙНОЕ ДНО*: сигналов не найдено.")
        lines.append(f"   (отсев: нет тренда вниз={stats['no_downtrend']}, нет первого дна={stats['no_first_bottom']}, нет пика={stats['no_mid_peak']}, нет второго дна={stats['no_second_bottom']}, уровень не совпал={stats['no_level_match']}, нет разворота={stats['no_reversal']}, нет объёма={stats['no_volume']})")
    
    return "\n".join(lines)
