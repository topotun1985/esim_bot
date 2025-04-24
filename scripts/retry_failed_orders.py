#!/usr/bin/env python
# -*- coding: utf-8 -*-

import asyncio
import sys
import os
from datetime import datetime
import logging
import json

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Добавляем корневую директорию проекта в sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import Order, OrderStatus, ESim, Package, User
from services.esim_service import ESIMService
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, joinedload
from sqlalchemy.future import select
from dotenv import load_dotenv

# Добавляем импорт для работы с Telegram ботом
from aiogram import Bot
from aiogram.enums import ParseMode

# Загружаем переменные окружения
load_dotenv()

# Получаем токен бота из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Инициализируем бота
bot = Bot(token=BOT_TOKEN)

# Создаем подключение к базе данных
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    logger.error("Переменная окружения DATABASE_URL не установлена")
    sys.exit(1)

# Проверяем, запущен ли скрипт в Docker-контейнере
# В Docker-контейнере нужно использовать оригинальный URL с хостом db
# При запуске вне Docker-контейнера нужно заменить db на localhost
is_docker = os.path.exists('/.dockerenv')
if "db:" in DATABASE_URL and not is_docker:
    DATABASE_URL = DATABASE_URL.replace("db:", "localhost:")
    logger.info(f"Скрипт запущен локально, используем локальный хост для подключения к PostgreSQL")

