# ema50_scanner.py
import logging
import random
import pandas as pd
from config import EMA50_TOUCH_PCT, EMA50_RSI_MIN, TOP_LIMIT

logger = logging.getLogger(__name__)

def scan_ema50(market_data):
    """
    Стратегия «Отскок от EMA 50» — вход в тренд.
    С подробным логированием и проверкой сходимости.
    """
    candidates = []
    stats = {
        'total': len(market_data),
        'no_data': 0,
        'no_trend200': 0,
        'no_correction': 0,
        'no_touch': 0,
        'no_reversal': 0,
        'no_rsi': 0,
        'no_volume': 0,
        'passed': 0,
        'errors': 0
    }
    
    # Для диагностики: 2 случайные бумаги, которые "потерялись"
    debug_tickers = []
    lost_papers = []  # Бумаги, которые не попали ни в один фильтр
    
    if len(market_data) >= 2:
        debug_items = random.sample(market_data, min(2, len(market_data)))
        debug_tickers = [item['ticker'] for item in debug_items]
        logger.info(f"🔍 ДИАГНОСТИКА EMA50: случайные бумаги {debug_tickers}")
    
    # Счётчик для отслеживания всех бумаг
    all_processed = 0
    
    for item in market_data:
        ticker = item['ticker']
        all_processed += 1
        
        try:
            df = item['data']
            if df is None or len(df) < 200:
                stats['no_data'] += 1
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
            avg_vol = float(last['avg_volume_20'])
            
            # Флаги для диагностики
            filter_results = {}
            filter_results['1_has_data'] = True
            
            # Фильтр 2: Долгосрочный тренд (close > EMA 200)
            if pd.isna(ema_200) or close_p <= ema_200:
                stats['no_trend200'] += 1
                filter_results['2_trend200'] = False
                self._log_lost_paper(ticker, item.get('short_name', ''), close_p, ema_50, ema_200, filter_results, debug_tickers)
                continue
            filter_results['2_trend200'] = True
            
            # Фильтр 3: Коррекция (close < EMA 20)
            if pd.isna(ema_20) or close_p >= ema_20:
                stats['no_correction'] += 1
                filter_results['3_correction'] = False
                self._log_lost_paper(ticker, item.get('short_name', ''), close_p, ema_50, ema_200, filter_results, debug_tickers)
                continue
            filter_results['3_correction'] = True
            
            # Фильтр 4: Касание EMA 50
            if pd.isna(ema_50):
                stats['no_touch'] += 1
                filter_results['4_touch'] = False
                self._log_lost_paper(ticker, item.get('short_name', ''), close_p, ema_50, ema_200, filter_results, debug_tickers)
                continue
            
            touch_bound = ema_50 * (1 + EMA50_TOUCH_PCT / 100)
            if low_p > touch_bound or close_p <= ema_50:
                stats['no_touch'] += 1
                filter_results['4_touch'] = False
                self._log_lost_paper(ticker, item.get('short_name', ''), close_p, ema_50, ema_200, filter_results, debug_tickers)
                continue
            filter_results['4_touch'] = True
            
            # Фильтр 5: Разворотная свеча (зелёная)
            if close_p <= open_p:
                stats['no_reversal'] += 1
                filter_results['5_reversal'] = False
                self._log_lost_paper(ticker, item.get('short_name', ''), close_p, ema_50, ema_200, filter_results, debug_tickers)
                continue
            filter_results['5_reversal'] = True
            
            # Фильтр 6: RSI > MIN и растёт
            if pd.isna(rsi) or rsi <= EMA50_RSI_MIN:
                stats['no_rsi'] += 1
                filter_results['6_rsi'] = False
                self._log_lost_paper(ticker, item.get('short_name', ''), close_p, ema_50, ema_200, filter_results, debug_tickers)
                continue
            
            if prev is not None:
                prev_rsi = float(prev['rsi_14'])
                if pd.notna(prev_rsi) and rsi <= prev_rsi:
                    stats['no_rsi'] += 1
                    filter_results['6_rsi'] = False
                    self._log_lost_paper(ticker, item.get('short_name', ''), close_p, ema_50, ema_200, filter_results, debug_tickers)
                    continue
            filter_results['6_rsi'] = True
            
            # Фильтр 7: Объём
            if pd.isna(avg_vol) or avg_vol == 0 or volume <= avg_vol:
                stats['no_volume'] += 1
                filter_results['7_volume'] = False
                self._log_lost_paper(ticker, item.get('short_name', ''), close_p, ema_50, ema_200, filter_results, debug_tickers)
                continue
            filter_results['7_volume'] = True
            
            # Все фильтры пройдены!
            candle_range = high_p - low_p
            position = (close_p - low_p) / candle_range if candle_range > 0 else 0
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
            
            stats['passed'] += 1
            
            if ticker in debug_tickers:
                logger.info(f"   {ticker}: ✅ ПРОШЁЛ! Score={score}")
                logger.info(f"      Фильтры: {filter_results}")
            
        except Exception as e:
            stats['errors'] += 1
            logger.error(f"Ошибка EMA50 {ticker}: {e}")
            continue
    
    # Итоговая статистика
    total_checked = all_processed - stats['no_data'] - stats['errors']
    sum_filters = (stats['no_trend200'] + stats['no_correction'] + stats['no_touch'] + 
                   stats['no_reversal'] + stats['no_rsi'] + stats['no_volume'] + stats['passed'])
    
    logger.info(f"\n📊 ИТОГИ ОТСКОК ОТ EMA 50:")
    logger.info(f"   Всего бумаг: {stats['total']}")
    logger.info(f"   Проверено: {total_checked}")
    logger.info(f"   Отсев по фильтрам:")
    logger.info(f"      ❌ Нет тренда (close ≤ EMA200): {stats['no_trend200']}")
    logger.info(f"      ❌ Нет коррекции (close ≥ EMA20): {stats['no_correction']}")
    logger.info(f"      ❌ Нет касания EMA50: {stats['no_touch']}")
    logger.info(f"      ❌ Нет разворота (не зелёная): {stats['no_reversal']}")
    logger.info(f"      ❌ RSI слабый/падает: {stats['no_rsi']}")
    logger.info(f"      ❌ Нет объёма: {stats['no_volume']}")
    logger.info(f"      ✅ Прошли все фильтры: {stats['passed']}")
    logger.info(f"   Сумма проверок: {sum_filters} (должна совпадать с {total_checked})")
    logger.info(f"   Ошибок: {stats['errors']}")
    
    # Проверка сходимости
    if sum_filters != total_checked:
        logger.warning(f"⚠️ Расхождение в подсчётах! Сумма={sum_filters}, проверено={total_checked}")
        logger.warning(f"   Разница: {total_checked - sum_filters} бумаг не учтены")
    
    # Сортировка и ограничение
    candidates.sort(key=lambda x: x['score'], reverse=True)
    top_candidates = candidates[:TOP_LIMIT]
    
    logger.info(f"   Бумаг после всех фильтров: {len(candidates)}")
    logger.info(f"   Отсортировано по Score. Отправлено в Telegram: {len(top_candidates)}")
    
    return top_candidates, stats


def _log_lost_paper(ticker, short_name, close_p, ema_50, ema_200, filter_results, debug_tickers):
    """Логирует информацию о бумаге, если она в списке отладки."""
    if ticker in debug_tickers:
        logger.info(f"   {ticker} ({short_name}): ❌ отсеяна")
        logger.info(f"      Цена: {close_p:.2f}, EMA50: {ema_50:.2f}, EMA200: {ema_200:.2f}")
        for fname, fresult in filter_results.items():
            status = "✅" if fresult else "❌"
            logger.info(f"      {status} {fname}")


def format_ema50_report(candidates, stats, date_str, time_str):
    """Форматирует отчёт по стратегии Отскок от EMA 50."""
    lines = [
        "📈 *ОТСКОК ОТ EMA 50 — вход в тренд*",
        f"📅 {date_str} | {time_str}",
        f"📊 Проанализировано: {stats['total']} | Найдено: {stats['passed']}",
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
