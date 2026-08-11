# hammer_scanner.py
import pandas as pd
import logging
from config import (
    HAMMER_SHADOW_BODY_RATIO, HAMMER_MAX_UPPER_SHADOW,
    HAMMER_SUPPORT_PCT, HAMMER_MIN_BODY_PCT, HAMMER_MIN_SHADOW_PCT,
    TOP_LIMIT
)

logger = logging.getLogger(__name__)

def scan_hammer(market_data):
    """
    Стратегия «Молот» — разворот у поддержки.
    С подробным логированием.
    """
    candidates = []
    stats = {
        'total': len(market_data),
        'no_data': 0,
        'no_pattern': 0,
        'no_volume': 0,
        'no_support': 0,
        'passed': 0,
        'errors': 0
    }
    
    all_processed = 0
    
    for item in market_data:
        ticker = item['ticker']
        all_processed += 1
        
        try:
            df = item['data']
            if df is None or len(df) < 60:
                stats['no_data'] += 1
                continue
            
            last = df.iloc[-1]
            open_p = float(last['open'])
            close_p = float(last['close'])
            high_p = float(last['high'])
            low_p = float(last['low'])
            volume = float(last['volume'])
            
            # Бычья свеча
            if close_p <= open_p:
                stats['no_pattern'] += 1
                continue
            
            body = close_p - open_p
            if body == 0:
                stats['no_pattern'] += 1
                continue
            
            lower_shadow = min(open_p, close_p) - low_p
            upper_shadow = high_p - max(open_p, close_p)
            
            # Минимальное тело 0.5%
            if (body / close_p) * 100 < HAMMER_MIN_BODY_PCT:
                stats['no_pattern'] += 1
                continue
            
            # Минимальная тень 2%
            if (lower_shadow / close_p) * 100 < HAMMER_MIN_SHADOW_PCT:
                stats['no_pattern'] += 1
                continue
            
            # Геометрия молота
            if lower_shadow < HAMMER_SHADOW_BODY_RATIO * body:
                stats['no_pattern'] += 1
                continue
            
            # Маленькая верхняя тень
            if upper_shadow > HAMMER_MAX_UPPER_SHADOW * body:
                stats['no_pattern'] += 1
                continue
            
            # Уровень поддержки
            min_60 = item['support_60']
            support_bound = min_60 * (1 + HAMMER_SUPPORT_PCT / 100)
            if close_p > support_bound:
                stats['no_support'] += 1
                continue
            
            # Объём
            avg_vol = float(df['avg_volume_20'].iloc[-1])
            if pd.isna(avg_vol) or avg_vol == 0 or volume <= avg_vol:
                stats['no_volume'] += 1
                continue
            
            volume_ratio = volume / avg_vol
            score = round((lower_shadow / body) * volume_ratio, 2)
            
            candidates.append({
                'ticker': item['ticker'],
                'short_name': item['short_name'],
                'score': score,
                'close': round(close_p, 2),
                'support': round(min_60, 2),
                'body_pct': round((body / close_p) * 100, 1),
                'shadow_pct': round((lower_shadow / close_p) * 100, 1),
                'volume_ratio': round(volume_ratio, 1)
            })
            
            stats['passed'] += 1
            
        except Exception as e:
            stats['errors'] += 1
            continue
    
    total_checked = all_processed - stats['no_data'] - stats['errors']
    sum_filters = stats['no_pattern'] + stats['no_support'] + stats['no_volume'] + stats['passed']
    
    logger.info(f"\n📊 ИТОГИ МОЛОТ:")
    logger.info(f"   Проверено: {total_checked}")
    logger.info(f"   ❌ Нет паттерна: {stats['no_pattern']}")
    logger.info(f"   ❌ Нет поддержки: {stats['no_support']}")
    logger.info(f"   ❌ Нет объёма: {stats['no_volume']}")
    logger.info(f"   ✅ Прошли: {stats['passed']}")
    
    if sum_filters != total_checked:
        logger.warning(f"⚠️ Расхождение: сумма={sum_filters}, проверено={total_checked}")
    
    candidates.sort(key=lambda x: x['score'], reverse=True)
    top_candidates = candidates[:TOP_LIMIT]
    
    logger.info(f"   Бумаг после всех фильтров: {len(candidates)}")
    logger.info(f"   Отправлено в Telegram: {len(top_candidates)}")
    
    return top_candidates, stats


def format_hammer_report(candidates, stats, date_str, time_str):
    """Форматирует отчёт по стратегии Молот."""
    lines = [
        "🔨 *МОЛОТ — разворот у поддержки*",
        f"📅 {date_str} | {time_str}",
        f"📊 Проанализировано: {stats['total']} | Найдено: {stats['passed']}",
        ""
    ]
    
    if candidates:
        medals = ["🥇", "🥈", "🥉"] + ["  "] * 7
        for i, c in enumerate(candidates):
            lines.extend([
                f"{medals[i]} *{i+1}. {c['ticker']}* ({c['short_name']}) | Score: *{c['score']}*",
                f"   💰 {c['close']} ₽ | Тело: {c['body_pct']}% | Тень: {c['shadow_pct']}%",
                f"   📉 Поддержка: {c['support']} ₽ | Объем: {c['volume_ratio']}x",
                ""
            ])
        lines.append("💡 *Стоп-лосс -2%. Цель: ближайшее сопротивление.*")
    else:
        lines.append("🔨 *МОЛОТ*: сигналов не найдено.")
        lines.append(f"   (отсев: нет паттерна={stats['no_pattern']}, нет поддержки={stats['no_support']}, нет объёма={stats['no_volume']})")
    
    return "\n".join(lines)
