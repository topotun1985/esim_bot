import logging
import json
from aiohttp import web
from aiogram import Router, Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from database.models import Order, OrderStatus, ESim
from utils.states import PaymentState
from services.payment_service import CRYPTOBOT_API_TOKEN

# Настраиваем логгер
logger = logging.getLogger(__name__)

# Создаем роутер для вебхуков
router = Router()

# Функция для проверки валидности запроса от CryptoBot
def is_valid_cryptobot_request(data, request_headers):
    """
    Проверяет валидность запроса от CryptoBot на основе заголовков.
    """
    if not data or not isinstance(data, dict):
        logger.warning("Invalid webhook data format")
        return False
    
    # В реальном приложении здесь можно проверить подпись запроса, 
    # если CryptoBot предоставляет такую возможность
    
    # Проверка основных полей в запросе
    required_fields = ["update_id", "payload"]
    for field in required_fields:
        if field not in data:
            logger.warning(f"Missing required field: {field}")
            return False
    
    return True

# Обработчик вебхуков от CryptoBot
async def handle_cryptobot_webhook(request):
    """
    Обрабатывает вебхуки от CryptoBot о статусе платежей.
    """
    try:
        # Получаем данные запроса
        data = await request.json()
        logger.info(f"Received webhook from CryptoBot: {data}")
        
        # Проверяем валидность запроса
        if not is_valid_cryptobot_request(data, request.headers):
            return web.json_response({"status": "error", "message": "Invalid request"}, status=400)
        
        # Получаем информацию о платеже
        update_type = data.get("update_type")
        
        # Обрабатываем только события invoice_paid
        if update_type == "invoice_paid":
            invoice_data = data.get("invoice", {})
            invoice_id = invoice_data.get("invoice_id")
            payload = invoice_data.get("payload", "")
            status = invoice_data.get("status")
            
            if status == "paid":
                await process_successful_payment(request.app["db_session"], 
                                                request.app["bot"], 
                                                payload, 
                                                invoice_id)
                
                return web.json_response({"status": "success"})
        
        # Для других типов событий просто логируем и возвращаем успех
        logger.info(f"Received webhook with update_type: {update_type}, not processing")
        return web.json_response({"status": "success"})
        
    except Exception as e:
        logger.exception(f"Error processing CryptoBot webhook: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)

# Функция для обработки успешного платежа
async def process_successful_payment(session, bot, payload, invoice_id):
    """
    Обрабатывает успешный платеж, обновляя статус заказа и отправляя уведомление пользователю.
    
    Args:
        session: Сессия БД
        bot: Экземпляр бота
        payload: Идентификатор заказа (app_invoice_id)
        invoice_id: ID инвойса в CryptoBot
    """
    try:
        # Извлекаем ID заказа из payload (формат "order_{order_id}_{random_hex}")
        if payload and payload.startswith("order_"):
            parts = payload.split("_")
            if len(parts) >= 2:
                order_id = int(parts[1])
                
                # Получаем заказ из БД с предварительной загрузкой связанных объектов
                stmt = select(Order).options(
                    joinedload(Order.user),
                    joinedload(Order.package).joinedload(Package.country)
                ).where(Order.id == order_id)
                result = await session.execute(stmt)
                order = result.scalar_one_or_none()
                
                if order:
                    # Проверяем, не обрабатывали ли мы уже этот платеж
                    if order.status == OrderStatus.PAID.value:
                        logger.info(f"Order {order_id} already marked as paid")
                        return
                    
                    # Обновляем статус заказа
                    order.status = OrderStatus.PAID.value
                    order.paid_at = datetime.utcnow()
                    order.payment_details = json.dumps({
                        "payment_method": "CryptoBot",
                        "invoice_id": invoice_id,
                        **(json.loads(order.payment_details) if order.payment_details else {})
                    })
                    await session.commit()
                    
                    logger.info(f"Order {order_id} marked as paid via webhook")
                    
                    # Проверяем, является ли этот заказ пополнением трафика
                    payment_details = json.loads(order.payment_details) if order.payment_details else {}
                    is_topup = "topup_for_esim_id" in payment_details
                    
                    if is_topup:
                        # Это заказ на пополнение трафика
                        esim_id = payment_details.get("topup_for_esim_id")
                        esim_iccid = payment_details.get("topup_for_esim_iccid")
                        
                        # Получаем eSIM из БД
                        esim_stmt = select(ESim).options(
                            joinedload(ESim.order)
                        ).where(ESim.id == esim_id)
                        esim_result = await session.execute(esim_stmt)
                        esim = esim_result.scalar_one_or_none()
                        
                        if esim:
                            # Инициируем пополнение трафика через сервис eSIM
                            try:
                                from services.esim_service import esim_service
                                
                                # Получаем код пакета без суффикса (согласно особенностям API)
                                package_code = order.package.code
                                if "-" in package_code:
                                    # Получаем первые три части кода (например, SI-0.3GB-1D из SI-0.3GB-1D-P82Y6VYRL)
                                    package_code_parts = package_code.split("-")
                                    if len(package_code_parts) >= 3:
                                        package_code = "-".join(package_code_parts[:3])
                                
                                # Вызываем API для пополнения трафика
                                topup_result = await esim_service.topup_esim(
                                    iccid=esim.iccid,
                                    package_code=package_code,
                                    transaction_id=order.transaction_id
                                )
                                
                                # Обновляем статус заказа
                                order.status = OrderStatus.PROCESSING.value
                                order.provider_order_id = topup_result.get("orderNo", "")
                                await session.commit()
                                
                                # Отправляем уведомление пользователю
                                package_info = f"{order.package.data_amount} {order.package.data_unit}"
                                country_name = order.package.country.name
                                
                                await bot.send_message(
                                    chat_id=order.user.telegram_id,
                                    text=f"✅ Ваш платеж для пополнения трафика eSIM ({package_info}) для {country_name} успешно получен!\n\n"
                                         f"ICCID: <code>{esim.iccid}</code>\n\n"
                                         f"Мы начали процесс пополнения трафика. Это может занять несколько минут. "
                                         f"Вы получите уведомление, когда процесс будет завершен.",
                                    parse_mode="HTML"
                                )
                                logger.info(f"Topup payment notification sent to user {order.user.telegram_id}")
                                
                            except Exception as e:
                                logger.error(f"Error processing eSIM topup: {e}")
                                
                                # Отправляем уведомление об ошибке пользователю
                                await bot.send_message(
                                    chat_id=order.user.telegram_id,
                                    text=f"✅ Ваш платеж для пополнения трафика eSIM успешно получен!\n\n"
                                         f"ICCID: <code>{esim.iccid}</code>\n\n"
                                         f"Однако, возникла ошибка при обработке пополнения. "
                                         f"Наша команда поддержки свяжется с вами в ближайшее время.",
                                    parse_mode="HTML"
                                )
                        else:
                            logger.error(f"eSIM not found for topup: {esim_id}")
                    else:
                        # Это обычный заказ на новую eSIM
                        # Отправляем уведомление пользователю
                        try:
                            await bot.send_message(
                                chat_id=order.user.telegram_id,
                                text=f"✅ Ваш платеж для заказа #{order_id} успешно получен! "
                                     f"Мы начали процесс активации вашей eSIM."
                            )
                            logger.info(f"Payment notification sent to user {order.user.telegram_id}")
                        except Exception as e:
                            logger.error(f"Error sending notification to user: {e}")
                else:
                    logger.warning(f"Order not found for id: {order_id}")
            else:
                logger.warning(f"Invalid payload format: {payload}")
        else:
            logger.warning(f"Invalid or missing payload: {payload}")
    except Exception as e:
        logger.exception(f"Error processing successful payment: {e}")
        # Не выбрасываем исключение дальше, чтобы не возвращать ошибку на вебхук

# Обработчик вебхуков от провайдера eSIM
async def handle_esim_webhook(request):
    """
    Обрабатывает вебхуки от провайдера eSIM о статусе eSIM.
    """
    try:
        # Получаем данные запроса
        data = await request.json()
        logger.info(f"Received webhook from eSIM provider: {json.dumps(data, indent=2, ensure_ascii=False)}")
        
        # Проверяем тип уведомления
        notify_type = data.get("notifyType")
        content = data.get("content", {})
        
        if not notify_type or not content:
            logger.warning("Invalid webhook data format from eSIM provider")
            return web.json_response({"status": "error", "message": "Invalid request"}, status=400)
        
        # Обрабатываем разные типы уведомлений
        if notify_type == "ORDER_STATUS":
            # Обработка статуса заказа
            order_no = content.get("orderNo")
            order_status = content.get("orderStatus")
            
            if order_no and order_status:
                await update_esim_order_status(request.app["db_session"], order_no, order_status)
                
        elif notify_type == "ESIM_STATUS":
            # Обработка статуса eSIM
            iccid = content.get("iccid")
            esim_status = content.get("esimStatus")
            smdp_status = content.get("smdpStatus")
            
            if iccid and (esim_status or smdp_status):
                await update_esim_status(request.app["db_session"], iccid, esim_status, smdp_status)
                
        elif notify_type == "DATA_USAGE":
            # Обработка использования данных
            iccid = content.get("iccid")
            total_volume = content.get("totalVolume")
            order_usage = content.get("orderUsage")
            remain = content.get("remain")
            
            if iccid and (total_volume is not None) and (order_usage is not None):
                await update_esim_data_usage(request.app["db_session"], iccid, total_volume, order_usage, remain)
                
        elif notify_type == "VALIDITY_USAGE":
            # Обработка срока действия
            iccid = content.get("iccid")
            expired_time = content.get("expiredTime")
            
            if iccid and expired_time:
                await update_esim_validity(request.app["db_session"], iccid, expired_time)
                
        return web.json_response({"status": "success"})
        
    except Exception as e:
        logger.exception(f"Error processing eSIM webhook: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)

# Функция для обновления статуса заказа eSIM
async def update_esim_order_status(session, order_no, order_status):
    """
    Обновляет статус заказа eSIM в базе данных.
    
    Args:
        session: Сессия БД
        order_no: Номер заказа у провайдера
        order_status: Новый статус заказа
    """
    try:
        from sqlalchemy.orm import joinedload
        
        # Находим eSIM по номеру заказа
        stmt = select(ESim).where(ESim.esim_tran_no == order_no).options(
            joinedload(ESim.order)
        )
        result = await session.execute(stmt)
        esim = result.scalars().first()
        
        if esim:
            # Обновляем статус eSIM
            esim.esim_status = order_status
            esim.updated_at = datetime.utcnow()
            await session.commit()
            
            logger.info(f"Updated eSIM order status: {order_no} -> {order_status}")
        else:
            logger.warning(f"eSIM not found for order_no: {order_no}")
            
    except Exception as e:
        logger.exception(f"Error updating eSIM order status: {e}")

# Функция для обновления статуса eSIM
async def update_esim_status(session, iccid, esim_status=None, smdp_status=None):
    """
    Обновляет статус eSIM в базе данных.
    
    Args:
        session: Сессия БД
        iccid: ICCID eSIM
        esim_status: Новый статус eSIM
        smdp_status: Статус SMDP
    """
    try:
        from sqlalchemy.orm import joinedload
        
        # Находим eSIM по ICCID
        stmt = select(ESim).where(ESim.iccid == iccid).options(
            joinedload(ESim.order)
        )
        result = await session.execute(stmt)
        esim = result.scalars().first()
        
        if esim:
            # Маппинг статусов провайдера на статусы в нашей системе
            status_mapping = {
                "IN_USE": "ACTIVATED",
                "INSTALLATION": "PROCESSING",
                "ENABLED": "ACTIVATED",
                "GOT_RESOURCE": "ACTIVATED",
                "CANCEL": "CANCELED",
                "RELEASED": "CANCELED"
            }
            
            # Обновляем статус eSIM
            if esim_status and esim_status in status_mapping:
                esim.esim_status = status_mapping[esim_status]
                logger.info(f"Mapped status from {esim_status} to {esim.esim_status}")
            elif esim_status:
                esim.esim_status = esim_status
                
            # Сохраняем статус SMDP для отладки
            if smdp_status:
                esim.smdp_status = smdp_status
                
            esim.updated_at = datetime.utcnow()
            await session.commit()
            
            logger.info(f"Updated eSIM status: {iccid} -> {esim.esim_status} (SMDP: {smdp_status})")
        else:
            logger.warning(f"eSIM not found for ICCID: {iccid}")
            
    except Exception as e:
        logger.exception(f"Error updating eSIM status: {e}")

# Функция для обновления использования данных eSIM
async def update_esim_data_usage(session, iccid, total_volume, order_usage, remain=None):
    """
    Обновляет информацию об использовании данных eSIM.
    
    Args:
        session: Сессия БД
        iccid: ICCID eSIM
        total_volume: Общий объем данных (в байтах)
        order_usage: Использованный объем данных (в байтах)
        remain: Оставшийся объем данных (в байтах)
    """
    try:
        from sqlalchemy.orm import joinedload
        
        # Находим eSIM по ICCID
        stmt = select(ESim).where(ESim.iccid == iccid).options(
            joinedload(ESim.order)
        )
        result = await session.execute(stmt)
        esim = result.scalars().first()
        
        if esim:
            # Обновляем информацию об использовании данных
            esim.total_volume = total_volume
            esim.order_usage = order_usage
            
            if remain is not None:
                esim.remaining_volume = remain
            else:
                # Вычисляем оставшийся объем данных
                esim.remaining_volume = total_volume - order_usage if total_volume >= order_usage else 0
                
            # Если данные исчерпаны, обновляем статус
            if esim.remaining_volume <= 0:
                esim.esim_status = "DEPLETED"
                
            esim.updated_at = datetime.utcnow()
            await session.commit()
            
            logger.info(f"Updated eSIM data usage: {iccid} -> Used: {order_usage}/{total_volume} bytes")
        else:
            logger.warning(f"eSIM not found for ICCID: {iccid}")
            
    except Exception as e:
        logger.exception(f"Error updating eSIM data usage: {e}")

# Функция для обновления срока действия eSIM
async def update_esim_validity(session, iccid, expired_time):
    """
    Обновляет срок действия eSIM.
    
    Args:
        session: Сессия БД
        iccid: ICCID eSIM
        expired_time: Время истечения срока действия (в формате ISO)
    """
    try:
        from sqlalchemy.orm import joinedload
        
        # Находим eSIM по ICCID
        stmt = select(ESim).where(ESim.iccid == iccid).options(
            joinedload(ESim.order)
        )
        result = await session.execute(stmt)
        esim = result.scalars().first()
        
        if esim:
            # Преобразуем строку в datetime
            try:
                expired_datetime = datetime.fromisoformat(expired_time.replace('Z', '+00:00'))
                
                # Обновляем срок действия
                esim.expired_time = expired_datetime
                esim.updated_at = datetime.utcnow()
                
                # Если срок действия истек, обновляем статус
                if expired_datetime < datetime.utcnow():
                    esim.esim_status = "EXPIRED"
                    
                await session.commit()
                
                logger.info(f"Updated eSIM validity: {iccid} -> Expires: {expired_time}")
            except ValueError as e:
                logger.error(f"Invalid expired_time format: {expired_time} - {e}")
        else:
            logger.warning(f"eSIM not found for ICCID: {iccid}")
            
    except Exception as e:
        logger.exception(f"Error updating eSIM validity: {e}")

# Настройка веб-сервера для обработки вебхуков
async def setup_webhook_server(app, bot, db_session, port=8080):
    """
    Настраивает веб-сервер для обработки вебхуков.
    
    Args:
        app: aiohttp web application
        bot: Экземпляр бота
        db_session: Фабрика сессий для БД
        port: Порт для веб-сервера (по умолчанию 8080)
    """
    # Сохраняем ссылки на бота и сессию БД в контексте приложения
    app["bot"] = bot
    app["db_session"] = db_session
    
    # Настраиваем роуты для вебхуков
    app.router.add_post('/webhook/cryptobot', handle_cryptobot_webhook)
    app.router.add_post('/webhook/esim', handle_esim_webhook)
    
    # Запускаем веб-сервер
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    logger.info(f"Webhook server started on port {port}")
    
    return runner
