# mean_reversion_scanner.py
import logging
import pandas as pd
from config import MR_MIN_DEVIATION_PCT, MR_RSI_MAX, MR_BLUE_CHIP_ONLY, BLUE_CHIPS, TOP_LIMIT

logger = logging.getLogger(__name__)

def scan_mean_reversion(market_data):
    """
    Стратегия «Возврат к EMA 20» — перепроданность голубой фишки.
    """
    candidates = []
    stats = {
        'total': len(market_data),
        'not_blue_chip': 0,
        'no_data': 0,
        'no_deviation': 0,
        'no_rsi': 0,
        'no_reversal': 0,
        'no_volume': 0,
        'passed': 0,
        'errors': 0
    }
    
    for item in market_data:
        ticker = item['ticker']
        
        try:
            if MR_BLUE_CHIP_ONLY and ticker not in BLUE_CHIPS:
                stats['not_blue_chip'] += 1
                continue
            
            df = item['data']
            if df is None or len(df) < 60:
                stats['no_data'] += 1
                continue
            
            last = df.iloc[-1]
            
            close_p = float(last['close'])
            open_p = float(last['open'])
            volume = float(last['volume'])
            ema_20 = float(last['ema_20'])
            rsi = float(last['rsi_14'])
            avg_vol = float(last['avg_volume_20'])
            
            # Отклонение от EMA 20
            if pd.isna(ema_20) or ema_20 == 0:
                stats['no_data'] += 1
                continue
            
            deviation_pct = (ema_20 - close_p) / ema_20 * 100
            
            # Фильтр: отклонение >= 7%
            if deviation_pct < MR_MIN_DEVIATION_PCT:
                stats['no_deviation'] += 1
                continue
            
            # Фильтр: RSI < 35
            if pd.isna(rsi) or rsi >= MR_RSI_MAX:
                stats['no_rsi'] += 1
                continue
            
            # Фильтр: зелёная свеча
            if close_p <= open_p:
                stats['no_reversal'] += 1
                continue
            
            # Фильтр: объём
            if pd.isna(avg_vol) or avg_vol == 0 or volume <= avg_vol:
                stats['no_volume'] += 1
                continue
            
            # Все фильтры пройдены
            volume_ratio = volume / avg_vol
            score = round(deviation_pct * volume_ratio * 5, 2)
            
            candidates.append({
                'ticker': ticker,
                'short_name': item['short_name'],
                'score': score,
                'close': round(close_p, 2),
                'ema_20': round(ema_20, 2),
                'deviation_pct': round(deviation_pct, 1),
                'rsi': round(rsi, 1),
                'volume_ratio': round(volume_ratio, 1)
            })
            
            stats['passed'] += 1
            
        except Exception as e:
            stats['errors'] += 1
            logger.error(f"Ошибка Возврат к EMA 20 {ticker}: {e}")
            continue
    
    logger.info(f"\n📊 ИТОГИ ВОЗВРАТ К EMA 20:")
    logger.info(f"   ❌ Не голубая фишка: {stats['not_blue_chip']}")
    logger.info(f"   ❌ Нет отклонения: {stats['no_deviation']}")
    logger.info(f"   ❌ RSI не низкий: {stats['no_rsi']}")
    logger.info(f"   ❌ Нет разворота: {stats['no_reversal']}")
    logger.info(f"   ❌ Нет объёма: {stats['no_volume']}")
    logger.info(f"   ✅ Прошли: {stats['passed']}")
    
    candidates.sort(key=lambda x: x['score'], reverse=True)
    return candidates[:TOP_LIMIT], stats


def format_mean_reversion_report(candidates, stats, date_str, time_str):
    """Форматирует отчёт."""
    lines = [
        "📉 *ВОЗВРАТ К EMA 20 — перепроданность фишки*",
        f"📅 {date_str} | {time_str}",
        f"📊 Найдено: {stats['passed']}",
        ""
    ]
    
    if candidates:
        medals = ["🥇", "🥈", "🥉"] + ["  "] * 7
        for i, c in enumerate(candidates):
            lines.extend([
                f"{medals[i]} *{i+1}. {c['ticker']}* ({c['short_name']}) | Score: *{c['score']}*",
                f"   💰 {c['close']} ₽ | EMA 20: {c['ema_20']} ₽ (отклонение: -{c['deviation_pct']}%)",
                f"   📉 RSI: {c['rsi']} | Объем: {c['volume_ratio']}x | Зелёная свеча ✅",
                ""
            ])
        lines.append("💡 *Цель: возврат к EMA 20 (+6–8%). Стоп: -2% от входа.*")
    else:
        lines.append("📉 *ВОЗВРАТ К EMA 20*: сигналов не найдено.")
    
    return "\n".join(lines)