logger.info(f"Подключение к базе данных: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL}")
engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def retry_failed_orders():
    """
    Находит заказы со статусом FAILED, которые были оплачены,
    и пытается создать для них eSIM через API провайдера.
    """
    logger.info("🔄 Запуск скрипта повторной обработки неудачных заказов")
    
    # Инициализируем сервисы
    async with AsyncSession(engine) as session:
        try:
            # Создаем экземпляр сервиса eSIM
            esim_service = ESIMService()
            
            # Сначала проверяем статус заказов, для которых eSIM создается асинхронно
            await check_async_esim_orders(session, esim_service)
            
            # Получаем список доступных пакетов из API
            try:
                all_available_packages = await esim_service.get_all_available_packages()
                logger.info(f"✅ Получено {len(all_available_packages)} доступных пакетов из API")
                
                # Выводим первые 5 пакетов для проверки
                for i, (code, data) in enumerate(list(all_available_packages.items())[:5]):
                    logger.info(f"Пакет {i+1}: {code}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось получить список доступных пакетов из API: {str(e)}")
                all_available_packages = {}
            
            # Получаем список неудачных заказов из базы данных
            logger.info("Поиск неудачных заказов в базе данных")
            
            # Используем joinedload для предварительной загрузки связанных объектов
            # чтобы избежать ошибки MissingGreenlet
            query = select(Order).options(
                joinedload(Order.package).joinedload(Package.country),
                joinedload(Order.user)
            ).where(
                Order.status == OrderStatus.FAILED.value,
                Order.paid_at.is_not(None)  # Заказ был оплачен
            )
            
            result = await session.execute(query)
            failed_orders = result.unique().scalars().all()
            
            # Сохраняем все необходимые данные заказов в локальные структуры
            orders_data = []
            for order in failed_orders:
                # Собираем все необходимые данные заказа
                order_data = {
                    "id": order.id,
                    "status": order.status,
                    "package_code": order.package.package_code if order.package else None,
                    "country_code": order.package.country.code if order.package and order.package.country else "",
                    "user_id": order.user.id if order.user else None,
                    "email": order.user.email if order.user and hasattr(order.user, 'email') else None,
                    "phone": order.user.phone if order.user and hasattr(order.user, 'phone') else None,
                }
                
                # Проверяем наличие необходимых данных
                if not order_data["package_code"]:
                    logger.error(f"❌ У заказа #{order_data['id']} отсутствует пакет")
                    continue
                
                if not order_data["user_id"]:
                    logger.error(f"❌ У заказа #{order_data['id']} отсутствует пользователь")
                    continue
                
                orders_data.append(order_data)
            
            if not orders_data:
                logger.info("✅ Неудачных оплаченных заказов не найдено")
                return
                
            logger.info(f"🔍 Найдено {len(orders_data)} неудачных оплаченных заказов")
            
            # Обрабатываем каждый заказ
            for order_data in orders_data:
                order_id = order_data["id"]
                logger.info(f"Обработка заказа #{order_id} (статус: {order_data['status']})")
                
                # Получаем код пакета и страны
                package_code = order_data["package_code"]
                country_code = order_data["country_code"]
                
                logger.info(f"Заказ #{order_id}: пакет {package_code}, страна {country_code}")
                
                # Используем только последнюю часть кода пакета (суффикс)
                modified_package_code = package_code.split("-")[-1] if "-" in package_code else package_code
                
                logger.info(f"Модифицирован код пакета: {package_code} -> {modified_package_code}")
                
                # Получаем email пользователя
                email = order_data["email"] or "topotun85@example.com"  # Запасной email, если у пользователя нет
                logger.info(f"Использую email: {email}")
                
                # Получаем телефон пользователя (если есть)
                phone = order_data["phone"] or ""
                
                # Создаем eSIM через API
                logger.info(f"Создание eSIM для заказа #{order_id}")
                esim_result = await esim_service.create_esim(
                    order_id=str(order_id),
                    package_code=modified_package_code,
                    email=email,
                    phone_number=phone,
                    country_code=country_code
                )
                
                # Проверяем результат создания eSIM
                if not esim_result.get("success"):
                    error_msg = esim_result.get("error", "Unknown error")
                    logger.error(f"❌ Не удалось создать eSIM для заказа #{order_id}: {error_msg}")
                    continue
                
                # Получаем данные eSIM
                iccid = esim_result.get("iccid", "")
                qr_code = esim_result.get("qr_code", "")
                activation_code = esim_result.get("activation_code", "")
                esim_tran_no = esim_result.get("esim_tran_no", "")
                
                # Если в ответе есть order_no, но нет iccid, это асинхронное создание
                # Но мы не будем менять статус, а просто залогируем это
                order_no = esim_result.get("order_no", "")
                if order_no and not iccid:
                    logger.info(f"ℹ️ Заказ eSIM #{order_id} создается асинхронно, номер заказа: {order_no}")
                    logger.info(f"Заказ останется в статусе FAILED и будет обработан при следующем запуске скрипта")
                    
                    # Сохраняем номер заказа в базе данных
                    order_query = select(Order).where(Order.id == order_id)
                    order_result = await session.execute(order_query)
                    order = order_result.scalar_one_or_none()
                    
                    if order:
                        order.order_no = order_no
                        await session.commit()
                        logger.info(f"✅ Номер заказа {order_no} сохранен в базе данных для заказа #{order_id}")
                    
                    continue
                
                if not iccid:
                    logger.error(f"❌ Не удалось получить ICCID для заказа #{order_id}")
                    continue
                
                logger.info(f"✅ eSIM успешно создан для заказа #{order_id}: ICCID {iccid}")
                
                # Получаем объект заказа из базы данных для обновления
                order_query = select(Order).where(Order.id == order_id)
                order_result = await session.execute(order_query)
                order = order_result.scalar_one_or_none()
                
                if not order:
                    logger.error(f"❌ Не удалось найти заказ #{order_id} в базе данных")
                    continue
                
                # Создаем запись об eSIM в базе данных
                esim = ESim(
                    order_id=order_id,
                    iccid=iccid,
                    qr_code_url=qr_code,
                    activation_code=activation_code,
                    esim_tran_no=esim_tran_no,
                    esim_status="ACTIVE",
                    raw_data=json.dumps(esim_result.get("raw_response", {}))
                )
                
                # Обновляем статус заказа
                order.status = OrderStatus.COMPLETED.value
                order.updated_at = datetime.now()
                
                # Сохраняем изменения в базе данных
                session.add(esim)
                session.add(order)
                await session.commit()
                
                logger.info(f"✅ Заказ #{order_id} успешно обновлен и помечен как выполненный")
                
                # Отправляем уведомление пользователю
                await send_esim_notification(order_id, iccid, qr_code, activation_code, esim_result)
        
        except Exception as e:
            logger.error(f"❌ Ошибка при выполнении скрипта: {str(e)}")
        finally:
            # Закрываем соединение с ботом
            await bot.session.close()

