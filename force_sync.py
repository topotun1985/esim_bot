import asyncio
import os
import sys
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from database.queries import get_all_countries
from services.esim_service import esim_service
from dotenv import load_dotenv

async def run_sync():
    # Загружаем переменные окружения
    load_dotenv()
    
    # Создаем подключение к БД
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+asyncpg://postgres:Vadim22021985@db:5432/esim_bot')
    engine = create_async_engine(DATABASE_URL, echo=False)
    
    # Создаем фабрику сессий
    session_pool = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    
    # Получаем тип синхронизации из аргументов командной строки
    sync_type = "all"
    if len(sys.argv) > 1:
        sync_type = sys.argv[1].lower()
    
    async with session_pool() as session:
        # Синхронизация только стран
        if sync_type == "countries":
            print('Начинаем синхронизацию стран...')
            result = await esim_service.sync_countries(session)
            if result['success']:
                print(f'✅ Успешно! Синхронизировано {result.get("countries_count", 0)} стран.')
            else:
                print(f'❌ Ошибка синхронизации стран: {result.get("error", "Неизвестная ошибка")}')
            return
            
        # Синхронизация пакетов для всех стран
        countries = await get_all_countries(session)
        print(f'Найдено {len(countries)} стран. Начинаем синхронизацию пакетов...')
        
        if sync_type == "packages" or sync_type == "all":
            for country in countries:
                print(f'Синхронизация пакетов для страны {country.name} ({country.code})...')
                try:
                    result = await esim_service.sync_packages(session, country.code)
                    if result['success']:
                        print(f'✅ Успешно! {result.get("packages_count", 0)} пакетов.')
                    else:
                        print(f'❌ Ошибка: {result.get("error", "Неизвестная ошибка")}')
                    
                    # Важно! Коммитим изменения после каждой страны
                    await session.commit()
                except Exception as e:
                    print(f'❌ Исключение при синхронизации пакетов для {country.code}: {str(e)}')
                    await session.rollback()
        
        print('Синхронизация завершена!')

# Запускаем функцию синхронизации
if __name__ == "__main__":
    asyncio.run(run_sync())