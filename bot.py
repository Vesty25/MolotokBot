# bot.py
import asyncio
import logging
from datetime import datetime
import pytz
from aiohttp import web

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import config
from database import SubscriberDB
from moex_parser import get_all_tickers, get_daily_candles, calculate_average_volume_rub
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

# ===== Веб-сервер для Render =====

async def health_check(request):
    """Эндпоинт для проверки здоровья сервера."""
    return web.Response(text="OK", status=200)

async def ping(request):
    """Эндпоинт для UptimeRobot с информацией о состоянии."""
    stats = db.get_stats()
    return web.json_response({
        "status": "alive",
        "timestamp": datetime.now(MOSCOW_TZ).isoformat(),
        "subscribers": stats,
        "bot_active": True
    })

def create_web_app():
    """Создание веб-приложения aiohttp."""
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/ping', ping)
    return app

# ===== Telegram Bot Handlers =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # Добавляем пользователя в БД
    db.add_subscriber(
        chat_id=chat_id,
        username=user.username,
        first_name=user.first_name
    )
    
    keyboard = [
        [InlineKeyboardButton("🔍 Запросить анализ", callback_data="scan")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("❌ Отписаться", callback_data="unsubscribe")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👋 Привет! Я бот «Молоток».\n\n"
        "🔨 Я ищу на Московской бирже акции с бычьим паттерном «Молот» на уровне поддержки.\n\n"
        "📅 Автоматическая рассылка: 10:30 и 19:30 МСК\n"
        "🔍 Ручной запуск: кнопка ниже или команда /scan\n\n"
        "💡 Используйте /help для справки",
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка по командам."""
    help_text = (
        "🤖 <b>Команды бота «Молоток»:</b>\n\n"
        "/start - Запуск бота и подписка\n"
        "/scan - Ручной запуск анализа\n"
        "/stats - Статистика подписчиков\n"
        "/unsubscribe - Отписаться от рассылки\n"
        "/help - Это сообщение\n\n"
        "📅 <b>Автоматическая рассылка:</b>\n"
        "• Утро: 10:30 МСК\n"
        "• Вечер: 19:30 МСК\n\n"
        "🔍 <b>Что ищет бот:</b>\n"
        "• Акции у локального минимума (60 дней)\n"
        "• Бычий «Молот» с длинной нижней тенью\n"
        "• Объем выше среднего (подтверждение)\n"
        "• Только ликвидные бумаги (>10 млн руб/день)"
    )
    await update.message.reply_text(help_text, parse_mode="HTML")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статистику."""
    stats = db.get_stats()
    await update.message.reply_text(
        f"📊 <b>Статистика бота:</b>\n\n"
        f"👥 Активных подписчиков: {stats['active']}\n"
        f"📝 Всего пользователей: {stats['total']}\n"
        f"⏰ Время сервера: {datetime.now(MOSCOW_TZ).strftime('%H:%M МСК')}",
        parse_mode="HTML"
    )

async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отписка от рассылки."""
    chat_id = update.effective_chat.id
    if db.remove_subscriber(chat_id):
        await update.message.reply_text(
            "❌ Вы отписались от рассылки. Чтобы подписаться снова, используйте /start"
        )
    else:
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "scan":
        await query.edit_message_text("⏳ Выполняю сканирование рынка... это займет около минуты.")
        try:
            scan_result = await run_full_scan()
            await query.edit_message_text(scan_result, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка сканирования: {e}")
            await query.edit_message_text("❌ Произошла ошибка при сканировании. Попробуйте позже.")
    
    elif query.data == "stats":
        stats = db.get_stats()
        await query.edit_message_text(
            f"📊 <b>Статистика бота:</b>\n\n"
            f"👥 Активных подписчиков: {stats['active']}\n"
            f"📝 Всего пользователей: {stats['total']}\n"
            f"⏰ Время сервера: {datetime.now(MOSCOW_TZ).strftime('%H:%M МСК')}",
            parse_mode="HTML"
        )
    
    elif query.data == "unsubscribe":
        chat_id = update.effective_chat.id
        if db.remove_subscriber(chat_id):
            await query.edit_message_text("❌ Вы успешно отписались от рассылки. Используйте /start чтобы подписаться снова.")
        else:
            await query.edit_message_text("⚠️ Ошибка при отписке. Попробуйте позже.")

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /scan."""
    msg = await update.message.reply_text("⏳ Анализирую акции Московской биржи...")
    try:
        scan_result = await run_full_scan()
        await msg.edit_text(scan_result, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка сканирования: {e}")
        await msg.edit_text("❌ Произошла ошибка при сканировании.")

# ===== Бизнес-логика сканирования =====

async def run_full_scan():
    """Основная логика сканирования рынка."""
    try:
        # Получаем тикеры
        all_tickers_df = get_all_tickers()
        total_tickers = len(all_tickers_df)
        logger.info(f"Загружено {total_tickers} тикеров с MOEX")
        
        # Анализ тикеров
        candidates = []
        processed = 0
        errors = 0
        
        for idx, row in all_tickers_df.iterrows():
            try:
                ticker = row['ticker']
                lot_size = row['lot_size']
                short_name = row['short_name']
                
                # Загружаем свечи
                candles = get_daily_candles(ticker, days=60)
                if candles is None or len(candles) < 60:
                    continue
                
                # Проверка ликвидности
                avg_vol_rub = calculate_average_volume_rub(candles, lot_size)
                if avg_vol_rub < config.MIN_AVG_VOLUME_RUB:
                    continue
                
                # Поиск паттерна
                pattern_result = find_hammer(candles)
                if pattern_result:
                    pattern_result['ticker'] = ticker
                    pattern_result['short_name'] = short_name
                    candidates.append(pattern_result)
                
                processed += 1
                if processed % 50 == 0:
                    logger.info(f"Обработано {processed}/{total_tickers}...")
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                errors += 1
                logger.error(f"Ошибка обработки {ticker}: {e}")
                continue
        
        logger.info(f"Сканирование завершено. Найдено сигналов: {len(candidates)}, ошибок: {errors}")
        
        # Сортировка и форматирование
        candidates.sort(key=lambda x: x['score'], reverse=True)
        top_candidates = candidates[:config.TOP_LIMIT]
        
        # Формирование отчета
        now_moscow = datetime.now(MOSCOW_TZ)
        date_str = now_moscow.strftime("%a, %d.%m")
        
        report_lines = [
            f"📅 <b>Обзор «Молот» ({date_str})</b>",
            f"📊 Проанализировано: {total_tickers} | Сигналов: {len(candidates)} | Топ-{min(config.TOP_LIMIT, len(top_candidates))}\n"
        ]
        
        medals = ["🥇", "🥈", "🥉"] + ["  "] * 7
        
        for i, c in enumerate(top_candidates):
            line = (
                f"{medals[i]} <b>{i+1}. {c['ticker']} ({c['short_name']})</b>\n"
                f"   📈 Score: <b>{c['score']}</b>\n"
                f"   💰 Цена: {c['close']:.2f} ₽ | Тело: {c['body_pct']:.1f}% | Тень: {c['shadow_pct']:.1f}%\n"
                f"   📉 Поддержка: {c['support']:.2f} ₽ | Объем: {c['volume_ratio']:.1f}x ✅"
            )
            report_lines.append(line)
        
        if not top_candidates:
            report_lines.append("❌ Качественных паттернов «Молот» на ликвидных бумагах сегодня не найдено.")
        
        return "\n\n".join(report_lines)
        
    except Exception as e:
        logger.error(f"Критическая ошибка сканирования: {e}", exc_info=True)
        return f"⚠️ Ошибка при сканировании: {str(e)[:200]}"

async def scheduled_scan(context: ContextTypes.DEFAULT_TYPE):
    """Задача для автоматической рассылки."""
    logger.info("Запуск планового сканирования...")
    
    subscribers = db.get_active_subscribers()
    if not subscribers:
        logger.warning("Нет активных подписчиков")
        return
    
    try:
        scan_result = await run_full_scan()
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
                # Если бот заблокирован пользователем - отписываем
                if "bot was blocked" in str(e).lower() or "deactivated" in str(e).lower():
                    db.remove_subscriber(chat_id)
                    logger.info(f"Подписчик {chat_id} удален (заблокировал бота)")
        
        logger.info(f"Рассылка завершена: {success}/{len(subscribers)}")
        
    except Exception as e:
        logger.error(f"Ошибка плановой рассылки: {e}", exc_info=True)

async def setup_bot():
    """Настройка и запуск бота."""
    # Проверка токена
    if not config.TELEGRAM_TOKEN or config.TELEGRAM_TOKEN == "YOUR_TOKEN_HERE":
        logger.error("❌ Не указан TELEGRAM_BOT_TOKEN!")
        raise ValueError("TELEGRAM_BOT_TOKEN не установлен")
    
    # Создание приложения Telegram
    application = Application.builder().token(config.TELEGRAM_TOKEN).build()
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("scan", scan_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Настройка планировщика
    scheduler = AsyncIOScheduler(timezone=MOSCOW_TZ)
    scheduler.add_job(
        scheduled_scan,
        trigger=CronTrigger(
            hour=config.MORNING_SCAN_HOUR,
            minute=config.MORNING_SCAN_MINUTE
        ),
        args=[application],
        id="morning_scan",
        replace_existing=True
    )
    scheduler.add_job(
        scheduled_scan,
        trigger=CronTrigger(
            hour=config.EVENING_SCAN_HOUR,
            minute=config.EVENING_SCAN_MINUTE
        ),
        args=[application],
        id="evening_scan",
        replace_existing=True
    )
    scheduler.start()
    logger.info(f"⏰ Планировщик запущен: {config.MORNING_SCAN_HOUR}:{config.MORNING_SCAN_MINUTE:02d} и {config.EVENING_SCAN_HOUR}:{config.EVENING_SCAN_MINUTE:02d} МСК")
    
    # Инициализация бота
    await application.initialize()
    await application.start()
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    
    logger.info("🤖 Бот запущен и готов к работе!")
    
    return application

async def main():
    """Главная функция - запуск веб-сервера и бота."""
    try:
        # Запускаем бота
        application = await setup_bot()
        
        # Запускаем веб-сервер
        web_app = create_web_app()
        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', config.PORT)
        await site.start()
        logger.info(f"🌐 Веб-сервер запущен на порту {config.PORT}")
        
        # Держим приложение запущенным
        # Создаем событие, которое никогда не завершится
        stop_event = asyncio.Event()
        await stop_event.wait()
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        raise
    finally:
        # Корректное завершение
        if 'application' in locals():
            await application.stop()
            await application.shutdown()

if __name__ == "__main__":
    # Запускаем приложение
    asyncio.run(main())
