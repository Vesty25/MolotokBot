# dividend_gap_scanner.py
import logging
import pandas as pd
from datetime import datetime, timedelta
from config import (
    DG_DAYS_SINCE_CUTOFF, DG_MIN_GAP_PCT, DG_MIN_RECOVERY_PCT,
    DG_BLUE_CHIP_ONLY, BLUE_CHIPS, DIVIDEND_CUTOFF_DATES, TOP_LIMIT
)

logger = logging.getLogger(__name__)

def scan_dividend_gap(market_data):
    """
    Стратегия «Дивидендный разрыв» — закрытие гэпа.
    """
    candidates = []
    stats = {
        'total': len(market_data),
        'not_blue_chip': 0,
        'no_cutoff': 0,
        'no_data': 0,
        'no_gap': 0,
        'no_recovery': 0,
        'no_volume': 0,
        'passed': 0,
        'errors': 0
    }
    
    if not DIVIDEND_CUTOFF_DATES:
        logger.warning("💸 ДИВИДЕНДНЫЙ РАЗРЫВ: таблица отсечек пуста, стратегия пропущена")
        return [], stats
    
    today = datetime.now()
    
    for item in market_data:
        ticker = item['ticker']
        
        try:
            if DG_BLUE_CHIP_ONLY and ticker not in BLUE_CHIPS:
                stats['not_blue_chip'] += 1
                continue
            
            # Проверяем дату отсечки
            if ticker not in DIVIDEND_CUTOFF_DATES:
                stats['no_cutoff'] += 1
                continue
            
            cutoff_str = DIVIDEND_CUTOFF_DATES[ticker]
            cutoff_date = datetime.strptime(cutoff_str, '%Y-%m-%d')
            
            days_since = (today - cutoff_date).days
            if days_since < 0 or days_since > DG_DAYS_SINCE_CUTOFF:
                stats['no_cutoff'] += 1
                continue
            
            df = item['data']
            if df is None or len(df) < 60:
                stats['no_data'] += 1
                continue
            
            # Ищем свечу отсечки по дате
            cutoff_df = df[df['date'].dt.date == cutoff_date.date()]
            if cutoff_df.empty:
                stats['no_data'] += 1
                continue
            
            cutoff_idx = cutoff_df.index[0]
            idx_pos = df.index.get_loc(cutoff_idx)
            
            if idx_pos < 1:
                stats['no_data'] += 1
                continue
            
            prev_candle = df.iloc[idx_pos - 1]
            cutoff_candle = df.iloc[idx_pos]
            
            prev_close = float(prev_candle['close'])
            cutoff_close = float(cutoff_candle['close'])
            cutoff_low = float(cutoff_candle['low'])
            
            # Гэп вниз: close_отсечки < close_до_отсечки * 0.97
            gap_pct = (prev_close - cutoff_close) / prev_close * 100
            
            if gap_pct < DG_MIN_GAP_PCT:
                stats['no_gap'] += 1
                continue
            
            # Восстановление: цена выше минимума отсечки на 2%+
            current_close = float(df['close'].iloc[-1])
            recovery_pct = (current_close - cutoff_low) / cutoff_low * 100
            
            if recovery_pct < DG_MIN_RECOVERY_PCT:
                stats['no_recovery'] += 1
                continue
            
            # Объём стабилен: avg_volume_после >= 0.6 * avg_volume_до
            after_cutoff = df.iloc[idx_pos+1:]
            if len(after_cutoff) < 3:
                stats['no_volume'] += 1
                continue
            
            before_cutoff = df.iloc[:idx_pos].tail(20)
            if len(before_cutoff) < 5:
                stats['no_volume'] += 1
                continue
            
            avg_vol_after = float(after_cutoff['volume'].head(3).mean())
            avg_vol_before = float(before_cutoff['volume'].tail(20).mean())
            
            if avg_vol_before == 0 or avg_vol_after < 0.6 * avg_vol_before:
                stats['no_volume'] += 1
                continue
            
            # Score
            volume_ratio = avg_vol_after / avg_vol_before if avg_vol_before > 0 else 0
            score = round((gap_pct / 2) * volume_ratio, 2)
            
            candidates.append({
                'ticker': ticker,
                'short_name': item['short_name'],
                'score': score,
                'close': round(current_close, 2),
                'cutoff_days_ago': days_since,
                'gap_pct': round(gap_pct, 1),
                'recovery_pct': round(recovery_pct, 1)
            })
            
            stats['passed'] += 1
            
        except Exception as e:
            stats['errors'] += 1
            logger.error(f"Ошибка Дивидендный разрыв {ticker}: {e}")
            continue
    
    logger.info(f"\n📊 ИТОГИ ДИВИДЕНДНЫЙ РАЗРЫВ:")
    logger.info(f"   ❌ Не голубая фишка: {stats['not_blue_chip']}")
    logger.info(f"   ❌ Нет отсечки: {stats['no_cutoff']}")
    logger.info(f"   ❌ Нет гэпа: {stats['no_gap']}")
    logger.info(f"   ❌ Нет восстановления: {stats['no_recovery']}")
    logger.info(f"   ❌ Объём нестабилен: {stats['no_volume']}")
    logger.info(f"   ✅ Прошли: {stats['passed']}")
    
    candidates.sort(key=lambda x: x['score'], reverse=True)
    return candidates[:TOP_LIMIT], stats


def format_dividend_gap_report(candidates, stats, date_str, time_str):
    """Форматирует отчёт."""
    lines = [
        "💸 *ДИВИДЕНДНЫЙ РАЗРЫВ — закрытие гэпа*",
        f"📅 {date_str} | {time_str}",
        f"📊 Найдено: {stats['passed']}",
        ""
    ]
    
    if candidates:
        medals = ["🥇", "🥈", "🥉"] + ["  "] * 7
        for i, c in enumerate(candidates):
            lines.extend([
                f"{medals[i]} *{i+1}. {c['ticker']}* ({c['short_name']}) | Score: *{c['score']}*",
                f"   💰 {c['close']} ₽ | Отсечка: {c['cutoff_days_ago']} дн. назад | Гэп: -{c['gap_pct']}%",
                f"   📈 Восстановление: +{c['recovery_pct']}% от минимума",
                ""
            ])
        lines.append("💡 *Цель: закрытие гэпа полностью. Стоп: под минимум дня отсечки.*")
    else:
        lines.append("💸 *ДИВИДЕНДНЫЙ РАЗРЫВ*: сигналов не найдено.")
    
    return "\n".join(lines)
