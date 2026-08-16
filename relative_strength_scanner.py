# relative_strength_scanner.py
import logging
import pandas as pd
from config import (
    RS_MIN_MARKET_DROP, RS_MIN_OUTPERFORM_PCT, RS_MAX_DROP_ACT,
    RS_BLUE_CHIP_ONLY, BLUE_CHIPS, TOP_LIMIT
)

logger = logging.getLogger(__name__)

def scan_relative_strength(market_data, imoex_analysis):
    """
    Стратегия «Сильная бумага» — против падающего рынка.
    Работает только при падении рынка.
    """
    candidates = []
    stats = {
        'total': len(market_data),
        'market_drop': imoex_analysis.get('day_change_pct', 0),
        'no_market_drop': 0,
        'not_blue_chip': 0,
        'no_data': 0,
        'weaker_than_market': 0,
        'dropped_too_much': 0,
        'no_trend': 0,
        'no_volume': 0,
        'passed': 0,
        'errors': 0
    }
    
    # Если рынок не упал — стратегия не работает
    if not imoex_analysis.get('available', False):
        logger.warning("💪 СИЛЬНАЯ БУМАГА: IMOEX не загружен, стратегия пропущена")
        stats['no_market_drop'] = len(market_data)
        return [], stats
    
    market_change = imoex_analysis['day_change_pct']
    
    if market_change > -RS_MIN_MARKET_DROP:
        logger.info(f"💪 СИЛЬНАЯ БУМАГА: рынок не упал (изменение {market_change:.1f}%), стратегия не активна")
        stats['no_market_drop'] = len(market_data)
        return [], stats
    
    logger.info(f"💪 СИЛЬНАЯ БУМАГА: рынок упал на {market_change:.1f}%, ищем сильные бумаги...")
    
    for item in market_data:
        ticker = item['ticker']
        
        try:
            # Фильтр: только голубые фишки
            if RS_BLUE_CHIP_ONLY and ticker not in BLUE_CHIPS:
                stats['not_blue_chip'] += 1
                continue
            
            df = item['data']
            if df is None or len(df) < 60:
                stats['no_data'] += 1
                continue
            
            last = df.iloc[-1]
            prev = df.iloc[-2] if len(df) >= 2 else None
            
            if prev is None:
                stats['no_data'] += 1
                continue
            
            close_p = float(last['close'])
            prev_close = float(prev['close'])
            open_p = float(last['open'])
            volume = float(last['volume'])
            avg_vol = float(last['avg_volume_20'])
            ema_200 = float(last['ema_200'])
            
            # Изменение акции за день
            stock_change = (close_p - prev_close) / prev_close * 100
            
            # Фильтр: акция сильнее рынка
            min_required = market_change + RS_MIN_OUTPERFORM_PCT
            if stock_change < min_required:
                stats['weaker_than_market'] += 1
                continue
            
            # Фильтр: акция не падает слишком сильно
            if stock_change < RS_MAX_DROP_ACT:
                stats['dropped_too_much'] += 1
                continue
            
            # Фильтр: долгосрочный тренд (выше EMA 200)
            if pd.isna(ema_200) or close_p <= ema_200:
                stats['no_trend'] += 1
                continue
            
            # Фильтр: объём
            if pd.isna(avg_vol) or avg_vol == 0 or volume <= avg_vol:
                stats['no_volume'] += 1
                continue
            
            # Все фильтры пройдены
            volume_ratio = volume / avg_vol
            outperformance = stock_change - market_change
            score = round(outperformance * -1 * volume_ratio * 10, 2)
            
            candidates.append({
                'ticker': ticker,
                'short_name': item['short_name'],
                'score': score,
                'close': round(close_p, 2),
                'stock_change': round(stock_change, 1),
                'market_change': round(market_change, 1),
                'volume_ratio': round(volume_ratio, 1)
            })
            
            stats['passed'] += 1
            
        except Exception as e:
            stats['errors'] += 1
            logger.error(f"Ошибка Сильная бумага {ticker}: {e}")
            continue
    
    logger.info(f"\n📊 ИТОГИ СИЛЬНАЯ БУМАГА:")
    logger.info(f"   Рынок: {market_change:.1f}%")
    logger.info(f"   ❌ Не голубая фишка: {stats['not_blue_chip']}")
    logger.info(f"   ❌ Слабее рынка: {stats['weaker_than_market']}")
    logger.info(f"   ❌ Упала слишком сильно: {stats['dropped_too_much']}")
    logger.info(f"   ❌ Нет тренда: {stats['no_trend']}")
    logger.info(f"   ❌ Нет объёма: {stats['no_volume']}")
    logger.info(f"   ✅ Прошли: {stats['passed']}")
    
    candidates.sort(key=lambda x: x['score'], reverse=True)
    top_candidates = candidates[:TOP_LIMIT]
    
    return top_candidates, stats


def format_relative_strength_report(candidates, stats, date_str, time_str):
    """Форматирует отчёт."""
    lines = [
        "💪 *СИЛЬНАЯ БУМАГА — против падающего рынка*",
        f"📅 {date_str} | {time_str}",
        f"📊 IMOEX: {stats['market_drop']}% | Найдено: {stats['passed']}",
        ""
    ]
    
    if candidates:
        medals = ["🥇", "🥈", "🥉"] + ["  "] * 7
        for i, c in enumerate(candidates):
            lines.extend([
                f"{medals[i]} *{i+1}. {c['ticker']}* ({c['short_name']}) | Score: *{c['score']}*",
                f"   💰 {c['close']} ₽ | Изменение: {c['stock_change']}% (рынок: {c['market_change']}%)",
                f"   📈 Объем: {c['volume_ratio']}x | Тренд (EMA 200): ✅",
                ""
            ])
        lines.append("💡 *Вход при первом признаке разворота рынка. Стоп: -2% от входа. Цель: возврат к EMA 20 (+4–7%).*")
    else:
        lines.append("💪 *СИЛЬНАЯ БУМАГА*: сигналов не найдено.")
    
    return "\n".join(lines)
