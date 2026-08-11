# ema50_scanner.py
import logging
import pandas as pd
from config import EMA50_TOUCH_PCT, EMA50_RSI_MIN, TOP_LIMIT

logger = logging.getLogger(__name__)

def scan_ema50(market_data):
    """
    Стратегия «Отскок от EMA 50» — вход в тренд.
    """
    candidates = []
    stats = {
        'total': len(market_data),
        'no_trend200': 0,
        'no_correction': 0,
        'no_touch': 0,
        'no_reversal': 0,
        'no_rsi': 0,
        'no_volume': 0,
        'found': 0
    }
    
    for item in market_data:
        try:
            df = item['data']
            if df is None or len(df) < 200:
                continue
            
            last = df.iloc[-1]
            prev = df.iloc[-2] if len(df) >= 2 else None
            
            close_p = float(last['close'])
            open_p = float(last['open'])
            high_p = float(last['high'])
            low_p = float(last['low'])
            volume = float(last['volume'])
            
            ema_20 = float(last['ema_20'])
            ema_50 = float(last['ema_50'])
            ema_200 = float(last['ema_200'])
            rsi = float(last['rsi_14'])
            
            # Долгосрочный тренд: close > EMA 200
            if pd.isna(ema_200) or close_p <= ema_200:
                stats['no_trend200'] += 1
                continue
            
            # Коррекция: close < EMA 20
            if pd.isna(ema_20) or close_p >= ema_20:
                stats['no_correction'] += 1
                continue
            
            # Касание EMA 50
            if pd.isna(ema_50):
                stats['no_touch'] += 1
                continue
            
            touch_bound = ema_50 * (1 + EMA50_TOUCH_PCT / 100)
            if low_p > touch_bound or close_p <= ema_50:
                stats['no_touch'] += 1
                continue
            
            # Разворотная свеча: зелёная
            if close_p <= open_p:
                stats['no_reversal'] += 1
                continue
            
            # RSI > 35 и растёт
            if pd.isna(rsi) or rsi <= EMA50_RSI_MIN:
                stats['no_rsi'] += 1
                continue
            
            if prev is not None:
                prev_rsi = float(prev['rsi_14'])
                if pd.notna(prev_rsi) and rsi <= prev_rsi:
                    stats['no_rsi'] += 1
                    continue
            
            # Объём
            avg_vol = float(last['avg_volume_20'])
            if pd.isna(avg_vol) or avg_vol == 0 or volume <= avg_vol:
                stats['no_volume'] += 1
                continue
            
            # Score
            candle_range = high_p - low_p
            if candle_range > 0:
                position = (close_p - low_p) / candle_range
            else:
                position = 0
            
            score = round(position * (volume / avg_vol) * 10, 2)
            
            candidates.append({
                'ticker': item['ticker'],
                'short_name': item['short_name'],
                'score': score,
                'close': round(close_p, 2),
                'ema_50': round(ema_50, 2),
                'ema_200': round(ema_200, 2),
                'ema_20': round(ema_20, 2),
                'rsi': round(rsi, 1),
                'rsi_up': True,
                'volume_ratio': round(volume / avg_vol, 1)
            })
            
            stats['found'] += 1
            
        except Exception as e:
            logger.error(f"Ошибка EMA50 {item.get('ticker', '?')}: {e}")
            continue
    
    candidates.sort(key=lambda x: x['score'], reverse=True)
    return candidates[:TOP_LIMIT], stats


def format_ema50_report(candidates, stats, date_str, time_str):
    """Форматирует отчёт по стратегии Отскок от EMA 50."""
    lines = [
        "📈 *ОТСКОК ОТ EMA 50 — вход в тренд*",
        f"📅 {date_str} | {time_str}",
        f"📊 Проанализировано: {stats['total']} | Найдено: {stats['found']}",
        ""
    ]
    
    if candidates:
        medals = ["🥇", "🥈", "🥉"] + ["  "] * 7
        for i, c in enumerate(candidates):
            lines.extend([
                f"{medals[i]} *{i+1}. {c['ticker']}* ({c['short_name']}) | Score: *{c['score']}*",
                f"   💰 {c['close']} ₽ | EMA 50: {c['ema_50']} ₽ (касание ✅)",
                f"   📊 EMA 200: {c['ema_200']} (тренд ✅) | EMA 20: {c['ema_20']}",
                f"   📉 RSI: {c['rsi']} ↗️ | Объем: {c['volume_ratio']}x",
                ""
            ])
        lines.append("💡 *Вход: лимитная заявка у цены закрытия. Стоп: -2% (под EMA 50). Цель 1: EMA 20. Цель 2: предыдущий максимум.*")
    else:
        lines.append("📈 *ОТСКОК ОТ EMA 50*: сигналов не найдено.")
        lines.append(f"   (отсев: нет тренда={stats['no_trend200']}, нет коррекции={stats['no_correction']}, нет касания={stats['no_touch']}, нет разворота={stats['no_reversal']}, RSI={stats['no_rsi']}, нет объёма={stats['no_volume']})")
    
    return "\n".join(lines)