async def check_async_esim_orders(session, esim_service):
    """
    Проверяет статус заказов, для которых eSIM создается асинхронно.
    Ищет заказы, у которых есть order_no, но нет связанной записи eSIM.
    """
    logger.info("🔍 Проверка статуса заказов с асинхронным созданием eSIM")
    
    # Ищем заказы, у которых есть order_no, но нет связанной записи eSIM
    query = select(Order).outerjoin(ESim, Order.id == ESim.order_id).where(
        Order.order_no.is_not(None),
        ESim.id.is_(None),
        Order.paid_at.is_not(None)  # Заказ был оплачен
    )
    
    # Выводим SQL запрос для отладки
    logger.info(f"SQL запрос: {query}")
    
    result = await session.execute(query)
    orders = result.unique().scalars().all()
    
    if not orders:
        logger.info("✅ Заказов с асинхронным созданием eSIM не найдено")
        
        # Для отладки проверим, есть ли заказы с order_no
        check_query = select(Order).where(
            Order.order_no.is_not(None),
            Order.paid_at.is_not(None)
        )
        check_result = await session.execute(check_query)
        check_orders = check_result.unique().scalars().all()
        
        if check_orders:
            logger.info(f"Найдено {len(check_orders)} заказов с order_no:")
            for order in check_orders:
                logger.info(f"Заказ #{order.id}, статус: {order.status}, order_no: {order.order_no}")
                
                # Проверяем, есть ли у заказа связанная запись eSIM
                esim_query = select(ESim).where(ESim.order_id == order.id)
                esim_result = await session.execute(esim_query)
                esim = esim_result.scalar_one_or_none()
                
                if esim:
                    logger.info(f"У заказа #{order.id} есть связанная запись eSIM: {esim.iccid}")
                else:
                    logger.info(f"У заказа #{order.id} нет связанной записи eSIM")
        else:
            logger.info("Заказов с order_no не найдено")
        
        return
    
    logger.info(f"🔍 Найдено {len(orders)} заказов с асинхронным созданием eSIM")
    
    # Проверяем статус каждого заказа
    for order in orders:
        order_id = order.id
        order_no = order.order_no
        
        logger.info(f"Проверка статуса заказа eSIM #{order_id} (order_no: {order_no})")
        
        # Проверяем статус заказа eSIM
        status_result = await esim_service.check_esim_order_status(order_no)
        
        # Проверяем результат проверки статуса
        if not status_result.get("success"):
            error_msg = status_result.get("error", "Unknown error")
            logger.error(f"❌ Не удалось проверить статус заказа eSIM для заказа #{order_id}: {error_msg}")
            continue
        
        # Получаем данные eSIM
        iccid = status_result.get("iccid", "")
        qr_code = status_result.get("qr_code", "")
        activation_code = status_result.get("activation_code", "")
        esim_tran_no = status_result.get("esim_tran_no", "")
        
        if not iccid:
            logger.info(f"ℹ️ eSIM для заказа #{order_id} еще создается")
            continue
        
        logger.info(f"✅ eSIM успешно получен для заказа #{order_id}: ICCID {iccid}")
        
        # Создаем запись об eSIM в базе данных
        esim = ESim(
            order_id=order_id,
            iccid=iccid,
            qr_code_url=qr_code,
            activation_code=activation_code,
            esim_tran_no=esim_tran_no,
            esim_status="ACTIVE",
            raw_data=json.dumps(status_result.get("raw_response", {}))
        )
        
        # Обновляем статус заказа
        order.status = OrderStatus.COMPLETED.value
        order.updated_at = datetime.now()
        
        # Сохраняем изменения в базе данных
        session.add(esim)
        session.add(order)
        await session.commit()
        
        logger.info(f"✅ Заказ #{order_id} успешно обновлен и помечен как выполненный")
        
        # Отправляем уведомление пользователю
        await send_esim_notification(order_id, iccid, qr_code, activation_code, status_result)

