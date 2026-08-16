# bot.py
import asyncio
import logging
from datetime import datetime
import pytz
from aiohttp import web

from squeeze_scanner import scan_squeeze, format_squeeze_report
from double_bottom_scanner import scan_double_bottom, format_double_bottom_report

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import config
from database import SubscriberDB
from moex_api import load_market_data

from hammer_scanner import scan_hammer, format_hammer_report
from breakout_scanner import scan_breakout, format_breakout_report
from ema50_scanner import scan_ema50, format_ema50_report

from relative_strength_scanner import scan_relative_strength, format_relative_strength_report
from mean_reversion_scanner import scan_mean_reversion, format_mean_reversion_report
from bullish_engulfing_scanner import scan_bullish_engulfing, format_bullish_engulfing_report
from dividend_gap_scanner import scan_dividend_gap, format_dividend_gap_report
from moex_api import load_imoex_index, get_imoex_analysis

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Часовой пояс МСК
MOSCOW_TZ = pytz.timezone("Europe/Moscow")

# Инициализация базы данных
db = SubscriberDB()

# Глобальные переменные для кэша
last_reports = {}  # {'hammer': str, 'breakout': str, 'ema50': str, 'summary': str}
last_scan_time = None

# ===== Клавиатуры =====

def get_main_keyboard():
    keyboard = [
        [KeyboardButton("🔨 Молот"), KeyboardButton("🚀 Пробой тишины")],
        [KeyboardButton("📈 Отскок от EMA 50"), KeyboardButton("🌀 Сжатая пружина")],
        [KeyboardButton("🏔️ Двойное дно"), KeyboardButton("💪 Сильная бумага")],
        [KeyboardButton("📉 Возврат к EMA 20"), KeyboardButton("📗 Бычье поглощение")],
        [KeyboardButton("💸 Дивидендный разрыв"), KeyboardButton("📊 Все стратегии")],
        [KeyboardButton("ℹ️ Помощь"), KeyboardButton("📋 Статистика")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, persistent=True)

def get_inline_strategy_menu():
    keyboard = [
        [InlineKeyboardButton("🔨 Молот", callback_data="scan_hammer"),
         InlineKeyboardButton("🚀 Пробой", callback_data="scan_breakout")],
        [InlineKeyboardButton("📈 EMA 50", callback_data="scan_ema50"),
         InlineKeyboardButton("🌀 Пружина", callback_data="scan_squeeze")],
        [InlineKeyboardButton("🏔️ Двойное дно", callback_data="scan_double_bottom"),
         InlineKeyboardButton("💪 Сильная бумага", callback_data="scan_rs")],
        [InlineKeyboardButton("📉 EMA 20", callback_data="scan_mean_reversion"),
         InlineKeyboardButton("📗 Поглощение", callback_data="scan_bullish_engulfing")],
        [InlineKeyboardButton("💸 Див. разрыв", callback_data="scan_dividend_gap")],
        [InlineKeyboardButton("📊 ВСЕ СТРАТЕГИИ", callback_data="scan_all")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("🔔 Подписка", callback_data="subscription")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_subscription_menu():
    """Меню управления подпиской."""
    keyboard = [
        [InlineKeyboardButton("✅ Подписаться", callback_data="sub_on"),
         InlineKeyboardButton("❌ Отписаться", callback_data="sub_off")],
        [InlineKeyboardButton("📊 Статус подписки", callback_data="sub_status")],
        [InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ===== Веб-сервер =====

async def health_check(request):
    return web.Response(text="OK", status=200)

async def ping(request):
    stats = db.get_stats()
    return web.json_response({
        "status": "alive",
        "timestamp": datetime.now(MOSCOW_TZ).isoformat(),
        "subscribers": stats,
        "bot_active": True
    })

def create_web_app():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/ping', ping)
    return app

# ===== Обработчики команд =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    db.add_subscriber(chat_id=chat_id, username=user.username, first_name=user.first_name)
    
    welcome_text = (
        f"👋 <b>Привет, {user.first_name}!</b>\n\n"
        "Я бот «Молоток» 🔨\n"
        "Анализирую рынок акций Мосбиржи по трём стратегиям:\n\n"
        "🔨 <b>Молот</b> — разворот у поддержки\n"
        "🚀 <b>Пробой тишины</b> — выход из боковика\n"
        "📈 <b>Отскок от EMA 50</b> — вход в тренд\n\n"
        "📅 <b>Автоматическая рассылка:</b>\n"
        f"• Утро: {config.MORNING_SCAN_HOUR}:{config.MORNING_SCAN_MINUTE:02d} МСК\n"
        f"• Вечер: {config.EVENING_SCAN_HOUR}:{config.EVENING_SCAN_MINUTE:02d} МСК\n\n"
        "Выберите стратегию в меню или нажмите кнопку:"
    )
    
    await update.message.reply_text(
        welcome_text,
        parse_mode="HTML",
        reply_markup=get_inline_strategy_menu()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка."""
    help_text = (
        "🤖 <b>Бот «Молоток» — Справка</b>\n\n"
        "<b>📋 Команды:</b>\n"
        "/start — Главное меню\n"
        "/scan — Запустить все стратегии\n"
        "/hammer — Стратегия «Молот»\n"
        "/breakout — Стратегия «Пробой тишины»\n"
        "/ema50 — Стратегия «Отскок от EMA 50»\n"
        "/stats — Статистика\n"
        "/subscribe — Подписаться\n"
        "/unsubscribe — Отписаться\n"
        "/help — Эта справка\n\n"
        "<b>🔍 Стратегии:</b>\n"
        "🔨 <b>Молот:</b> свечной паттерн у 60-дневного минимума\n"
        "🚀 <b>Пробой тишины:</b> выход из узкого боковика на объёме\n"
        "📈 <b>Отскок от EMA 50:</b> коррекция к скользящей средней в тренде\n\n"
        "💡 <i>Анализ занимает 1-2 минуты</i>"
    )
    
    await update.message.reply_text(help_text, parse_mode="HTML")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика."""
    stats = db.get_stats()
    current_time = datetime.now(MOSCOW_TZ)
    
    stats_text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 Активных подписчиков: <b>{stats['active']}</b>\n"
        f"📝 Всего пользователей: <b>{stats['total']}</b>\n"
        f"⏰ Время сервера: <b>{current_time.strftime('%H:%M МСК')}</b>\n"
        f"📅 Дата: <b>{current_time.strftime('%d.%m.%Y')}</b>\n\n"
    )
    
    if last_scan_time:
        stats_text += f"🕐 Последний анализ: <b>{last_scan_time.strftime('%H:%M:%S МСК')}</b>"
    else:
        stats_text += "🕐 Последний анализ: <b>ещё не проводился</b>"
    
    await update.message.reply_text(stats_text, parse_mode="HTML")

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    if db.add_subscriber(chat_id, user.username, user.first_name):
        await update.message.reply_text(
            f"✅ <b>Вы подписаны!</b>\n"
            f"Рассылка в {config.MORNING_SCAN_HOUR}:{config.MORNING_SCAN_MINUTE:02d} "
            f"и {config.EVENING_SCAN_HOUR}:{config.EVENING_SCAN_MINUTE:02d} МСК",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("❌ Ошибка подписки.")

async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if db.remove_subscriber(chat_id):
        await update.message.reply_text("❌ <b>Вы отписались от рассылки.</b>", parse_mode="HTML")
    else:
        await update.message.reply_text("⚠️ Вы не были подписаны.")

# ===== Команды для отдельных стратегий =====

async def hammer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_single_strategy(update, context, 'hammer')

async def breakout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_single_strategy(update, context, 'breakout')

async def ema50_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_single_strategy(update, context, 'ema50')

async def scan_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_single_strategy(update, context, 'all')

# ===== Обработчики текстовых сообщений =====

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок постоянного меню."""
    text = update.message.text
    
    if text == "🔨 Молот":
        await run_single_strategy(update, context, 'hammer')
    elif text == "🚀 Пробой тишины":
        await run_single_strategy(update, context, 'breakout')
    elif text == "📈 Отскок от EMA 50":
        await run_single_strategy(update, context, 'ema50')
    elif text == "📊 Все стратегии":
        await run_single_strategy(update, context, 'all')
    elif text == "ℹ️ Помощь":
        await help_command(update, context)
    elif text == "📋 Статистика":
        await stats_command(update, context)
    elif text == "🌀 Сжатая пружина":
        await run_single_strategy(update, context, 'squeeze')
    elif text == "🏔️ Двойное дно":
        await run_single_strategy(update, context, 'double_bottom')

# ===== Обработчик инлайн-кнопок =====

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на инлайн-кнопки."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "scan_hammer":
        await run_single_strategy_inline(query, context, 'hammer')
    elif query.data == "scan_breakout":
        await run_single_strategy_inline(query, context, 'breakout')
    elif query.data == "scan_ema50":
        await run_single_strategy_inline(query, context, 'ema50')
    elif query.data == "scan_squeeze":
        await run_single_strategy_inline(query, context, 'squeeze')
    elif query.data == "scan_double_bottom":
        await run_single_strategy_inline(query, context, 'double_bottom')
    elif query.data == "scan_all":
        await run_single_strategy_inline(query, context, 'all')
    elif query.data == "stats":
        stats = db.get_stats()
        current_time = datetime.now(MOSCOW_TZ)
        await query.edit_message_text(
            f"📊 <b>Статистика</b>\n\n"
            f"👥 Подписчиков: {stats['active']}\n"
            f"⏰ {current_time.strftime('%H:%M МСК')}",
            parse_mode="HTML",
            reply_markup=get_inline_strategy_menu()
        )
    elif query.data == "subscription":
        chat_id = query.message.chat_id
        subs = db.get_active_subscribers()
        is_subscribed = chat_id in subs
        status = "✅ Подписан" if is_subscribed else "❌ Не подписан"
        await query.edit_message_text(
            f"🔔 <b>Управление подпиской</b>\n\nСтатус: {status}",
            parse_mode="HTML",
            reply_markup=get_subscription_menu()
        )
    elif query.data == "sub_on":
        user = query.from_user
        chat_id = query.message.chat_id
        if db.add_subscriber(chat_id, user.username, user.first_name):
            await query.edit_message_text("✅ <b>Вы подписались!</b>", parse_mode="HTML", reply_markup=get_inline_strategy_menu())
        else:
            await query.edit_message_text("❌ Ошибка.", reply_markup=get_subscription_menu())
    elif query.data == "sub_off":
        chat_id = query.message.chat_id
        if db.remove_subscriber(chat_id):
            await query.edit_message_text("❌ <b>Вы отписались.</b>", parse_mode="HTML", reply_markup=get_inline_strategy_menu())
        else:
            await query.edit_message_text("⚠️ Ошибка.", reply_markup=get_subscription_menu())
    elif query.data == "sub_status":
        chat_id = query.message.chat_id
        subs = db.get_active_subscribers()
        is_subscribed = chat_id in subs
        status = "✅ Подписан" if is_subscribed else "❌ Не подписан"
        await query.edit_message_text(
            f"🔔 <b>Статус подписки:</b> {status}\nID: <code>{chat_id}</code>",
            parse_mode="HTML",
            reply_markup=get_subscription_menu()
        )
    elif query.data == "main_menu":
        await query.edit_message_text(
            "🤖 <b>Главное меню</b>\nВыберите стратегию:",
            parse_mode="HTML",
            reply_markup=get_inline_strategy_menu()
        )

# ===== Логика сканирования =====

async def run_single_strategy(update, context, strategy):
    """Запуск стратегии через команду или кнопку."""
    msg = await update.message.reply_text(f"⏳ Загружаю данные рынка...")
    
    if update.effective_chat:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        result_text = await execute_scan(strategy)
        await msg.edit_text(result_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка сканирования: {e}", exc_info=True)
        await msg.edit_text("❌ <b>Ошибка при анализе.</b> Попробуйте позже.", parse_mode="HTML")

async def run_single_strategy_inline(query, context, strategy):
    """Запуск стратегии через инлайн-кнопку."""
    await query.edit_message_text("⏳ Загружаю данные рынка...")
    
    try:
        result_text = await execute_scan(strategy)
        await query.edit_message_text(result_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка сканирования: {e}", exc_info=True)
        await query.edit_message_text("❌ <b>Ошибка при анализе.</b>", parse_mode="HTML", reply_markup=get_inline_strategy_menu())

async def execute_scan(strategy):
    """
    Выполняет сканирование по выбранной стратегии.
    strategy: 'hammer', 'breakout', 'ema50', 'squeeze', 'double_bottom',
              'rs', 'mean_reversion', 'bullish_engulfing', 'dividend_gap', 'all'
    """
    global last_reports, last_scan_time
    
    # Загружаем данные (один раз для всех стратегий)
    logger.info("📥 Загрузка данных рынка...")
    market_data = load_market_data()
    
    # Загружаем индекс IMOEX
    imoex_df = load_imoex_index()
    imoex_analysis = get_imoex_analysis(imoex_df)
    
    now = datetime.now(MOSCOW_TZ)
    date_str = now.strftime("%a, %d.%m.%Y")
    time_str = now.strftime("%H:%M МСК")
    
    last_scan_time = now
    last_reports = {}
    
    # Проверка паники
    is_panic = imoex_analysis.get('is_panic', False)
    market_change = imoex_analysis.get('day_change_pct', 0)
    
    if is_panic:
        logger.warning(f"⚠️ ПАНИКА! IMOEX: {market_change}% за день. Разворотные стратегии отключены.")
    
    # Вспомогательная функция проверки блокировки
    def is_blocked(strategy_name):
        return is_panic and strategy_name in config.BLOCKED_IN_PANIC
    
    # Вспомогательная функция форматирования отключённой стратегии
    def blocked_message(strategy_emoji, strategy_name):
        return f"{strategy_emoji} *{strategy_name}*: ⛔ отключён (паника на рынке)"
    
    # ========== СТРАТЕГИЯ 1: МОЛОТ ==========
    if strategy == 'hammer':
        if is_blocked('hammer'):
            return blocked_message("🔨", "МОЛОТ")
        
        logger.info("🔨 Запуск стратегии Молот...")
        candidates, stats = scan_hammer(market_data)
        report = format_hammer_report(candidates, stats, date_str, time_str)
        last_reports['hammer'] = report
        return report
    
    # ========== СТРАТЕГИЯ 2: ПРОБОЙ ТИШИНЫ ==========
    elif strategy == 'breakout':
        if is_blocked('breakout'):
            return blocked_message("🚀", "ПРОБОЙ ТИШИНЫ")
        
        logger.info("🚀 Запуск стратегии Пробой тишины...")
        candidates, stats = scan_breakout(market_data)
        report = format_breakout_report(candidates, stats, date_str, time_str)
        last_reports['breakout'] = report
        return report
    
    # ========== СТРАТЕГИЯ 3: ОТСКОК ОТ EMA 50 ==========
    elif strategy == 'ema50':
        if is_blocked('ema50_bounce'):
            return blocked_message("📈", "ОТСКОК ОТ EMA 50")
        
        logger.info("📈 Запуск стратегии Отскок от EMA 50...")
        candidates, stats = scan_ema50(market_data)
        report = format_ema50_report(candidates, stats, date_str, time_str)
        last_reports['ema50'] = report
        return report
    
    # ========== СТРАТЕГИЯ 4: СЖАТАЯ ПРУЖИНА ==========
    elif strategy == 'squeeze':
        if is_blocked('squeeze'):
            return blocked_message("🌀", "СЖАТАЯ ПРУЖИНА")
        
        logger.info("🌀 Запуск стратегии Сжатая пружина...")
        candidates, stats = scan_squeeze(market_data)
        report = format_squeeze_report(candidates, stats, date_str, time_str)
        last_reports['squeeze'] = report
        return report
    
    # ========== СТРАТЕГИЯ 5: ДВОЙНОЕ ДНО ==========
    elif strategy == 'double_bottom':
        if is_blocked('double_bottom'):
            return blocked_message("🏔️", "ДВОЙНОЕ ДНО")
        
        logger.info("🏔️ Запуск стратегии Двойное дно...")
        candidates, stats = scan_double_bottom(market_data)
        report = format_double_bottom_report(candidates, stats, date_str, time_str)
        last_reports['double_bottom'] = report
        return report
    
    # ========== СТРАТЕГИЯ 6: СИЛЬНАЯ БУМАГА ==========
    elif strategy == 'rs':
        logger.info("💪 Запуск стратегии Сильная бумага...")
        candidates, stats = scan_relative_strength(market_data, imoex_analysis)
        report = format_relative_strength_report(candidates, stats, date_str, time_str)
        last_reports['rs'] = report
        return report
    
    # ========== СТРАТЕГИЯ 7: ВОЗВРАТ К EMA 20 ==========
    elif strategy == 'mean_reversion':
        if is_blocked('mean_reversion'):
            return blocked_message("📉", "ВОЗВРАТ К EMA 20")
        
        logger.info("📉 Запуск стратегии Возврат к EMA 20...")
        candidates, stats = scan_mean_reversion(market_data)
        report = format_mean_reversion_report(candidates, stats, date_str, time_str)
        last_reports['mean_reversion'] = report
        return report
    
    # ========== СТРАТЕГИЯ 8: БЫЧЬЕ ПОГЛОЩЕНИЕ ==========
    elif strategy == 'bullish_engulfing':
        if is_blocked('bullish_engulfing'):
            return blocked_message("📗", "БЫЧЬЕ ПОГЛОЩЕНИЕ")
        
        logger.info("📗 Запуск стратегии Бычье поглощение...")
        candidates, stats = scan_bullish_engulfing(market_data)
        report = format_bullish_engulfing_report(candidates, stats, date_str, time_str)
        last_reports['bullish_engulfing'] = report
        return report
    
    # ========== СТРАТЕГИЯ 9: ДИВИДЕНДНЫЙ РАЗРЫВ ==========
    elif strategy == 'dividend_gap':
        logger.info("💸 Запуск стратегии Дивидендный разрыв...")
        candidates, stats = scan_dividend_gap(market_data)
        report = format_dividend_gap_report(candidates, stats, date_str, time_str)
        last_reports['dividend_gap'] = report
        return report
    
    # ========== ВСЕ СТРАТЕГИИ ==========
    elif strategy == 'all':
        logger.info("📊 Запуск ВСЕХ стратегий...")
        
        reports = {}
        summary_lines = [
            "📊 *СВОДКА СТРАТЕГИЙ*",
            f"📅 {date_str} | {time_str}"
        ]
        
        # Добавляем предупреждение о панике
        if is_panic:
            summary_lines.append(f"⚠️ Рынок упал на {abs(market_change)}% за день. Разворотные стратегии отключены.")
        
        summary_lines.append("")
        
        # Запускаем все 9 стратегий
        all_strategies = [
            ('hammer', '🔨', 'Молот', 'hammer', scan_hammer, format_hammer_report),
            ('breakout', '🚀', 'Пробой тишины', 'breakout', scan_breakout, format_breakout_report),
            ('ema50', '📈', 'Отскок от EMA 50', 'ema50_bounce', scan_ema50, format_ema50_report),
            ('squeeze', '🌀', 'Сжатая пружина', 'squeeze', scan_squeeze, format_squeeze_report),
            ('double_bottom', '🏔️', 'Двойное дно', 'double_bottom', scan_double_bottom, format_double_bottom_report),
            ('rs', '💪', 'Сильная бумага', 'rs', scan_relative_strength, format_relative_strength_report),
            ('mean_reversion', '📉', 'Возврат к EMA 20', 'mean_reversion', scan_mean_reversion, format_mean_reversion_report),
            ('bullish_engulfing', '📗', 'Бычье поглощение', 'bullish_engulfing', scan_bullish_engulfing, format_bullish_engulfing_report),
            ('dividend_gap', '💸', 'Дивидендный разрыв', 'dividend_gap', scan_dividend_gap, format_dividend_gap_report),
        ]
        
        report_parts = []
        
        for key, emoji, display_name, block_key, scan_func, format_func in all_strategies:
            # Проверяем блокировку паникой
            if is_blocked(block_key):
                summary_lines.append(f"{emoji} {display_name}: ⛔ отключён (паника)")
                reports[key] = f"{emoji} *{display_name}*: ⛔ отключён (паника на рынке)"
                continue
            
            # Запускаем сканер
            try:
                logger.info(f"{emoji} Запуск: {display_name}...")
                
                if key == 'rs':
                    # Для Сильной бумаги нужен imoex_analysis
                    candidates, stats = scan_relative_strength(market_data, imoex_analysis)
                    report = format_relative_strength_report(candidates, stats, date_str, time_str)
                else:
                    candidates, stats = scan_func(market_data)
                    report = format_func(candidates, stats, date_str, time_str)
                
                reports[key] = report
                summary_lines.append(f"{emoji} {display_name}: {stats['passed']} сигналов")
                
            except Exception as e:
                logger.error(f"❌ Ошибка в {display_name}: {e}", exc_info=True)
                reports[key] = f"{emoji} *{display_name}*: ⚠️ ошибка"
                summary_lines.append(f"{emoji} {display_name}: ⚠️ ошибка")
        
        # Формируем сводку
        summary_lines.append("---")
        summary_lines.append("*Далее — детальные отчёты по каждой стратегии.*")
        summary = "\n".join(summary_lines)
        
        last_reports['summary'] = summary
        
        # Объединяем все отчёты
        full_report_parts = [summary, ""]
        
        for key, emoji, display_name, _, _, _ in all_strategies:
            if key in reports:
                full_report_parts.append(reports[key])
                full_report_parts.append("")
        
        full_report = "\n\n".join(full_report_parts).strip()
        
        # Сохраняем все отчёты для последующего доступа
        for key, report in reports.items():
            last_reports[key] = report
        
        # Обрезаем для Telegram (лимит 4096 символов)
        if len(full_report) > 4000:
            logger.warning(f"⚠️ Отчёт обрезан: {len(full_report)} символов")
            full_report = full_report[:4000] + "\n\n⚠️ Отчёт обрезан из-за лимита Telegram."
        
        return full_report
    
    # ========== НЕИЗВЕСТНАЯ СТРАТЕГИЯ ==========
    else:
        logger.warning(f"⚠️ Неизвестная стратегия: {strategy}")
        return "⚠️ Неизвестная стратегия."

async def scheduled_scan(context: ContextTypes.DEFAULT_TYPE):
    """Задача для автоматической рассылки."""
    global last_reports, last_scan_time
    
    logger.info("📅 Запуск планового сканирования...")
    
    subscribers = db.get_active_subscribers()
    if not subscribers:
        logger.warning("Нет активных подписчиков")
        return
    
    try:
        # Выполняем все стратегии
        full_report = await execute_scan('all')
        
        # Отправляем сводку и отдельные отчёты
        for chat_id in subscribers:
            try:
                # Сначала сводку
                if 'summary' in last_reports:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=last_reports['summary'],
                        parse_mode="HTML"
                    )
                    await asyncio.sleep(0.5)
                
                # Затем каждый отчёт отдельно
                report_keys = ['hammer', 'breakout', 'ema50', 'squeeze', 'double_bottom',
                               'rs', 'mean_reversion', 'bullish_engulfing', 'dividend_gap']
                
                for key in report_keys:
                    if key in last_reports and '⛔' not in last_reports[key]:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=last_reports[key],
                            parse_mode="HTML"
                        )
                        await asyncio.sleep(0.5)
                        
            except Exception as e:
                logger.error(f"Ошибка отправки {chat_id}: {e}")
                if "bot was blocked" in str(e).lower():
                    db.remove_subscriber(chat_id)
        
        logger.info(f"Рассылка завершена: {len(subscribers)} подписчиков")
        
    except Exception as e:
        logger.error(f"Ошибка плановой рассылки: {e}", exc_info=True)

async def setup_bot():
    """Настройка и запуск бота."""
    if not config.TELEGRAM_TOKEN or config.TELEGRAM_TOKEN == "YOUR_TOKEN_HERE":
        logger.error("❌ Не указан TELEGRAM_BOT_TOKEN!")
        raise ValueError("TELEGRAM_BOT_TOKEN не установлен")
    
    application = Application.builder().token(config.TELEGRAM_TOKEN).build()
    
    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("scan", scan_all_command))
    application.add_handler(CommandHandler("hammer", hammer_command))
    application.add_handler(CommandHandler("breakout", breakout_command))
    application.add_handler(CommandHandler("ema50", ema50_command))
    application.add_handler(CommandHandler("squeeze", squeeze_command))
    application.add_handler(CommandHandler("doublebottom", double_bottom_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    
    # Обработчик текстовых сообщений (кнопки меню)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Обработчик инлайн-кнопок
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Настройка планировщика
    scheduler = AsyncIOScheduler(timezone=MOSCOW_TZ)
    scheduler.add_job(
        scheduled_scan,
        trigger=CronTrigger(hour=config.MORNING_SCAN_HOUR, minute=config.MORNING_SCAN_MINUTE),
        args=[application],
        id="morning_scan",
        replace_existing=True
    )
    scheduler.add_job(
        scheduled_scan,
        trigger=CronTrigger(hour=config.EVENING_SCAN_HOUR, minute=config.EVENING_SCAN_MINUTE),
        args=[application],
        id="evening_scan",
        replace_existing=True
    )
    scheduler.start()
    
    logger.info(f"⏰ Планировщик запущен: {config.MORNING_SCAN_HOUR}:{config.MORNING_SCAN_MINUTE:02d} и {config.EVENING_SCAN_HOUR}:{config.EVENING_SCAN_MINUTE:02d} МСК")
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    
    logger.info("🤖 Бот запущен и готов к работе!")
    
    return application

async def main():
    """Главная функция."""
    try:
        application = await setup_bot()
        
        # Веб-сервер
        web_app = create_web_app()
        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', config.PORT)
        await site.start()
        logger.info(f"🌐 Веб-сервер запущен на порту {config.PORT}")
        
        # Бесконечное ожидание
        stop_event = asyncio.Event()
        await stop_event.wait()
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        raise
    finally:
        if 'application' in locals():
            await application.stop()
            await application.shutdown()

async def squeeze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_single_strategy(update, context, 'squeeze')

async def double_bottom_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_single_strategy(update, context, 'double_bottom')

if __name__ == "__main__":
    asyncio.run(main())
