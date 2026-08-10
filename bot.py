# bot.py
import asyncio
import logging
from datetime import datetime
import pytz
from aiohttp import web

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import config
from database import SubscriberDB
from moex_parser import (
    get_filtered_tickers,
    get_daily_candles,
    calculate_average_volume_rub,
    is_valid_share_type,
    diagnose_sber_candles
)
from pattern_engine import find_hammer

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
last_scan_report = None
last_scan_time = None

# ===== Клавиатуры =====

def get_main_keyboard():
    """Основное меню бота (постоянная клавиатура)."""
    keyboard = [
        [KeyboardButton("🔍 Сканировать рынок"), KeyboardButton("📊 Статистика")],
        [KeyboardButton("ℹ️ Помощь"), KeyboardButton("🔔 Подписка")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, persistent=True)

def get_inline_main_menu():
    """Инлайн меню (под сообщениями)."""
    keyboard = [
        [InlineKeyboardButton("🔍 Запросить анализ", callback_data="scan")],
        [InlineKeyboardButton("📊 Статистика бота", callback_data="stats")],
        [InlineKeyboardButton("📋 Последний отчет", callback_data="last_report")],
        [InlineKeyboardButton("🔔 Управление подпиской", callback_data="subscription")]
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
    """Эндпоинт для проверки здоровья сервера."""
    return web.Response(text="OK", status=200)

async def ping(request):
    """Эндпоинт для UptimeRobot."""
    stats = db.get_stats()
    return web.json_response({
        "status": "alive",
        "timestamp": datetime.now(MOSCOW_TZ).isoformat(),
        "subscribers": stats,
        "bot_active": True
    })

def create_web_app():
    """Создание веб-приложения."""
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/ping', ping)
    return app

# ===== Обработчики команд =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    db.add_subscriber(
        chat_id=chat_id,
        username=user.username,
        first_name=user.first_name
    )
    
    welcome_text = (
        f"👋 <b>Привет, {user.first_name}!</b>\n\n"
        "Я бот «Молоток» 🔨\n"
        "Ищу акции с бычьим паттерном «Молот» у уровня поддержки.\n\n"
        "📅 <b>Автоматическая рассылка:</b>\n"
        f"• Утро: {config.MORNING_SCAN_HOUR}:{config.MORNING_SCAN_MINUTE:02d} МСК\n"
        f"• Вечер: {config.EVENING_SCAN_HOUR}:{config.EVENING_SCAN_MINUTE:02d} МСК\n\n"
        "🔍 <b>Как использовать:</b>\n"
        "• Нажмите кнопку ниже для анализа\n"
        "• Используйте меню для навигации\n"
        "• Команда /scan для ручного запуска\n\n"
        "💡 <i>Анализ рынка занимает 1-2 минуты</i>"
    )
    
    await update.message.reply_text(
        welcome_text,
        parse_mode="HTML",
        reply_markup=get_inline_main_menu()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка по командам."""
    help_text = (
        "🤖 <b>Бот «Молоток» - Справка</b>\n\n"
        "<b>📋 Команды:</b>\n"
        "/start - Главное меню\n"
        "/scan - Запустить анализ рынка\n"
        "/stats - Статистика бота\n"
        "/subscribe - Подписаться на рассылку\n"
        "/unsubscribe - Отписаться от рассылки\n"
        "/help - Эта справка\n\n"
        "<b>🔍 Что анализирует бот:</b>\n"
        "• Только обыкновенные и привилегированные акции\n"
        "• Цена закрытия > 10 ₽ (без мусорных бумаг)\n"
        "• Средний объем > 10 млн руб/день\n"
        "• Тело свечи ≥ 0.5% от цены\n"
        "• Нижняя тень ≥ 2% от цены\n"
        "• Паттерн «Молот» у 60-дневного минимума\n"
        "• Подтверждение повышенным объемом\n\n"
        "<b>📊 Как читать сигналы:</b>\n"
        "Score - сила сигнала (чем выше, тем лучше)\n"
        "Тело - размер тела свечи в %\n"
        "Тень - размер нижней тени в %\n"
        "Объем - превышение над средним\n\n"
        "<b>⚠️ Важно:</b>\n"
        "Проверяйте сигналы визуально!\n"
        "Используйте стоп-лосс -2%."
    )
    
    await update.message.reply_text(help_text, parse_mode="HTML")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статистику."""
    stats = db.get_stats()
    current_time = datetime.now(MOSCOW_TZ)
    
    stats_text = (
        "📊 <b>Статистика бота «Молоток»</b>\n\n"
        f"👥 Активных подписчиков: <b>{stats['active']}</b>\n"
        f"📝 Всего пользователей: <b>{stats['total']}</b>\n"
        f"⏰ Время сервера: <b>{current_time.strftime('%H:%M МСК')}</b>\n"
        f"📅 Дата: <b>{current_time.strftime('%d.%m.%Y')}</b>\n\n"
    )
    
    if last_scan_time:
        stats_text += f"🕐 Последний анализ: <b>{last_scan_time.strftime('%H:%M:%S МСК')}</b>\n"
    else:
        stats_text += "🕐 Последний анализ: <b>еще не проводился</b>\n"
    
    stats_text += (
        f"\n🔔 Рассылка: <b>{config.MORNING_SCAN_HOUR}:{config.MORNING_SCAN_MINUTE:02d} "
        f"и {config.EVENING_SCAN_HOUR}:{config.EVENING_SCAN_MINUTE:02d} МСК</b>"
    )
    
    await update.message.reply_text(stats_text, parse_mode="HTML")

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подписка на рассылку."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    if db.add_subscriber(chat_id, user.username, user.first_name):
        await update.message.reply_text(
            f"✅ <b>Вы подписаны на рассылку!</b>\n\n"
            f"Теперь вы будете получать:\n"
            f"• Утренний анализ в {config.MORNING_SCAN_HOUR}:{config.MORNING_SCAN_MINUTE:02d} МСК\n"
            f"• Вечерний анализ в {config.EVENING_SCAN_HOUR}:{config.EVENING_SCAN_MINUTE:02d} МСК\n\n"
            "Чтобы отписаться, используйте /unsubscribe",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")

async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отписка от рассылки."""
    chat_id = update.effective_chat.id
    
    if db.remove_subscriber(chat_id):
        await update.message.reply_text(
            "❌ <b>Вы отписались от рассылки.</b>\n\n"
            "Вы больше не будете получать автоматические отчеты.\n"
            "Но вы всегда можете запустить анализ вручную!\n\n"
            "Чтобы подписаться снова, используйте /subscribe",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("⚠️ Вы не были подписаны или произошла ошибка.")

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /scan."""
    global last_scan_report, last_scan_time
    
    msg = await update.message.reply_text(
        "🔍 <b>Запускаю анализ рынка...</b>\n\n"
        "⏳ Фильтрация инструментов, загрузка свечей...\n"
        "Это займет 1-2 минуты.",
        parse_mode="HTML"
    )
    
    if update.effective_chat:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing"
        )
    
    try:
        scan_result = await run_full_scan()
        last_scan_report = scan_result
        last_scan_time = datetime.now(MOSCOW_TZ)
        
        await msg.edit_text(scan_result, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка сканирования: {e}", exc_info=True)
        await msg.edit_text(
            "❌ <b>Произошла ошибка при сканировании.</b>\n\n"
            "Попробуйте позже или обратитесь к администратору.",
            parse_mode="HTML"
        )

# ===== Обработчики текстовых сообщений =====

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений (кнопок меню)."""
    text = update.message.text
    
    if text == "🔍 Сканировать рынок":
        await scan_command(update, context)
    elif text == "📊 Статистика":
        await stats_command(update, context)
    elif text == "ℹ️ Помощь":
        await help_command(update, context)
    elif text == "🔔 Подписка":
        chat_id = update.effective_chat.id
        subs = db.get_active_subscribers()
        is_subscribed = chat_id in subs
        
        status = "✅ <b>Вы подписаны</b>" if is_subscribed else "❌ <b>Вы не подписаны</b>"
        
        await update.message.reply_text(
            f"🔔 <b>Управление подпиской</b>\n\n"
            f"Статус: {status}\n\n"
            "Выберите действие:",
            parse_mode="HTML",
            reply_markup=get_subscription_menu()
        )
    else:
        await update.message.reply_text(
            "Используйте кнопки меню или команды.\n"
            "Введите /help для справки."
        )

# ===== Обработчик инлайн-кнопок =====

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на инлайн-кнопки."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "scan":
        global last_scan_report, last_scan_time
        
        await query.edit_message_text(
            "🔍 <b>Запускаю анализ рынка...</b>\n\n"
            "⏳ Фильтрация инструментов, загрузка свечей...",
            parse_mode="HTML"
        )
        
        if update.effective_chat:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action="typing"
            )
        
        try:
            scan_result = await run_full_scan()
            last_scan_report = scan_result
            last_scan_time = datetime.now(MOSCOW_TZ)
            
            await query.edit_message_text(scan_result, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка сканирования: {e}", exc_info=True)
            await query.edit_message_text(
                "❌ <b>Ошибка при сканировании.</b>\n\n"
                "Попробуйте позже.",
                parse_mode="HTML",
                reply_markup=get_inline_main_menu()
            )
    
    elif query.data == "stats":
        stats = db.get_stats()
        current_time = datetime.now(MOSCOW_TZ)
        
        stats_text = (
            "📊 <b>Статистика бота «Молоток»</b>\n\n"
            f"👥 Активных подписчиков: <b>{stats['active']}</b>\n"
            f"📝 Всего пользователей: <b>{stats['total']}</b>\n"
            f"⏰ Время сервера: <b>{current_time.strftime('%H:%M МСК')}</b>\n"
            f"📅 Дата: <b>{current_time.strftime('%d.%m.%Y')}</b>\n\n"
        )
        
        if last_scan_time:
            stats_text += f"🕐 Последний анализ: <b>{last_scan_time.strftime('%H:%M:%S МСК')}</b>"
        else:
            stats_text += "🕐 Последний анализ: <b>еще не проводился</b>"
        
        await query.edit_message_text(
            stats_text,
            parse_mode="HTML",
            reply_markup=get_inline_main_menu()
        )
    
    elif query.data == "last_report":
        if last_scan_report and last_scan_time:
            await query.edit_message_text(
                f"📋 <b>Последний отчет</b>\n"
                f"🕐 Время: {last_scan_time.strftime('%H:%M:%S МСК')}\n\n"
                f"{last_scan_report}",
                parse_mode="HTML"
            )
        else:
            await query.edit_message_text(
                "📋 <b>Отчетов пока нет</b>\n\n"
                "Запустите первый анализ!",
                parse_mode="HTML",
                reply_markup=get_inline_main_menu()
            )
    
    elif query.data == "subscription":
        chat_id = query.message.chat_id
        subs = db.get_active_subscribers()
        is_subscribed = chat_id in subs
        
        status = "✅ <b>Вы подписаны</b>" if is_subscribed else "❌ <b>Вы не подписаны</b>"
        
        await query.edit_message_text(
            f"🔔 <b>Управление подпиской</b>\n\n"
            f"Статус: {status}\n\n"
            "Выберите действие:",
            parse_mode="HTML",
            reply_markup=get_subscription_menu()
        )
    
    elif query.data == "sub_on":
        user = query.from_user
        chat_id = query.message.chat_id
        
        if db.add_subscriber(chat_id, user.username, user.first_name):
            await query.edit_message_text(
                f"✅ <b>Вы успешно подписались!</b>\n\n"
                f"Отчеты будут приходить в {config.MORNING_SCAN_HOUR}:{config.MORNING_SCAN_MINUTE:02d} "
                f"и {config.EVENING_SCAN_HOUR}:{config.EVENING_SCAN_MINUTE:02d} МСК",
                parse_mode="HTML",
                reply_markup=get_inline_main_menu()
            )
        else:
            await query.edit_message_text(
                "❌ Ошибка подписки. Попробуйте позже.",
                parse_mode="HTML",
                reply_markup=get_subscription_menu()
            )
    
    elif query.data == "sub_off":
        chat_id = query.message.chat_id
        
        if db.remove_subscriber(chat_id):
            await query.edit_message_text(
                "❌ <b>Вы отписались от рассылки.</b>\n\n"
                "Вы всегда можете подписаться снова!",
                parse_mode="HTML",
                reply_markup=get_inline_main_menu()
            )
        else:
            await query.edit_message_text(
                "⚠️ Ошибка отписки. Попробуйте позже.",
                parse_mode="HTML",
                reply_markup=get_subscription_menu()
            )
    
    elif query.data == "sub_status":
        chat_id = query.message.chat_id
        subs = db.get_active_subscribers()
        is_subscribed = chat_id in subs
        
        status_text = (
            f"🔔 <b>Статус подписки</b>\n\n"
            f"Текущий статус: {'✅ Подписан' if is_subscribed else '❌ Не подписан'}\n"
            f"ID чата: <code>{chat_id}</code>\n\n"
        )
        
        if is_subscribed:
            status_text += "Вы будете получать автоматические отчеты."
        else:
            status_text += "Вы не будете получать автоматические отчеты."
        
        await query.edit_message_text(
            status_text,
            parse_mode="HTML",
            reply_markup=get_subscription_menu()
        )
    
    elif query.data == "main_menu":
        await query.edit_message_text(
            "🤖 <b>Главное меню бота «Молоток»</b>\n\n"
            "Выберите действие:",
            parse_mode="HTML",
            reply_markup=get_inline_main_menu()
        )

# ===== Бизнес-логика сканирования =====

async def run_full_scan():
    """
    Основная логика сканирования рынка с подробной диагностикой.
    """
    try:
        # ДИАГНОСТИКА: Загружаем свечи SBER
        diagnose_sber_candles()
        
        # Шаг 1: Получаем отфильтрованный список тикеров
        logger.info("\n" + "🔍 " + "=" * 58)
        logger.info("🔍 НАЧАЛО ПОЛНОГО СКАНИРОВАНИЯ")
        logger.info("🔍 " + "=" * 58)
        
        tickers_df = get_filtered_tickers()
        
        if tickers_df.empty:
            logger.error("❌ КРИТИЧЕСКАЯ ОШИБКА: Не удалось загрузить список инструментов")
            return (
                "⚠️ <b>Не удалось загрузить список инструментов.</b>\n\n"
                "Возможно, API Мосбиржи недоступно.\n"
                "Попробуйте позже."
            )
        
        total_loaded = len(tickers_df)
        logger.info(f"\n📊 НАЧАЛО ФИЛЬТРАЦИИ {total_loaded} бумаг")
        logger.info("-" * 60)
        
        # Шаг 2: Применяем фильтры к каждому тикеру
        filtered_tickers = []
        skipped = {
            'no_candles': 0,
            'not_share': 0,
            'low_volume': 0,
            'low_price': 0,
            'api_error': 0
        }
        
        examples_passed = []
        examples_low_volume = []
        examples_low_price = []
        
        for idx, row in tickers_df.iterrows():
            try:
                ticker = row['ticker']
                lot_size = row['lot_size']
                short_name = row['short_name']
                sec_type = row.get('sec_type', '')
                
                # Фильтр 1: Тип инструмента
                if not is_valid_share_type(sec_type):
                    skipped['not_share'] += 1
                    continue
                
                # Загружаем свечи
                candles = get_daily_candles(ticker, days=60)
                if candles is None or len(candles) < 60:
                    skipped['no_candles'] += 1
                    continue
                
                # Получаем последнюю свечу
                last_candle = candles.iloc[-1]
                close_price = float(last_candle['close'])
                
                # Фильтр 2: Минимальная цена
                if close_price <= config.MIN_PRICE:
                    skipped['low_price'] += 1
                    if len(examples_low_price) < 5:
                        examples_low_price.append(f"{ticker} ({close_price:.2f}₽)")
                    continue
                
                # Фильтр 3: Ликвидность
                avg_vol_rub = calculate_average_volume_rub(candles, lot_size)
                if avg_vol_rub < config.MIN_AVG_VOLUME_RUB:
                    skipped['low_volume'] += 1
                    if len(examples_low_volume) < 5:
                        examples_low_volume.append(f"{ticker} ({avg_vol_rub:,.0f}₽/день)")
                    continue
                
                # Бумага прошла все фильтры!
                filtered_tickers.append({
                    'ticker': ticker,
                    'short_name': short_name,
                    'lot_size': lot_size,
                    'candles': candles
                })
                
                if len(examples_passed) < 10:
                    examples_passed.append(f"{ticker} ({short_name}) - цена: {close_price:.2f}₽")
                
            except Exception as e:
                skipped['api_error'] += 1
                if skipped['api_error'] <= 3:
                    logger.error(f"Ошибка обработки {ticker}: {e}")
                continue
        
        # ДИАГНОСТИКА: Итоги фильтрации
        logger.info("\n" + "📊 " + "=" * 58)
        logger.info("📊 ИТОГИ ФИЛЬТРАЦИИ")
        logger.info("📊 " + "=" * 58)
        logger.info(f"📥 Загружено акций (после фильтра типа): {total_loaded}")
        logger.info(f"❌ Нет свечей/мало данных: {skipped['no_candles']}")
        logger.info(f"❌ Цена < {config.MIN_PRICE}₽: {skipped['low_price']}")
        logger.info(f"❌ Объем < {config.MIN_AVG_VOLUME_RUB:,.0f}₽: {skipped['low_volume']}")
        logger.info(f"❌ Ошибки API: {skipped['api_error']}")
        logger.info(f"✅ ОСТАЛОСЬ ДЛЯ АНАЛИЗА: {len(filtered_tickers)}")
        
        if examples_passed:
            logger.info(f"\n✅ Примеры ПРОШЕДШИХ все фильтры (первые 10):")
            for ex in examples_passed:
                logger.info(f"   {ex}")
        
        if examples_low_price:
            logger.info(f"\n📉 Примеры отсеянных по цене (<{config.MIN_PRICE}₽):")
            for ex in examples_low_price:
                logger.info(f"   {ex}")
        
        if examples_low_volume:
            logger.info(f"\n📉 Примеры отсеянных по объему (<{config.MIN_AVG_VOLUME_RUB:,.0f}₽):")
            for ex in examples_low_volume:
                logger.info(f"   {ex}")
        
        if len(filtered_tickers) == 0:
            logger.warning("\n⚠️ ПОСЛЕ ФИЛЬТРАЦИИ НЕ ОСТАЛОСЬ БУМАГ ДЛЯ АНАЛИЗА!")
        
        logger.info("📊 " + "=" * 58 + "\n")
        
        # Шаг 3: Поиск паттерна
        if len(filtered_tickers) == 0:
            now_moscow = datetime.now(MOSCOW_TZ)
            date_str = now_moscow.strftime("%a, %d.%m.%Y")
            time_str = now_moscow.strftime("%H:%M МСК")
            
            return (
                f"📅 *Ежедневный обзор «Молот» ({date_str})*\n"
                f"🕐 Время: {time_str}\n"
                f"📊 Проанализировано бумаг: 0\n"
                f"❌ Качественных сигналов не найдено.\n\n"
                f"💡 После фильтрации не осталось бумаг для анализа.\n"
                f"Возможные причины:\n"
                f"• Выходной день на бирже\n"
                f"• Все бумаги ниже порога ликвидности\n"
                f"• Технический сбой API\n\n"
                f"Попробуйте позже в торговый день."
            )
        
        logger.info(f"🔍 НАЧАЛО ПОИСКА ПАТТЕРНОВ среди {len(filtered_tickers)} бумаг")
        
        candidates = []
        analyzed = 0
        patterns_found = 0
        
        for item in filtered_tickers:
            try:
                pattern_result = find_hammer(item['candles'])
                
                if pattern_result:
                    pattern_result['ticker'] = item['ticker']
                    pattern_result['short_name'] = item['short_name']
                    candidates.append(pattern_result)
                    patterns_found += 1
                
                analyzed += 1
                if analyzed % 50 == 0:
                    logger.info(f"   Прогресс: {analyzed}/{len(filtered_tickers)} | Найдено: {patterns_found}")
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Ошибка анализа {item['ticker']}: {e}")
                continue
        
        logger.info(f"✅ АНАЛИЗ ЗАВЕРШЕН: найдено {len(candidates)} паттернов")
        logger.info("=" * 60 + "\n")
        
        # Шаг 4: Сортировка и форматирование
        candidates.sort(key=lambda x: x['score'], reverse=True)
        top_candidates = candidates[:config.TOP_LIMIT]
        
        now_moscow = datetime.now(MOSCOW_TZ)
        date_str = now_moscow.strftime("%a, %d.%m.%Y")
        time_str = now_moscow.strftime("%H:%M МСК")
        
        report_lines = [
            f"📅 *Ежедневный обзор «Молот» ({date_str})*",
            f"🕐 Время: {time_str}",
            f"📊 Проанализировано бумаг: {len(filtered_tickers)}",
        ]
        
        if top_candidates:
            report_lines.append(f"✅ Найдено качественных сигналов: {len(candidates)}")
            report_lines.append("")
            
            medals = ["🥇", "🥈", "🥉"] + ["  "] * 7
            
            for i, c in enumerate(top_candidates):
                lines = [
                    f"{medals[i]} *{i+1}. {c['ticker']}* ({c['short_name']})",
                    f"   📈 Score: *{c['score']}*",
                    f"   💰 Цена: {c['close']:.2f} ₽ | Тело: {c['body_pct']:.1f}% | Тень: {c['shadow_pct']:.1f}%",
                    f"   📉 Поддержка: {c['support']:.2f} ₽ | Объем: {c['volume_ratio']:.1f}x от среднего",
                    ""
                ]
                report_lines.extend(lines)
            
            report_lines.append(
                "💡 *Что делать с сигналами?*\n"
                "Проверь график в Т-Инвестициях. Если «Молот» подтверждается визуально — "
                "выставляй лимитную заявку со стоп-лоссом -2%."
            )
        else:
            report_lines.append("❌ Качественных сигналов не найдено.")
            report_lines.append("")
            report_lines.append(
                "💡 Рынок не дает надёжных разворотных паттернов. "
                "Сегодня без сделок. Жди следующий день."
            )
        
        return "\n".join(report_lines)
        
    except Exception as e:
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}", exc_info=True)
        return f"⚠️ Ошибка при сканировании: {str(e)[:200]}"

async def scheduled_scan(context: ContextTypes.DEFAULT_TYPE):
    """Задача для автоматической рассылки."""
    global last_scan_report, last_scan_time
    
    logger.info("📅 Запуск планового сканирования...")
    
    subscribers = db.get_active_subscribers()
    if not subscribers:
        logger.warning("Нет активных подписчиков")
        return
    
    try:
        scan_result = await run_full_scan()
        last_scan_report = scan_result
        last_scan_time = datetime.now(MOSCOW_TZ)
        
        success = 0
        for chat_id in subscribers:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=scan_result,
                    parse_mode="HTML"
                )
                success += 1
            except Exception as e:
                logger.error(f"Ошибка отправки {chat_id}: {e}")
                if "bot was blocked" in str(e).lower():
                    db.remove_subscriber(chat_id)
        
        logger.info(f"Рассылка завершена: {success}/{len(subscribers)}")
        
    except Exception as e:
        logger.error(f"Ошибка плановой рассылки: {e}", exc_info=True)

# ===== Инициализация бота =====

async def setup_bot():
    """Настройка и запуск бота."""
    if not config.TELEGRAM_TOKEN or config.TELEGRAM_TOKEN == "YOUR_TOKEN_HERE":
        logger.error("❌ Не указан TELEGRAM_BOT_TOKEN!")
        raise ValueError("TELEGRAM_BOT_TOKEN не установлен")
    
    application = Application.builder().token(config.TELEGRAM_TOKEN).build()
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("scan", scan_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
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
    
    logger.info(
        f"⏰ Планировщик запущен: "
        f"{config.MORNING_SCAN_HOUR}:{config.MORNING_SCAN_MINUTE:02d} и "
        f"{config.EVENING_SCAN_HOUR}:{config.EVENING_SCAN_MINUTE:02d} МСК"
    )
    
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

if __name__ == "__main__":
    asyncio.run(main())