async def send_esim_notification(order_id, iccid, qr_code, activation_code, esim_result):
    """
    Отправляет уведомление пользователю о созданной eSIM через Telegram бота
    
    Args:
        order_id: ID заказа
        iccid: ICCID eSIM
        qr_code: URL QR-кода для активации
        activation_code: Код активации
        esim_result: Полный результат создания eSIM
    """
    logger.info(f"Отправка уведомления пользователю о созданной eSIM для заказа #{order_id}")
    
    try:
        async with async_session() as session:
            # Получаем заказ с пользователем и пакетом
            query = select(Order).options(
                joinedload(Order.user),
                joinedload(Order.package).joinedload(Package.country)
            ).where(Order.id == order_id)
            
            result = await session.execute(query)
            order = result.unique().scalar_one_or_none()
            
            if not order or not order.user:
                logger.error(f"❌ Не удалось найти заказ #{order_id} или пользователя для отправки уведомления")
                return
            
            # Формируем сообщение с информацией о eSIM
            message_text = (
                "🎉 *Ваша eSIM готова!*\n\n"
                f"*ICCID:* `{iccid}`\n"
            )
            
            # Добавляем информацию о пакете
            if order.package and order.package.country:
                message_text += (
                    f"*Страна:* {order.package.country.name}\n"
                    f"*Пакет:* {order.package.data_amount} ГБ на {order.package.duration} дней\n\n"
                )
            
            # Добавляем QR-код, если доступен
            if qr_code:
                message_text += "QR-код для активации отправлен отдельным сообщением.\n\n"
            
            # Добавляем код активации, если доступен
            if activation_code:
                message_text += f"*Код для активации:* `{activation_code}`\n\n"
            
            # Добавляем APN, если доступен
            apn = esim_result.get("apn", "")
            if apn:
                message_text += f"*APN:* `{apn}`\n\n"
            
            # Добавляем инструкции по активации
            message_text += (
                "*Инструкции по активации:*\n"
                "1. Откройте настройки вашего телефона\n"
                "2. Перейдите в раздел 'Сотовая связь' или 'SIM-карты'\n"
                "3. Выберите 'Добавить eSIM' или 'Добавить тарифный план'\n"
                "4. Отсканируйте QR-код или введите код активации вручную\n"
                "5. Следуйте инструкциям на экране\n\n"
                "Если у вас возникли проблемы с активацией, обратитесь в нашу службу поддержки."
            )
            
            # Отправляем сообщение пользователю
            await bot.send_message(
                chat_id=order.user.telegram_id,
                text=message_text,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Если есть QR-код, отправляем его отдельным сообщением
            if qr_code:
                try:
                    await bot.send_photo(
                        chat_id=order.user.telegram_id,
                        photo=qr_code,
                        caption="QR-код для активации вашей eSIM. Отсканируйте его в настройках телефона."
                    )
                except Exception as e:
                    logger.error(f"❌ Ошибка при отправке QR-кода: {str(e)}")
                    # Отправляем ссылку на QR-код, если не удалось отправить изображение
                    await bot.send_message(
                        chat_id=order.user.telegram_id,
                        text=f"Ссылка на QR-код для активации: {qr_code}"
                    )
            
            logger.info(f"✅ Уведомление о созданной eSIM успешно отправлено пользователю {order.user.telegram_id}")
    
    except Exception as e:
        logger.exception(f"❌ Ошибка при отправке уведомления пользователю: {str(e)}")

if __name__ == "__main__":
    # Запускаем асинхронную функцию
    asyncio.run(retry_failed_orders())