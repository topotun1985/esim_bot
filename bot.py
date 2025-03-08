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

from handlers.start import router as start_router
from handlers.catalog import router as catalog_router
from database.models import Base
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

# Функция конфигурирования и запуска бота
async def main():
    # Создаем объекты для хранения сервисов
    bot = None
    session_pool = None
    
    # Функция для корректного завершения работы
    async def shutdown(signal_type=None):
        nonlocal bot, session_pool
        
        logger.info(f'Received signal {signal_type}, shutting down...')
        
        # Закрываем пул сессий
        if session_pool:
            await session_pool.close()
            logger.info('Database session pool closed')
        
        # Закрываем сессию бота
        if bot:
            with suppress(Exception):
                await bot.session.close()
                logger.info('Bot session closed')
        
        # Останавливаем event loop
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        [task.cancel() for task in tasks]
        logger.info(f'Cancelling {len(tasks)} outstanding tasks')
        await asyncio.gather(*tasks, return_exceptions=True)
        asyncio.get_event_loop().stop()
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
        # Здесь можно добавить другие роутеры, когда они будут созданы
        # dp.include_router(account_router)
        # dp.include_router(support_router)
        # dp.include_router(admin_router)
        
        # Установка команд бота
        await set_bot_commands(bot)
        
        # Синхронизация данных стран и пакетов из API
        async with session_pool() as session:
            logger.info("🔄 Начинаем синхронизацию стран и пакетов из API...")
            
            # Сначала синхронизируем только страны
            from database.queries import get_all_countries
            
            # Пробуем синхронизировать страны с несколькими попытками
            max_attempts = 3
            attempt = 1
            success = False
            
            while attempt <= max_attempts and not success:
                try:
                    logger.info(f"Синхронизация стран: попытка {attempt} из {max_attempts}")
                    success = await esim_service.sync_countries_and_packages(session, sync_packages=False)
                    
                    if success:
                        logger.info("✅ Синхронизация стран завершена успешно!")
                        break
                    else:
                        logger.warning(f"⚠️ Попытка {attempt} синхронизации стран не удалась")
                except Exception as e:
                    logger.error(f"❌ Ошибка при синхронизации стран (попытка {attempt}): {e}")
                
                attempt += 1
                if attempt <= max_attempts and not success:
                    # Ждем перед следующей попыткой
                    logger.info(f"⏳ Ожидание перед попыткой {attempt}...")
                    await asyncio.sleep(3)
            
            # Теперь синхронизируем пакеты для всех стран из базы данных
            countries = await get_all_countries(session)
            logger.info(f"🌎 В базе данных {len(countries)} стран")
            
            # Синхронизируем пакеты для каждой страны
            total_packages = 0
            countries_with_packages = 0
            countries_processed = 0
            
            for country in countries:
                countries_processed += 1
                logger.info(f"🔄 Синхронизация пакетов для страны {country.code} ({countries_processed}/{len(countries)})")
                
                # Синхронизируем пакеты для текущей страны
                packages_success = await esim_service.sync_packages_for_country(session, country)
                
                # Проверяем результаты синхронизации для этой страны
                from database.queries import get_packages_by_country
                packages = await get_packages_by_country(session, country.id)
                total_packages += len(packages)
                
                if len(packages) > 0:
                    countries_with_packages += 1
                    logger.info(f"✅ Получено {len(packages)} пакетов для страны {country.code}")
                else:
                    logger.warning(f"⚠️ Нет пакетов для страны {country.code}")
            
            logger.info(f"💾 Всего в базе данных {total_packages} пакетов для {countries_with_packages} стран")
                        break
                    else:
                        logger.warning(f"⚠️ Попытка {attempt} синхронизации не удалась")
                except Exception as e:
                    logger.error(f"❌ Ошибка при синхронизации (попытка {attempt}): {e}")
                
                attempt += 1
                if attempt <= max_attempts and not success:
                    # Ждем перед следующей попыткой
                    logger.info(f"⏳ Ожидание перед попыткой {attempt}...")
                    await asyncio.sleep(3)
            
            if not success:
                logger.error("❌ Все попытки синхронизации завершились неудачей")
        
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