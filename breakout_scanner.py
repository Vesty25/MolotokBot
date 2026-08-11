# breakout_scanner.py
import logging
import numpy as np
from config import BREAKOUT_RANGE_PCT, BREAKOUT_VOLUME_RATIO, BREAKOUT_LOOKBACK, TOP_LIMIT

logger = logging.getLogger(__name__)

def scan_breakout(market_data):
    """
    Стратегия «Пробой тишины» — выход из боковика.
    """
    candidates = []
    stats = {
        'total': len(market_data),
        'no_trend': 0,
        'no_range': 0,
        'no_breakout': 0,
        'no_volume': 0,
        'found': 0
    }
    
    for item in market_data:
        try:
            df = item['data']
            if df is None or len(df) < 60:
                continue
            
            last = df.iloc[-1]
            close_p = float(last['close'])
            open_p = float(last['open'])
            volume = float(last['volume'])
            ema_50 = float(last['ema_50'])
            
            # Тренд: close > EMA 50
            if pd.isna(ema_50) or close_p <= ema_50:
                stats['no_trend'] += 1
                continue
            
            # Данные за 15 дней (без последнего дня)
            prev_15 = df.iloc[-(BREAKOUT_LOOKBACK+1):-1]
            if len(prev_15) < BREAKOUT_LOOKBACK:
                continue
            
            # Средняя амплитуда
            amplitudes = (prev_15['high'] - prev_15['low']) / prev_15['close']
            avg_amplitude = float(amplitudes.mean()) * 100
            
            if avg_amplitude > BREAKOUT_RANGE_PCT:
                stats['no_range'] += 1
                continue
            
            # Пробой: close > max high за 15 дней
            max_high_15 = float(prev_15['high'].max())
            if close_p <= max_high_15:
                stats['no_breakout'] += 1
                continue
            
            # Объём
            avg_vol_15 = float(prev_15['volume'].mean())
            if avg_vol_15 == 0 or volume < BREAKOUT_VOLUME_RATIO * avg_vol_15:
                stats['no_volume'] += 1
                continue
            
            # Зелёная свеча
            if close_p <= open_p:
                continue
            
            # Score
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
            
            stats['found'] += 1
            
        except Exception as e:
            logger.error(f"Ошибка Пробой {item.get('ticker', '?')}: {e}")
            continue
    
    candidates.sort(key=lambda x: x['score'], reverse=True)
    return candidates[:TOP_LIMIT], stats


def format_breakout_report(candidates, stats, date_str, time_str):
    """Форматирует отчёт по стратегии Пробой тишины."""
    lines = [
        "🚀 *ПРОБОЙ ТИШИНЫ — выход из боковика*",
        f"📅 {date_str} | {time_str}",
        f"📊 Проанализировано: {stats['total']} | Найдено: {stats['found']}",
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
        lines.append(f"   (отсев: нет тренда={stats['no_trend']}, не сузился={stats['no_range']}, нет пробоя={stats['no_breakout']}, нет объёма={stats['no_volume']})")
    
    return "\n".join(lines)
