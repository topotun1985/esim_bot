import asyncio
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Настраиваем логгер
logging.basicConfig(
    level=logging.INFO, 
    format='[%(asctime)s] #%(levelname)-8s %(filename)s:%(lineno)d - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Получаем URL базы данных из переменных окружения
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:Vadim22021985@db:5432/esim_bot")

# Migration SQL statements для PostgreSQL
MIGRATION_SQL = [
    """
    -- Проверяем, существует ли столбец invoice_id в таблице orders
    SELECT COUNT(*) 
    FROM information_schema.columns 
    WHERE table_name = 'orders' AND column_name = 'invoice_id';
    """,
    """
    -- Если столбец invoice_id не существует, добавляем его
    ALTER TABLE orders ADD COLUMN invoice_id VARCHAR(255);
    """,
    """
    -- Проверяем, существует ли столбец payment_details в таблице orders
    SELECT COUNT(*) 
    FROM information_schema.columns 
    WHERE table_name = 'orders' AND column_name = 'payment_details';
    """,
    """
    -- Если столбец payment_details не существует, добавляем его
    ALTER TABLE orders ADD COLUMN payment_details TEXT;
    """,
    """
    -- Проверяем, существует ли столбец paid_at в таблице orders
    SELECT COUNT(*) 
    FROM information_schema.columns 
    WHERE table_name = 'orders' AND column_name = 'paid_at';
    """,
    """
    -- Если столбец paid_at не существует, добавляем его
    ALTER TABLE orders ADD COLUMN paid_at TIMESTAMP;
    """,
    """
    -- Проверяем, существует ли столбец retail_price в таблице packages
    SELECT COUNT(*) 
    FROM information_schema.columns 
    WHERE table_name = 'packages' AND column_name = 'retail_price';
    """,
    """
    -- Если столбец retail_price не существует, добавляем его
    ALTER TABLE packages ADD COLUMN retail_price FLOAT;
    """,
    """
    -- Проверяем, существует ли столбец last_synced_at в таблице packages
    SELECT COUNT(*) 
    FROM information_schema.columns 
    WHERE table_name = 'packages' AND column_name = 'last_synced_at';
    """,
    """
    -- Если столбец last_synced_at не существует, добавляем его
    ALTER TABLE packages ADD COLUMN last_synced_at TIMESTAMP;
    """,
    """
    -- Проверяем, существует ли столбец name_ru в таблице countries
    SELECT COUNT(*) 
    FROM information_schema.columns 
    WHERE table_name = 'countries' AND column_name = 'name_ru';
    """,
    """
    -- Если столбец name_ru не существует, добавляем его
    ALTER TABLE countries ADD COLUMN name_ru VARCHAR(255);
    """
]

async def run_migrations():
    """Запускает миграции для добавления новых полей в таблицы orders и packages"""
    # Создаем асинхронный движок SQLAlchemy
    engine = create_async_engine(DATABASE_URL)
    
    # Создаем фабрику сессий
    async_session = sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    
    # Выполняем миграции в транзакции
    async with async_session() as session:
        try:
            # Проверяем наличие столбца invoice_id
            result = await session.execute(text(MIGRATION_SQL[0]))
            has_invoice_id = result.fetchone()[0] > 0
            
            if not has_invoice_id:
                logger.info("Adding 'invoice_id' column to orders table")
                await session.execute(text(MIGRATION_SQL[1]))
            else:
                logger.info("Column 'invoice_id' already exists in orders table")
            
            # Проверяем наличие столбца payment_details
            result = await session.execute(text(MIGRATION_SQL[2]))
            has_payment_details = result.fetchone()[0] > 0
            
            if not has_payment_details:
                logger.info("Adding 'payment_details' column to orders table")
                await session.execute(text(MIGRATION_SQL[3]))
            else:
                logger.info("Column 'payment_details' already exists in orders table")
            
            # Проверяем наличие столбца paid_at
            result = await session.execute(text(MIGRATION_SQL[4]))
            has_paid_at = result.fetchone()[0] > 0
            
            if not has_paid_at:
                logger.info("Adding 'paid_at' column to orders table")
                await session.execute(text(MIGRATION_SQL[5]))
            else:
                logger.info("Column 'paid_at' already exists in orders table")
            
            # Проверяем наличие столбца retail_price
            result = await session.execute(text(MIGRATION_SQL[6]))
            has_retail_price = result.fetchone()[0] > 0
            
            if not has_retail_price:
                logger.info("Adding 'retail_price' column to packages table")
                await session.execute(text(MIGRATION_SQL[7]))
            else:
                logger.info("Column 'retail_price' already exists in packages table")
            
            # Проверяем наличие столбца last_synced_at
            result = await session.execute(text(MIGRATION_SQL[8]))
            has_last_synced_at = result.fetchone()[0] > 0
            
            if not has_last_synced_at:
                logger.info("Adding 'last_synced_at' column to packages table")
                await session.execute(text(MIGRATION_SQL[9]))
            else:
                logger.info("Column 'last_synced_at' already exists in packages table")
                
            # Проверяем наличие столбца name_ru
            result = await session.execute(text(MIGRATION_SQL[10]))
            has_name_ru = result.fetchone()[0] > 0
            
            if not has_name_ru:
                logger.info("Adding 'name_ru' column to countries table")
                await session.execute(text(MIGRATION_SQL[11]))
            else:
                logger.info("Column 'name_ru' already exists in countries table")
            
            # Сохраняем изменения
            await session.commit()
            logger.info("Migrations completed successfully")
        except Exception as e:
            await session.rollback()
            logger.error(f"Error during migrations: {e}")
            raise
    
    # Закрываем соединение с базой данных
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run_migrations())
