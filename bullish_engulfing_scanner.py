# bullish_engulfing_scanner.py
import logging
import pandas as pd
from config import BE_BLUE_CHIP_ONLY, BE_MIN_BODY_RATIO, BLUE_CHIPS, TOP_LIMIT

logger = logging.getLogger(__name__)

def scan_bullish_engulfing(market_data):
    """
    Стратегия «Бычье поглощение» — выкуп просадки.
    """
    candidates = []
    stats = {
        'total': len(market_data),
        'not_blue_chip': 0,
        'no_data': 0,
        'no_red_yesterday': 0,
        'no_green_today': 0,
        'no_engulfing': 0,
        'no_body_ratio': 0,
        'no_volume': 0,
        'passed': 0,
        'errors': 0
    }
    
    for item in market_data:
        ticker = item['ticker']
        
        try:
            if BE_BLUE_CHIP_ONLY and ticker not in BLUE_CHIPS:
                stats['not_blue_chip'] += 1
                continue
            
            df = item['data']
            if df is None or len(df) < 60:
                stats['no_data'] += 1
                continue
            
            last = df.iloc[-1]
            prev = df.iloc[-2]
            
            close_p = float(last['close'])
            open_p = float(last['open'])
            volume = float(last['volume'])
            avg_vol = float(last['avg_volume_20'])
            
            prev_close = float(prev['close'])
            prev_open = float(prev['open'])
            
            # Вчера красная
            if prev_close >= prev_open:
                stats['no_red_yesterday'] += 1
                continue
            
            # Сегодня зелёная
            if close_p <= open_p:
                stats['no_green_today'] += 1
                continue
            
            # Поглощение
            if close_p < prev_open or open_p > prev_close:
                stats['no_engulfing'] += 1
                continue
            
            # Тело сегодня > тела вчера
            body_today = close_p - open_p
            body_yesterday = prev_open - prev_close
            
            if body_today < BE_MIN_BODY_RATIO * body_yesterday:
                stats['no_body_ratio'] += 1
                continue
            
            # Объём
            if pd.isna(avg_vol) or avg_vol == 0 or volume <= avg_vol:
                stats['no_volume'] += 1
                continue
            
            # Score
            volume_ratio = volume / avg_vol
            body_ratio = body_today / body_yesterday if body_yesterday > 0 else 0
            score = round(body_ratio * volume_ratio * 10, 2)
            
            # Проценты для отчёта
            prev_change_pct = (prev_close - prev_open) / prev_open * 100
            today_change_pct = (close_p - open_p) / open_p * 100
            
            candidates.append({
                'ticker': ticker,
                'short_name': item['short_name'],
                'score': score,
                'close': round(close_p, 2),
                'prev_change_pct': round(prev_change_pct, 1),
                'today_change_pct': round(today_change_pct, 1),
                'body_pct': round(today_change_pct, 1),
                'volume_ratio': round(volume_ratio, 1)
            })
            
            stats['passed'] += 1
            
        except Exception as e:
            stats['errors'] += 1
            logger.error(f"Ошибка Бычье поглощение {ticker}: {e}")
            continue
    
    logger.info(f"\n📊 ИТОГИ БЫЧЬЕ ПОГЛОЩЕНИЕ:")
    logger.info(f"   ❌ Не голубая фишка: {stats['not_blue_chip']}")
    logger.info(f"   ❌ Вчера не красная: {stats['no_red_yesterday']}")
    logger.info(f"   ❌ Сегодня не зелёная: {stats['no_green_today']}")
    logger.info(f"   ❌ Нет поглощения: {stats['no_engulfing']}")
    logger.info(f"   ❌ Тело маленькое: {stats['no_body_ratio']}")
    logger.info(f"   ❌ Нет объёма: {stats['no_volume']}")
    logger.info(f"   ✅ Прошли: {stats['passed']}")
    
    candidates.sort(key=lambda x: x['score'], reverse=True)
    return candidates[:TOP_LIMIT], stats


def format_bullish_engulfing_report(candidates, stats, date_str, time_str):
    """Форматирует отчёт."""
    lines = [
        "📗 *БЫЧЬЕ ПОГЛОЩЕНИЕ — выкуп просадки*",
        f"📅 {date_str} | {time_str}",
        f"📊 Найдено: {stats['passed']}",
        ""
    ]
    
    if candidates:
        medals = ["🥇", "🥈", "🥉"] + ["  "] * 7
        for i, c in enumerate(candidates):
            lines.extend([
                f"{medals[i]} *{i+1}. {c['ticker']}* ({c['short_name']}) | Score: *{c['score']}*",
                f"   💰 {c['close']} ₽ | Вчера: {c['prev_change_pct']}%, Сегодня: +{c['today_change_pct']}%",
                f"   📊 Тело сегодня: {c['body_pct']}% | Объем: {c['volume_ratio']}x",
                ""
            ])
        lines.append("💡 *Вход у цены закрытия. Стоп: под минимум сегодняшней свечи. Цель: 5–8%.*")
    else:
        lines.append("📗 *БЫЧЬЕ ПОГЛОЩЕНИЕ*: сигналов не найдено.")
    
    return "\n".join(lines)
