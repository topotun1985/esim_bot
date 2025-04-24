import os
import asyncio
import logging
import signal
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeDefault
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from aiohttp import web
import datetime
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
import json

from handlers.start import router as start_router
from handlers.catalog import router as catalog_router
from handlers.payment import router as payment_router
from handlers.account import router as account_router
from handlers.admin import router as admin_router
from handlers.webhook import setup_webhook_server
from database.models import Base, ESim, Order, User
from database.queries import get_all_countries
from services.esim_service import esim_service

from contextlib import suppress


load_dotenv()

# Настраиваем базовую конфигурацию логирования
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] #%(levelname)-8s %(filename)s:'
           '%(lineno)d - %(name)s - %(message)s'
)

# Инициализируем логгер модуля
logger = logging.getLogger(__name__)

# Определение базовых команд бота
BOT_COMMANDS = [
    ("start", "Запустить бота / Start the bot"),
    ("menu", "Главное меню / Main menu"),
    ("help", "Помощь / Help"),
]


async def create_db_and_tables():
    """Создает базу данных и таблицы, если они не существуют"""
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./esim_bot.db")
    engine = create_async_engine(DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database and tables created successfully")
    return engine


def get_commands_for_language(language_code: str) -> list[BotCommand]:
    """Создает список команд для конкретного языка."""
    commands_dict = {
        "ru": [
            BotCommand(command="start", description="Запустить бота"),
            BotCommand(command="menu", description="Главное меню"),
            BotCommand(command="help", description="Помощь"),
        ],
        "en": [
            BotCommand(command="start", description="Start the bot"),
            BotCommand(command="menu", description="Main menu"),
            BotCommand(command="help", description="Help"),
        ]
    }

    return commands_dict.get(language_code, commands_dict["en"])


async def set_bot_commands(bot: Bot):
    """Устанавливает команды бота для каждого поддерживаемого языка."""
    # Список поддерживаемых языков
    supported_languages = ["ru", "en"]

    try:
        # Удаляем глобальные команды (без языка)
        await bot.delete_my_commands(scope=BotCommandScopeDefault())

        # Удаляем команды для каждого языка
        for lang in supported_languages:
            try:
                await bot.delete_my_commands(
                    scope=BotCommandScopeDefault(),
                    language_code=lang
                )
            except Exception as e:
                logger.warning(f"Failed to delete commands for {lang}: {e}")

        # Устанавливаем команды для каждого языка
        for lang in supported_languages:
            try:
                # Получаем локализованные команды
                commands = get_commands_for_language(lang)

                # Устанавливаем команды для конкретного языка
                await bot.set_my_commands(
                    commands,
                    scope=BotCommandScopeDefault(),
                    language_code=lang
                )
                logger.info(f"Set commands for language: {lang}")
            except Exception as e:
                logger.error(f"Failed to set commands for {lang}: {e}")

        # Устанавливаем английские команды как дефолтные (без указания языка)
        default_commands = get_commands_for_language("en")
        await bot.set_my_commands(default_commands, scope=BotCommandScopeDefault())

    except Exception as e:
        logger.error(f"Failed to set bot commands: {e}")


# Функция для периодической синхронизации пакетов с API
async def periodic_package_sync(session_factory, sync_interval_hours=1):
    """
    Периодически синхронизирует пакеты eSIM с API провайдера

    Args:
        session_factory: Фабрика сессий базы данных
        sync_interval_hours: Интервал синхронизации в часах
    """
    logger.info(f"🔄 Запущена задача периодической синхронизации пакетов. Интервал: {sync_interval_hours} часов")

    while True:
        try:
            # Определяем следующее время синхронизации
            next_sync = datetime.datetime.now() + datetime.timedelta(hours=sync_interval_hours)
            logger.info(f"⏳ Следующая синхронизация пакетов запланирована на: {next_sync.strftime('%Y-%m-%d %H:%M:%S')}")

            # Ждем до следующей синхронизации (конвертируем часы в секунды)
            await asyncio.sleep(sync_interval_hours * 3600)

            # Выполняем синхронизацию
            logger.info("🔄 Начинается плановая синхронизация пакетов...")

            async with session_factory() as session:
                # Вызываем метод синхронизации пакетов из сервиса
                result = await esim_service.sync_packages_with_api(session)

                if result["success"]:
                    logger.info(f"✅ Плановая синхронизация пакетов успешно завершена. "
                                f"Успешно обработано стран: {result.get('success_count', 0)}, "
                                f"Ошибок: {result.get('failed_count', 0)}, "
                                f"Всего пакетов: {result.get('total_packages', 0)}")
                else:
                    error_message = result.get("error", "Неизвестная ошибка")
                    logger.error(f"❌ Ошибка при плановой синхронизации пакетов: {error_message}")

        except Exception as e:
            logger.exception(f"❌ Критическая ошибка в задаче периодической синхронизации: {e}")
            # Ждем некоторое время перед следующей попыткой в случае ошибки
            await asyncio.sleep(900)  # 15 минут


# Фоновые задачи
async def check_esim_balance_task(bot: Bot, session_pool):
    """
    Фоновая задача для проверки баланса eSIM и отправки уведомлений
    при низком балансе трафика
    """
    logger.info("Запущена фоновая задача проверки баланса eSIM")

    # Интервал проверки в секундах (по умолчанию раз в 12 часов)
    check_interval = int(os.getenv("BALANCE_CHECK_INTERVAL", 43200))

    # Порог для уведомления (процент оставшегося трафика)
    low_balance_threshold = float(os.getenv("LOW_BALANCE_THRESHOLD", 20.0))

    while True:
        try:
            async with session_pool() as session:
                # Получаем все активные eSIM
                query = select(ESim).options(
                    joinedload(ESim.order).joinedload(Order.user),
                    joinedload(ESim.order).joinedload(Order.package)
                ).where(
                    ESim.esim_status == "ACTIVATED"
                )

                result = await session.execute(query)
                active_esims = result.scalars().all()

                for esim in active_esims:
                    try:
                        # Проверяем статус eSIM через API
                        esim_status = await esim_service.check_esim_status(
                            esim.esim_tran_no, esim.iccid
                        )

                        if not esim_status.get("success"):
                            continue

                        # Получаем данные о трафике
                        total_volume = esim_status.get("total_volume", 0)
                        used_volume = esim_status.get("order_usage", 0)

                        if total_volume > 0:
                            # Вычисляем процент оставшегося трафика
                            remaining_percent = 100 - (used_volume / total_volume * 100)

                            # Проверяем, не отправляли ли мы уже уведомление
                            # (сохраняем флаг в raw_data)
                            raw_data = esim.raw_data or {}

                            # Если raw_data - строка, декодируем JSON
                            if isinstance(raw_data, str):
                                try:
                                    raw_data = json.loads(raw_data)
                                except json.JSONDecodeError:
                                    raw_data = {}

                            notification_sent = raw_data.get("low_balance_notification_sent", False)

                            # Если баланс низкий и уведомление еще не отправлено
                            if remaining_percent <= low_balance_threshold and not notification_sent:
                                # Отправляем уведомление пользователю
                                await send_low_balance_notification(
                                    bot,
                                    esim,
                                    remaining_percent,
                                    session
                                )

                                # Обновляем флаг в raw_data
                                raw_data["low_balance_notification_sent"] = True
                                esim.raw_data = json.dumps(raw_data)
                                await session.commit()

                            # Если баланс восстановился, сбрасываем флаг
                            elif remaining_percent > low_balance_threshold and notification_sent:
                                raw_data["low_balance_notification_sent"] = False
                                esim.raw_data = json.dumps(raw_data)
                                await session.commit()

                    except Exception as e:
                        logger.error(f"Ошибка при проверке eSIM {esim.iccid}: {str(e)}")
                        continue

        except Exception as e:
            logger.error(f"Ошибка в фоновой задаче проверки баланса: {str(e)}")
            # Отправляем уведомление в админ-канал
            admin_chat_id = os.getenv("ADMIN_CHAT_ID")
            if admin_chat_id:
                await bot.send_message(
                    chat_id=admin_chat_id,
                    text=f"⚠️ Ошибка в фоновой задаче проверки баланса eSIM:\n{str(e)}"
                )

        # Ждем до следующей проверки
        await asyncio.sleep(check_interval)


async def send_low_balance_notification(bot: Bot, esim: ESim, remaining_percent: float, session: AsyncSession):
    """
    Отправляет уведомление пользователю о низком балансе трафика

    Args:
        bot: Экземпляр бота
        esim: Объект eSIM
        remaining_percent: Процент оставшегося трафика
        session: Сессия базы данных
    """
    try:
        # Получаем данные о пользователе и пакете
        order = esim.order
        user = order.user
        package = order.package

        # Форматируем сообщение в зависимости от языка пользователя
        if user.language_code == 'ru':
            message_text = (
                f"⚠️ <b>Внимание! Низкий баланс трафика</b>\n\n"
                f"У вашей eSIM для <b>{package.country.name}</b> осталось всего "
                f"<b>{remaining_percent:.1f}%</b> трафика.\n\n"
                f"ICCID: <code>{esim.iccid}</code>\n"
                f"Пакет: {package.name}\n\n"
                f"Чтобы продлить eSIM или пополнить баланс трафика, "
                f"воспользуйтесь командой /menu и перейдите в раздел 'Мои eSIM'."
            )
        else:
            message_text = (
                f"⚠️ <b>Warning! Low data balance</b>\n\n"
                f"Your eSIM for <b>{package.country.name}</b> has only "
                f"<b>{remaining_percent:.1f}%</b> of data remaining.\n\n"
                f"ICCID: <code>{esim.iccid}</code>\n"
                f"Package: {package.name}\n\n"
                f"To extend your eSIM or top up your data balance, "
                f"use the /menu command and go to 'My eSIMs' section."
            )

        # Отправляем сообщение пользователю
        await bot.send_message(
            chat_id=user.telegram_id,
            text=message_text,
            parse_mode=ParseMode.HTML
        )

        logger.info(f"Отправлено уведомление о низком балансе для eSIM {esim.iccid}")

    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления о низком балансе: {str(e)}")


# Функция конфигурирования и запуска бота
async def main():
    # Создаем объекты для хранения сервисов
    bot = None
    session_pool = None

    # Функция для корректного завершения работы
    async def shutdown(signal_type=None):
        nonlocal bot

        logger.info(f'Received signal {signal_type}, shutting down...')

        # Закрываем пул сессий - не требуется, так как session_pool это функция sessionmaker
        logger.info('Database connections will be closed automatically')

        # Закрываем сессию бота
        if bot:
            with suppress(Exception):
                await bot.session.close()
                logger.info('Bot session closed')

        # Отменяем все задачи, кроме текущей
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        logger.info(f'Cancelling {len(tasks)} outstanding tasks')

        # Отменяем все задачи и ждем их завершения
        for task in tasks:
            task.cancel()

        if tasks:
            # Ждем завершения всех задач с обработкой исключений
            await asyncio.gather(*tasks, return_exceptions=True)

        # Не останавливаем event loop здесь, это произойдет автоматически
        logger.info('Shutdown complete')

    try:
        # Создаем базу данных и таблицы
        engine = await create_db_and_tables()

        # Создаем фабрику сессий
        session_pool = sessionmaker(
            engine, expire_on_commit=False, class_=AsyncSession
        )

        # Инициализируем бота
        bot = Bot(token=os.getenv("BOT_TOKEN", ""),
                  default=DefaultBotProperties(parse_mode=ParseMode.HTML))

        # Выбираем хранилище для FSM (Redis или Memory)
        if os.getenv("USE_REDIS", "False").lower() == "true":
            storage = RedisStorage.from_url(
                os.getenv("REDIS_URL", "redis://localhost:6379/0")
            )
            logger.info("Using Redis storage for FSM")
        else:
            storage = MemoryStorage()
            logger.info("Using Memory storage for FSM")

        # Создаем диспетчера
        dp = Dispatcher(storage=storage)

        # Устанавливаем middleware для передачи сессии БД в хендлеры
        @dp.update.middleware()
        async def db_session_middleware(handler, event, data):
            async with session_pool() as session:
                data["session"] = session
                return await handler(event, data)

        # Регистрируем роутеры
        dp.include_router(start_router)
        dp.include_router(catalog_router)
        dp.include_router(payment_router)
        dp.include_router(account_router)
        dp.include_router(admin_router)
        # Здесь можно добавить другие роутеры, когда они будут созданы
        # dp.include_router(support_router)

        # Установка команд бота
        await set_bot_commands(bot)

        # Синхронизация данных стран и пакетов из API
        # Проверяем, нужно ли запускать синхронизацию при старте
        auto_sync = os.getenv("AUTO_SYNC_ON_STARTUP", "False").lower() == "true"

        # Инициализируем переменные для синхронизации
        max_attempts = 3

        # Запускаем фоновые задачи
        asyncio.create_task(check_esim_balance_task(bot, session_pool))

        # Запуск периодической синхронизации пакетов, если включено
        sync_packages_enabled = os.getenv("ENABLE_PERIODIC_PACKAGE_SYNC", "True").lower() == "true"
        sync_interval_hours = float(os.getenv("PACKAGE_SYNC_INTERVAL_HOURS", "1.0"))

        if sync_packages_enabled:
            logger.info(f"✅ Периодическая синхронизация пакетов включена. Интервал: {sync_interval_hours} часов")
            asyncio.create_task(periodic_package_sync(session_pool, sync_interval_hours))
        else:
            logger.info("❌ Периодическая синхронизация пакетов отключена")

        # Настраиваем и запускаем вебхук-сервер для обработки платежей
        webhook_enabled = os.getenv("ENABLE_WEBHOOKS", "False").lower() == "true"
        if webhook_enabled:
            webhook_port = int(os.getenv("WEBHOOK_PORT", "9091"))
            logger.info(f"Setting up webhook server on port {webhook_port}")
            app = web.Application()
            webhook_runner = await setup_webhook_server(app, bot, session_pool, webhook_port)
            logger.info("Webhook server is running")
        else:
            logger.info("Webhooks are disabled. Set ENABLE_WEBHOOKS=true to enable them.")

        # Запуск бота
        logger.info("Starting bot")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)

    except Exception as e:
        logger.error(f"Critical error: {e}", exc_info=True)
        await shutdown()
        raise
    finally:
        await shutdown()


if __name__ == "__main__":
    asyncio.run(main())