from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, or_
from sqlalchemy.orm import joinedload
from datetime import datetime, timedelta
import logging
import json
from typing import List

from database.models import User, Order, ESim, OrderStatus, Package, OrderType
from database.queries import get_user_by_telegram_id
from handlers.start import get_main_menu_keyboard
from utils.states import MainMenu, AccountMenu, TopUpESim
from services.esim_service import esim_service
from utils.helpers import format_bytes, format_datetime, format_esim_status, format_expiration_date

logger = logging.getLogger(__name__)

router = Router()

# Функция для получения активных eSIM пользователя
async def get_active_esims_for_user(session: AsyncSession, user_id: int) -> list[ESim]:
    """Получение списка активных eSIM пользователя"""
    result = await session.execute(
        select(ESim)
        .join(Order, ESim.order_id == Order.id)
        .where(
            and_(
                Order.user_id == user_id,
                Order.status == OrderStatus.COMPLETED.value
            )
        )
        .options(
            joinedload(ESim.order).joinedload(Order.package).joinedload(Package.country)
        )
        .order_by(desc(ESim.created_at))
    )
    return result.scalars().all()

# Функция для экранирования специальных символов Markdown
def escape_markdown(text: str) -> str:
    """
    Экранирует специальные символы Markdown в тексте.
    """
    if not text:
        return ""
    
    # Экранируем специальные символы Markdown
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f"\\{char}")
    
    return text

# Обработчик для входа в личный кабинет
@router.callback_query(F.data == "account")
async def account_menu(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик для отображения меню личного кабинета"""
    user_data = await state.get_data()
    language_code = user_data.get("language_code", "ru")
    
    # Получаем пользователя из БД
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        logger.error(f"User not found: {callback.from_user.id}")
        await callback.answer("Ошибка: пользователь не найден" if language_code == 'ru' else "Error: user not found")
        return
    
    # Получаем активные eSIM пользователя
    active_esims = await get_active_esims_for_user(session, user.id)
    
    # Получаем общее количество заказов пользователя
    result = await session.execute(
        select(Order)
        .where(Order.user_id == user.id)
        .order_by(desc(Order.created_at))
    )
    orders = result.scalars().all()
    
    # Форматируем дату регистрации
    registration_date = format_datetime(user.created_at, language=language_code)
    
    # Формируем сообщение
    message_text = (
        f"👤 *Личный кабинет*\n\n"
        f"*Telegram ID:* `{user.telegram_id}`\n"
        f"*Имя:* {user.first_name or ''} {user.last_name or ''}\n"
        f"*Username:* @{user.username or 'не указан'}\n"
        f"*Дата регистрации:* {registration_date}\n\n"
    ) if language_code == 'ru' else (
        f"👤 *Account*\n\n"
        f"*Telegram ID:* `{user.telegram_id}`\n"
        f"*Name:* {user.first_name or ''} {user.last_name or ''}\n"
        f"*Username:* @{user.username or 'not specified'}\n"
        f"*Registration date:* {registration_date}\n\n"
    )
    
    # Добавляем информацию о количестве активных eSIM и заказов
    if active_esims:
        # Подсчитываем суммарный объем трафика
        total_data = sum(esim.total_volume or 0 for esim in active_esims)
        used_data = sum(esim.order_usage or 0 for esim in active_esims)
        
        # Форматируем трафик
        formatted_total = format_bytes(total_data)
        formatted_used = format_bytes(used_data)
        
        # Вычисляем процент использования
        usage_percent = 0
        if total_data > 0:
            usage_percent = round((used_data / total_data) * 100, 1)
        
        message_text += (
            f"*Статистика:*\n"
            f"• Активные eSIM: {len(active_esims)}\n"
            f"• Всего заказов: {len(orders)}\n"
            f"• Общий трафик: {formatted_used} из {formatted_total} ({usage_percent}%)\n\n"
            f"Выберите действие ниже:"
        ) if language_code == 'ru' else (
            f"*Statistics:*\n"
            f"• Active eSIMs: {len(active_esims)}\n"
            f"• Total orders: {len(orders)}\n"
            f"• Total data: {formatted_used} of {formatted_total} ({usage_percent}%)\n\n"
            f"Choose an action below:"
        )
    else:
        message_text += (
            f"*Статистика:*\n"
            f"• Активные eSIM: 0\n"
            f"• Всего заказов: {len(orders)}\n\n"
            f"У вас пока нет активных eSIM.\n"
            f"Выберите действие ниже:"
        ) if language_code == 'ru' else (
            f"*Statistics:*\n"
            f"• Active eSIMs: 0\n"
            f"• Total orders: {len(orders)}\n\n"
            f"You don't have any active eSIMs yet.\n"
            f"Choose an action below:"
        )
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    # Кнопка для просмотра активных eSIM
    builder.button(
        text="📱 Мои eSIM" if language_code == 'ru' else "📱 My eSIMs",
        callback_data="my_esims"
    )
    
    # Кнопка для просмотра истории заказов
    builder.button(
        text="📋 История заказов" if language_code == 'ru' else "📋 Order History",
        callback_data="order_history"
    )
    
    # Кнопка для возврата в главное меню
    builder.button(
        text="🏠 Главное меню" if language_code == 'ru' else "🏠 Main Menu",
        callback_data="main_menu"
    )
    
    # Настраиваем расположение кнопок
    builder.adjust(1)
    
    # Устанавливаем состояние
    await state.set_state(AccountMenu.menu)
    
    # Отправляем сообщение
    await callback.message.edit_text(
        message_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

# Обработчик для просмотра списка eSIM пользователя
@router.callback_query(F.data == "my_esims")
async def list_esims(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик для отображения списка eSIM пользователя"""
    user_data = await state.get_data()
    language_code = user_data.get("language_code", "ru")
    
    # Получаем пользователя из БД
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        logger.error(f"User not found: {callback.from_user.id}")
        await callback.answer("Ошибка: пользователь не найден" if language_code == 'ru' else "Error: user not found")
        return
    
    # Получаем активные eSIM пользователя
    active_esims = await get_active_esims_for_user(session, user.id)
    
    if not active_esims:
        # Если у пользователя нет активных eSIM
        message_text = (
            "У вас пока нет активных eSIM.\n\n"
            "Вы можете приобрести eSIM в главном меню."
        ) if language_code == 'ru' else (
            "You don't have any active eSIMs yet.\n\n"
            "You can purchase an eSIM from the main menu."
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(
            text="👤 Личный кабинет" if language_code == 'ru' else "👤 Account",
            callback_data="account"
        )
        builder.button(
            text="🏠 Главное меню" if language_code == 'ru' else "🏠 Main Menu",
            callback_data="main_menu"
        )
        builder.adjust(2)
        
        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup()
        )
        return
    
    # Формируем сообщение со списком eSIM
    message_text = (
        "📱 *Ваши активные eSIM:*\n\n"
    ) if language_code == 'ru' else (
        "📱 *Your active eSIMs:*\n\n"
    )
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    # Добавляем каждую eSIM в список
    for i, esim in enumerate(active_esims, 1):
        # Получаем заказ, связанный с eSIM
        order = esim.order
        
        # Получаем пакет, связанный с заказом
        package = order.package
        
        # Форматируем дату создания и статус
        created_date = format_datetime(esim.created_at, language=language_code)
        status_display = format_esim_status(esim.esim_status, language_code)
        expiration_date = format_expiration_date(esim.expired_time, language_code)
        
        # Форматируем использование трафика
        total_volume = esim.total_volume or 0
        used_volume = esim.order_usage or 0
        usage_percent = 0
        if total_volume > 0:
            usage_percent = round((used_volume / total_volume) * 100, 1)
        
        formatted_total = format_bytes(total_volume)
        formatted_used = format_bytes(used_volume)
        
        # Экранируем значения переменных для Markdown
        country_name = escape_markdown(package.country.name)
        status_display = escape_markdown(status_display)
        package_info_ru = escape_markdown(f"{package.data_amount} ГБ на {package.duration} дней")
        package_info_en = escape_markdown(f"{package.data_amount} GB for {package.duration} days")
        expiration_date = escape_markdown(expiration_date)
        formatted_used = escape_markdown(formatted_used)
        formatted_total = escape_markdown(formatted_total)
        created_date = escape_markdown(created_date)
        iccid = escape_markdown(esim.iccid)
        
        # Добавляем информацию о eSIM в сообщение
        message_text += (
            f"*{i}. eSIM {country_name}*\n"
            f"ICCID: `{iccid}`\n"
            f"Статус: {status_display}\n"
            f"Пакет: {package_info_ru}\n"
            f"Трафик: {formatted_used} из {formatted_total} ({usage_percent}%)\n"
            f"Создана: {created_date}\n"
            f"Срок действия: {expiration_date}\n\n"
        ) if language_code == 'ru' else (
            f"*{i}. eSIM {country_name}*\n"
            f"ICCID: `{iccid}`\n"
            f"Status: {status_display}\n"
            f"Package: {package_info_en}\n"
            f"Data: {formatted_used} of {formatted_total} ({usage_percent}%)\n"
            f"Created: {created_date}\n"
            f"Expires: {expiration_date}\n\n"
        )
        
        # Добавляем кнопку для проверки статуса этой eSIM
        builder.button(
            text=f"📊 Статус eSIM #{i}" if language_code == 'ru' else f"📊 eSIM #{i} Status",
            callback_data=f"check_esim_status:{esim.id}"
        )
    
    # Добавляем кнопку для возврата в личный кабинет
    builder.button(
        text="👤 Личный кабинет" if language_code == 'ru' else "👤 Account",
        callback_data="account"
    )

    # Добавляем кнопку для возврата в главное меню
    builder.button(
        text="🏠 Главное меню" if language_code == 'ru' else "🏠 Main Menu",
        callback_data="main_menu"
    )

    # Настраиваем расположение кнопок
    builder.adjust(2)
    
    # Отправляем сообщение
    await callback.message.edit_text(
        message_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

# Обработчик для проверки статуса eSIM
@router.callback_query(lambda c: c.data.startswith("check_esim_status:"))
async def check_esim_status(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик для проверки статуса eSIM"""
    esim_id = int(callback.data.split(":")[1])
    user_data = await state.get_data()
    language_code = user_data.get("language_code", "ru")
    
    # Показываем сообщение о проверке
    message_text = (
        "⏳ Проверяем статус eSIM...\n\n"
        "Это может занять некоторое время. Пожалуйста, подождите."
    ) if language_code == 'ru' else (
        "⏳ Checking eSIM status...\n\n"
        "This may take some time. Please wait."
    )
    
    await callback.message.edit_text(
        message_text,
        reply_markup=None
    )
    
    # Получаем eSIM из БД
    result = await session.execute(
        select(ESim)
        .where(ESim.id == esim_id)
        .options(
            joinedload(ESim.order).joinedload(Order.package).joinedload(Package.country)
        )
    )
    esim = result.scalars().first()
    if not esim:
        logger.error(f"eSIM not found: {esim_id}")
        message_text = (
            "❌ Ошибка: eSIM не найдена.\n\n"
            "Пожалуйста, вернитесь в список eSIM и попробуйте снова."
        ) if language_code == 'ru' else (
            "❌ Error: eSIM not found.\n\n"
            "Please return to the eSIM list and try again."
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(
            text="◀️ Назад к списку" if language_code == 'ru' else "◀️ Back to list",
            callback_data="my_esims"
        )
        
        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup()
        )
        return
    
    # Получаем заказ, связанный с eSIM
    order = esim.order
    
    # Получаем пакет, связанный с заказом
    package = order.package
    
    # Проверяем статус eSIM через API провайдера
    esim_status = await esim_service.check_esim_status(esim.esim_tran_no, esim.iccid)
    
    if not esim_status.get('success'):
        # Если не удалось получить статус, показываем последние известные данные
        logger.error(f"Failed to get eSIM status: {esim_status.get('error')}")
        
        # Форматируем дату создания
        created_date = format_datetime(esim.created_at, language=language_code)
        
        message_text = (
            f"📱 *Информация о eSIM*\n\n"
            f"*Страна:* {package.country.name}\n"
            f"*Пакет:* {package.data_amount} ГБ на {package.duration} дней\n"
            f"*ICCID:* `{esim.iccid}`\n"
            f"*Статус:* {format_esim_status(esim.esim_status, language_code)}\n"
            f"*Создана:* {created_date}\n\n"
            f"❗ *Не удалось получить актуальный статус eSIM*\n"
            f"Ошибка: {esim_status.get('error', 'Неизвестная ошибка')}\n\n"
            f"Показаны последние известные данные."
        ) if language_code == 'ru' else (
            f"📱 *eSIM Information*\n\n"
            f"*Country:* {package.country.name}\n"
            f"*Package:* {package.data_amount} GB for {package.duration} days\n"
            f"*ICCID:* `{esim.iccid}`\n"
            f"*Status:* {format_esim_status(esim.esim_status, language_code)}\n"
            f"*Created:* {created_date}\n\n"
            f"❗ *Failed to get current eSIM status*\n"
            f"Error: {esim_status.get('error', 'Unknown error')}\n\n"
            f"Showing last known data."
        )
    else:
        # Обновляем данные eSIM в БД
        # Маппинг статусов провайдера на статусы в нашей системе
        status_mapping = {
            "IN_USE": "ACTIVATED",
            "INSTALLATION": "PROCESSING",
            "ENABLED": "ACTIVATED",  
            "GOT_RESOURCE": "READY",
            "CANCEL": "CANCELED",
            "RELEASED": "CANCELED"
        }
        
        # Получаем статус eSIM из ответа API
        api_esim_status = esim_status.get('esim_status', esim.esim_status)
        
        # Применяем маппинг статусов
        if api_esim_status in status_mapping:
            mapped_status = status_mapping[api_esim_status]
            logger.info(f"Mapped status from {api_esim_status} to {mapped_status}")
            esim.esim_status = mapped_status
        else:
            esim.esim_status = api_esim_status
            
        esim.order_usage = esim_status.get('order_usage', esim.order_usage)
        
        # Обновляем срок действия eSIM, если он есть в ответе API
        if esim_status.get('expired_time'):
            try:
                # Преобразуем строку даты в объект datetime
                expired_time_str = esim_status.get('expired_time')
                # Обрабатываем разные форматы даты
                if 'Z' in expired_time_str:
                    expired_time_str = expired_time_str.replace('Z', '+00:00')
                if '+' not in expired_time_str and 'T' in expired_time_str:
                    expired_time_str = expired_time_str + '+00:00'
                
                expired_time = datetime.fromisoformat(expired_time_str)
                # Удаляем информацию о часовом поясе перед сохранением в базу данных
                expired_time = expired_time.replace(tzinfo=None)
                esim.expired_time = expired_time
                logger.info(f"Updated eSIM expiration date: {expired_time}")
            except (ValueError, TypeError) as e:
                logger.error(f"Error parsing expired_time: {esim_status.get('expired_time')} - {e}")
        
        esim.updated_at = datetime.utcnow()
        await session.commit()
        
        # Форматируем данные для отображения
        created_date = format_datetime(esim.created_at, language=language_code)
        updated_date = format_datetime(esim.updated_at, language=language_code)
        
        # Форматируем использование трафика
        total_volume = esim_status.get('total_volume', 0)
        used_volume = esim_status.get('order_usage', 0)
        usage_percent = esim_status.get('usage_percent', 0)
        
        formatted_total = format_bytes(total_volume)
        formatted_used = format_bytes(used_volume)
        
        # Используем новую функцию для форматирования статуса eSIM
        esim_status_text = esim_status.get('esim_status', 'UNKNOWN')
        status_display = format_esim_status(esim_status_text, language_code)
        
        # Форматируем дату истечения срока действия
        expiration_date = format_expiration_date(esim.expired_time, language_code)
        
        # Экранируем значения переменных для Markdown
        country_name = escape_markdown(package.country.name)
        package_info = f"{package.data_amount} ГБ на {package.duration} дней" if language_code == 'ru' else f"{package.data_amount} GB for {package.duration} days"
        package_info = escape_markdown(package_info)
        status_display = escape_markdown(status_display)
        created_date = escape_markdown(created_date)
        updated_date = escape_markdown(updated_date)
        expiration_date = escape_markdown(expiration_date)
        formatted_used = escape_markdown(formatted_used)
        formatted_total = escape_markdown(formatted_total)
        iccid = escape_markdown(esim.iccid)
        
        # Формируем сообщение с информацией о eSIM
        message_text = (
            f"📱 *Информация о eSIM*\n\n"
            f"*Страна:* {country_name}\n"
            f"*Пакет:* {package_info}\n"
            f"*ICCID:* `{iccid}`\n"
            f"*Статус:* {status_display}\n"
            f"*Создана:* {created_date}\n"
            f"*Обновлено:* {updated_date}\n"
            f"*Использование трафика:*\n"
            f"Использовано: {formatted_used} из {formatted_total} ({usage_percent}%)\n"
            f"*Срок действия:* {expiration_date}\n\n"
        ) if language_code == 'ru' else (
            f"📱 *eSIM Information*\n\n"
            f"*Country:* {country_name}\n"
            f"*Package:* {package_info}\n"
            f"*ICCID:* `{iccid}`\n"
            f"*Status:* {status_display}\n"
            f"*Created:* {created_date}\n"
            f"*Updated:* {updated_date}\n"
            f"*Data Usage:*\n"
            f"Used: {formatted_used} of {formatted_total} ({usage_percent}%)\n"
            f"*Expires:* {expiration_date}\n\n"
        )
        
        # Добавляем информацию о QR-коде, если доступна
        if esim.qr_code_url:
            message_text += (
                "\n*QR-код для активации:*\n"
                "Нажмите кнопку ниже, чтобы получить QR-код.\n"
            ) if language_code == 'ru' else (
                "\n*QR Code for activation:*\n"
                "Click the button below to get the QR code.\n"
            )
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    # Добавляем кнопку для получения QR-кода, если он доступен
    if esim.qr_code_url:
        builder.button(
            text="📲 Показать QR-код" if language_code == 'ru' else "📲 Show QR Code",
            callback_data=f"show_qr_code:{esim.id}"
        )
    
    # Добавляем кнопку для обновления статуса
    builder.button(
        text="🔄 Обновить статус" if language_code == 'ru' else "🔄 Refresh Status",
        callback_data=f"check_esim_status:{esim.id}"
    )
    
    # Добавляем кнопку для продления eSIM
    builder.button(
        text="🔋 Пополнить трафик" if language_code == 'ru' else "🔋 Top Up Data",
        callback_data=f"topup_esim:{esim.id}"
    )
    
    # Добавляем кнопку для возврата к списку eSIM
    builder.button(
        text="◀️ Назад к списку" if language_code == 'ru' else "◀️ Back to list",
        callback_data="my_esims"
    )
    
    # Добавляем кнопку для возврата в главное меню
    builder.button(
        text="🏠 Главное меню" if language_code == 'ru' else "🏠 Main Menu",
        callback_data="main_menu"
    )
    
    # Настраиваем расположение кнопок: 2 в ряд, затем 1, затем 2 в ряд
    if esim.qr_code_url:
        builder.adjust(2, 1, 2)
    else:
        # Если нет QR-кода, то первый ряд будет содержать только одну кнопку
        builder.adjust(1, 1, 2)
    
    # Отправляем сообщение
    await callback.message.edit_text(
        message_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

# Обработчик для отображения QR-кода eSIM
@router.callback_query(lambda c: c.data.startswith("show_qr_code:"))
async def show_qr_code(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик для отображения QR-кода eSIM"""
    esim_id = int(callback.data.split(":")[1])
    user_data = await state.get_data()
    language_code = user_data.get("language_code", "ru")
    
    # Получаем eSIM из БД
    result = await session.execute(
        select(ESim)
        .where(ESim.id == esim_id)
        .options(
            joinedload(ESim.order).joinedload(Order.package).joinedload(Package.country)
        )
    )
    esim = result.scalars().first()
    if not esim or not esim.qr_code_url:
        logger.error(f"eSIM or QR code not found: {esim_id}")
        await callback.answer(
            "QR-код недоступен" if language_code == 'ru' else "QR code not available",
            show_alert=True
        )
        return
    
    # Получаем заказ и пакет
    order = esim.order
    package = order.package
    
    # Форматируем статус и срок действия
    status_display = format_esim_status(esim.esim_status, language_code)
    expiration_date = format_expiration_date(esim.expired_time, language_code)
    
    # Экранируем значения переменных для Markdown
    iccid = escape_markdown(esim.iccid)
    country_name = escape_markdown(package.country.name)
    package_info_ru = escape_markdown(f"{package.data_amount} ГБ на {package.duration} дней")
    package_info_en = escape_markdown(f"{package.data_amount} GB for {package.duration} days")
    expiration_date = escape_markdown(expiration_date)
    qr_code_url = escape_markdown(esim.qr_code_url)
    
    # Формируем подпись к QR-коду
    caption = (
        f"📱 *QR-код для активации eSIM*\n\n"
        f"*ICCID:* `{iccid}`\n"
        f"*Страна:* {country_name}\n"
        f"*Пакет:* {package_info_ru}\n"
        f"*Статус:* {status_display}\n"
        f"📲 *Инструкция по активации:*\n"
        f"1. Откройте настройки телефона\n"
        f"2. Перейдите в раздел 'Сотовая связь' или 'SIM-карты'\n"
        f"3. Выберите 'Добавить тарифный план' или 'Добавить eSIM'\n"
        f"4. Отсканируйте этот QR-код\n"
        f"5. Следуйте инструкциям на экране\n\n"
        f"❗ Сохраните этот QR-код, он может понадобиться для повторной активации\n"
        f"*Срок действия:* {expiration_date}"
    ) if language_code == 'ru' else (
        f"📱 *QR code for eSIM activation*\n\n"
        f"*ICCID:* `{iccid}`\n"
        f"*Country:* {country_name}\n"
        f"*Package:* {package_info_en}\n"
        f"*Status:* {status_display}\n"
        f"📲 *Activation instructions:*\n"
        f"1. Open your phone settings\n"
        f"2. Go to 'Cellular' or 'SIM cards' section\n"
        f"3. Select 'Add Cellular Plan' or 'Add eSIM'\n"
        f"4. Scan this QR code\n"
        f"5. Follow the on-screen instructions\n\n"
        f"❗ Save this QR code, you may need it for reactivation\n"
        f"*Expires:* {expiration_date}"
    )
    
    try:
        # Отправляем QR-код как фото
        await callback.message.answer_photo(
            photo=esim.qr_code_url,
            caption=caption,
            parse_mode="Markdown"
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error sending QR code: {e}")
        # Если не удалось отправить фото, отправляем ссылку
        await callback.message.answer(
            (
                f"❌ *Не удалось отправить QR-код как изображение*\n\n"
                f"*ICCID:* `{iccid}`\n"
                f"*Статус:* {status_display}\n\n"
                f"Ссылка на QR-код: {qr_code_url}\n\n"
                f"Сохраните эту ссылку, она может понадобиться для активации eSIM."
            ) if language_code == 'ru' else (
                f"❌ *Failed to send QR code as an image*\n\n"
                f"*ICCID:* `{iccid}`\n"
                f"*Status:* {status_display}\n\n"
                f"QR code link: {qr_code_url}\n\n"
                f"Save this link, you may need it for eSIM activation."
            ),
            parse_mode="Markdown"
        )
        await callback.answer()

# Обработчик для просмотра информации о eSIM
@router.callback_query(lambda c: c.data.startswith("view_esim:"))
async def view_esim_info(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Отображает информацию о eSIM"""
    esim_id = int(callback.data.split(":")[1])
    user_data = await state.get_data()
    language_code = user_data.get("language_code", "ru")
    
    # Получаем eSIM из БД
    result = await session.execute(
        select(ESim)
        .where(ESim.id == esim_id)
        .options(
            joinedload(ESim.order).joinedload(Order.package).joinedload(Package.country),
            joinedload(ESim.order).joinedload(Order.user)
        )
    )
    esim = result.scalars().first()
    
    if not esim:
        logger.error(f"eSIM not found: {esim_id}")
        message_text = (
            "❌ Ошибка: eSIM не найдена.\n\n"
            "Пожалуйста, вернитесь в список eSIM и попробуйте снова."
        ) if language_code == 'ru' else (
            "❌ Error: eSIM not found.\n\n"
            "Please return to the eSIM list and try again."
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(
            text="◀️ Назад к списку" if language_code == 'ru' else "◀️ Back to list",
            callback_data="my_esims"
        )
        
        try:
            await callback.message.edit_text(
                message_text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                # Игнорируем ошибку, если сообщение не изменилось
                await callback.answer()
            else:
                # Пробрасываем другие ошибки
                raise
        return
    
    # Получаем пакет и страну
    package = esim.order.package
    country = package.country
    
    # Проверяем статус eSIM через API провайдера
    esim_status = await esim_service.check_esim_status(esim.esim_tran_no, esim.iccid)
    
    # Форматируем дату создания
    created_date = format_datetime(esim.created_at, language=language_code)
    
    # Формируем сообщение с информацией о eSIM
    if esim_status.get('success'):
        # Обновляем статус eSIM в БД, если получили новый статус
        if 'smdpStatus' in esim_status:
            esim.esim_status = esim_status['smdpStatus']
            await session.commit()
        
        # Получаем информацию о балансе
        data_balance = esim_status.get('dataBalance', 'N/A')
        data_used = esim_status.get('dataUsed', 'N/A')
        expiry_date = esim_status.get('expiryDate', None)
        
        if expiry_date:
            expiry_date = format_datetime(expiry_date, language=language_code)
        else:
            expiry_date = "N/A"
        
        message_text = (
            f"📱 <b>Информация о eSIM</b>\n\n"
            f"Страна: {country.flag_emoji} {country.name}\n"
            f"Пакет: {package.data_amount} ГБ на {package.duration} дней\n"
            f"ICCID: <code>{esim.iccid}</code>\n"
            f"Статус: {format_esim_status(esim.esim_status, language_code)}\n"
            f"Создана: {created_date}\n\n"
            f"Баланс трафика: {data_balance}\n"
            f"Использовано: {data_used}\n"
            f"Действует до: {expiry_date}"
        ) if language_code == 'ru' else (
            f"📱 <b>eSIM Information</b>\n\n"
            f"Country: {country.flag_emoji} {country.name}\n"
            f"Package: {package.data_amount} GB for {package.duration} days\n"
            f"ICCID: <code>{esim.iccid}</code>\n"
            f"Status: {format_esim_status(esim.esim_status, language_code)}\n"
            f"Created: {created_date}\n\n"
            f"Data Balance: {data_balance}\n"
            f"Data Used: {data_used}\n"
            f"Valid Until: {expiry_date}"
        )
    else:
        # Если не удалось получить статус, показываем последние известные данные
        logger.error(f"Failed to get eSIM status: {esim_status.get('error')}")
        
        message_text = (
            f"📱 <b>Информация о eSIM</b>\n\n"
            f"Страна: {country.flag_emoji} {country.name}\n"
            f"Пакет: {package.data_amount} ГБ на {package.duration} дней\n"
            f"ICCID: <code>{esim.iccid}</code>\n"
            f"Статус: {format_esim_status(esim.esim_status, language_code)}\n"
            f"Создана: {created_date}\n\n"
            f"❗ <b>Не удалось получить актуальный статус eSIM</b>\n"
            f"Ошибка: {esim_status.get('error', 'Неизвестная ошибка')}\n\n"
            f"Показаны последние известные данные."
        ) if language_code == 'ru' else (
            f"📱 <b>eSIM Information</b>\n\n"
            f"Country: {country.flag_emoji} {country.name}\n"
            f"Package: {package.data_amount} GB for {package.duration} days\n"
            f"ICCID: <code>{esim.iccid}</code>\n"
            f"Status: {format_esim_status(esim.esim_status, language_code)}\n"
            f"Created: {created_date}\n\n"
            f"❗ <b>Failed to get current eSIM status</b>\n"
            f"Error: {esim_status.get('error', 'Unknown error')}\n\n"
            f"Showing last known data."
        )
    
    # Создаем клавиатуру с кнопками
    builder = InlineKeyboardBuilder()
    
    # Кнопка пополнения трафика
    builder.button(
        text="🔋 Пополнить трафик" if language_code == 'ru' else "🔋 Top Up Data",
        callback_data=f"topup_esim:{esim_id}"
    )
    
    # Кнопка QR-кода
    builder.button(
        text="📲 QR-код" if language_code == 'ru' else "📲 QR Code",
        callback_data=f"qr_code:{esim_id}"
    )
    
    # Кнопка назад к списку eSIM
    builder.button(
        text="◀️ Назад к списку" if language_code == 'ru' else "◀️ Back to list",
        callback_data="my_esims"
    )
    
    # Кнопка назад в главное меню
    builder.button(
        text="🏠 Главное меню" if language_code == 'ru' else "🏠 Main Menu",
        callback_data="main_menu"
    )
    
    # Настраиваем расположение кнопок (по две в ряд)
    builder.adjust(2)
    
    try:
        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            # Игнорируем ошибку, если сообщение не изменилось
            await callback.answer()
        else:
            # Пробрасываем другие ошибки
            raise

# Обработчик для просмотра истории заказов
@router.callback_query(F.data == "order_history")
async def order_history(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик для отображения истории заказов пользователя"""
    user_data = await state.get_data()
    language_code = user_data.get("language_code", "ru")
    
    # Инициализируем страницу, если это первый вызов
    page = 1
    await state.update_data(order_history_page=page)
    
    # Получаем пользователя из БД
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        logger.error(f"User not found: {callback.from_user.id}")
        await callback.answer("Ошибка: пользователь не найден" if language_code == 'ru' else "Error: user not found")
        return
    
    # Получаем заказы пользователя, отсортированные по дате создания (сначала новые)
    result = await session.execute(
        select(Order)
        .where(Order.user_id == user.id)
        .options(
            joinedload(Order.package).joinedload(Package.country),
            joinedload(Order.esim)
        )
        .order_by(desc(Order.created_at))
    )
    orders = result.unique().scalars().all()
    
    if not orders:
        # Если у пользователя нет заказов
        message_text = (
            "У вас пока нет заказов.\n\n"
            "Вы можете приобрести eSIM в главном меню."
        ) if language_code == 'ru' else (
            "You don't have any orders yet.\n\n"
            "You can purchase an eSIM from the main menu."
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(
            text="🏠 Главное меню" if language_code == 'ru' else "🏠 Main Menu",
            callback_data="main_menu"
        )
        builder.button(
            text="◀️ Назад" if language_code == 'ru' else "◀️ Back",
            callback_data="account"
        )
        builder.adjust(1)
        
        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup()
        )
        return
    
    # Сохраняем все заказы в состоянии для использования при пагинации
    await state.update_data(all_orders_ids=[order.id for order in orders])
    
    # Отображаем заказы с учетом пагинации
    await display_orders_page(callback, state, session, orders, page, language_code)

# Функция для отображения страницы с заказами
async def display_orders_page(callback: CallbackQuery, state: FSMContext, session: AsyncSession, 
                             orders: list, page: int, language_code: str):
    """Отображает страницу с заказами с учетом пагинации"""
    # Количество заказов на странице
    orders_per_page = 10
    
    # Вычисляем общее количество страниц
    total_pages = (len(orders) + orders_per_page - 1) // orders_per_page
    
    # Проверяем, что страница в допустимых пределах
    if page < 1:
        page = 1
    elif page > total_pages:
        page = total_pages
    
    # Вычисляем индексы для текущей страницы
    start_idx = (page - 1) * orders_per_page
    end_idx = min(start_idx + orders_per_page, len(orders))
    
    # Получаем заказы для текущей страницы
    current_page_orders = orders[start_idx:end_idx]
    
    # Формируем сообщение с историей заказов
    message_text = (
        "📋 *История заказов*\n\n"
    ) if language_code == 'ru' else (
        "📋 *Order History*\n\n"
    )
    
    # Добавляем информацию о каждом заказе на текущей странице
    for i, order in enumerate(current_page_orders, start_idx + 1):
        # Получаем пакет, связанный с заказом
        package = order.package
        
        # Форматируем дату создания
        created_date = format_datetime(order.created_at, language=language_code)
        
        # Определяем статус заказа
        status_text = order.status
        if language_code == 'ru':
            status_display = {
                OrderStatus.CREATED.value: "🔄 Создан",
                OrderStatus.AWAITING_PAYMENT.value: "⏳ Ожидает оплаты",
                OrderStatus.PAID.value: "💰 Оплачен",
                OrderStatus.PROCESSING.value: "⚙️ Обрабатывается",
                OrderStatus.COMPLETED.value: "✅ Завершен",
                OrderStatus.FAILED.value: "❌ Ошибка",
                OrderStatus.CANCELED.value: "❌ Отменен"
            }.get(status_text, status_text)
        else:
            status_display = {
                OrderStatus.CREATED.value: "🔄 Created",
                OrderStatus.AWAITING_PAYMENT.value: "⏳ Pending payment",
                OrderStatus.PAID.value: "💰 Paid",
                OrderStatus.PROCESSING.value: "⚙️ Processing",
                OrderStatus.COMPLETED.value: "✅ Completed",
                OrderStatus.FAILED.value: "❌ Failed",
                OrderStatus.CANCELED.value: "❌ Canceled"
            }.get(status_text, status_text)
        
        # Добавляем информацию о заказе в сообщение
        message_text += (
            f"*{i}. Заказ #{order.id}*\n"
            f"Страна: {package.country.name}\n"
            f"Пакет: {package.data_amount} ГБ на {package.duration} дней\n"
            f"Сумма: ${order.amount:.2f}\n"
            f"Статус: {status_display}\n"
            f"Дата: {created_date}\n\n"
        ) if language_code == 'ru' else (
            f"*{i}. Order #{order.id}*\n"
            f"Country: {package.country.name}\n"
            f"Package: {package.data_amount} GB for {package.duration} days\n"
            f"Amount: ${order.amount:.2f}\n"
            f"Status: {status_display}\n"
            f"Date: {created_date}\n\n"
        )
    
    # Добавляем информацию о пагинации
    message_text += (
        f"_Страница {page} из {total_pages} (всего заказов: {len(orders)})_\n\n"
    ) if language_code == 'ru' else (
        f"_Page {page} of {total_pages} (total orders: {len(orders)})_\n\n"
    )
    
    # Создаем клавиатуру
    builder = InlineKeyboardBuilder()
    
    # Создаем список для кнопок навигации
    nav_buttons = []
    
    # Добавляем кнопки навигации, если есть несколько страниц
    if total_pages > 1:
        # Кнопка "Предыдущая страница", если мы не на первой странице
        if page > 1:
            nav_buttons.append({
                "text": "◀️ Назад" if language_code == 'ru' else "◀️ Previous",
                "callback_data": f"order_page:{page-1}"
            })
        
        # Кнопка "Следующая страница", если мы не на последней странице
        if page < total_pages:
            nav_buttons.append({
                "text": "Вперед ▶️" if language_code == 'ru' else "Next ▶️",
                "callback_data": f"order_page:{page+1}"
            })
    
    # Добавляем навигационные кнопки в builder
    for button in nav_buttons:
        builder.button(text=button["text"], callback_data=button["callback_data"])
    
    # Добавляем кнопку для возврата в личный кабинет
    builder.button(
        text="👤 Личный кабинет" if language_code == 'ru' else "👤 Account",
        callback_data="account"
    )
    
    # Добавляем кнопку для возврата в главное меню
    builder.button(
        text="🏠 Главное меню" if language_code == 'ru' else "🏠 Main Menu",
        callback_data="main_menu"
    )
    
    # Настраиваем расположение кнопок
    # Если есть навигационные кнопки, то располагаем их в первом ряду
    # А кнопки "Личный кабинет" и "Главное меню" во втором ряду
    if len(nav_buttons) == 2:
        builder.adjust(2, 2)  # Два ряда по две кнопки
    elif len(nav_buttons) == 1:
        builder.adjust(1, 2)  # Первый ряд - одна кнопка, второй ряд - две кнопки
    else:
        builder.adjust(2)  # Только один ряд с двумя кнопками
    
    # Устанавливаем состояние
    await state.set_state(AccountMenu.orders)
    
    # Отправляем сообщение
    await callback.message.edit_text(
        message_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

# Обработчик для переключения между страницами истории заказов
@router.callback_query(F.data.startswith("order_page:"))
async def switch_order_page(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик для переключения между страницами истории заказов"""
    # Получаем номер страницы из callback_data
    page = int(callback.data.split(":")[1])
    
    # Получаем данные из состояния
    user_data = await state.get_data()
    language_code = user_data.get("language_code", "ru")
    all_orders_ids = user_data.get("all_orders_ids", [])
    
    # Получаем пользователя из БД
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        logger.error(f"User not found: {callback.from_user.id}")
        await callback.answer("Ошибка: пользователь не найден" if language_code == 'ru' else "Error: user not found")
        return
    
    # Получаем все заказы из базы данных по их ID
    result = await session.execute(
        select(Order)
        .where(Order.id.in_(all_orders_ids))
        .options(
            joinedload(Order.package).joinedload(Package.country),
            joinedload(Order.esim)
        )
        .order_by(desc(Order.created_at))
    )
    orders = result.unique().scalars().all()
    
    # Обновляем страницу в состоянии
    await state.update_data(order_history_page=page)
    
    # Отображаем заказы для выбранной страницы
    await display_orders_page(callback, state, session, orders, page, language_code)

# Обработчик для пополнения трафика eSIM
@router.callback_query(lambda c: c.data.startswith("topup_esim:"))
async def topup_esim(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик для пополнения трафика eSIM"""
    esim_id = int(callback.data.split(":")[1])
    user_data = await state.get_data()
    language_code = user_data.get("language_code", "ru")
    
    # Получаем eSIM из БД с предварительной загрузкой связанных объектов
    result = await session.execute(
        select(ESim)
        .where(ESim.id == esim_id)
        .options(
            joinedload(ESim.order).joinedload(Order.package).joinedload(Package.country),
            joinedload(ESim.order).joinedload(Order.user)
        )
    )
    esim = result.scalars().first()
    
    if not esim:
        logger.error(f"eSIM not found: {esim_id}")
        message_text = (
            "❌ Ошибка: eSIM не найдена.\n\n"
            "Пожалуйста, вернитесь в список eSIM и попробуйте снова."
        ) if language_code == 'ru' else (
            "❌ Error: eSIM not found.\n\n"
            "Please return to the eSIM list and try again."
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(
            text="◀️ Назад к списку" if language_code == 'ru' else "◀️ Back to list",
            callback_data="my_esims"
        )
        
        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup()
        )
        return
    
    # Получаем страну из пакета eSIM
    country = esim.order.package.country
    
    # Получаем доступные пакеты для этой страны
    packages_result = await session.execute(
        select(Package)
        .where(
            Package.country_id == country.id,
            Package.is_available == True
        )
        .order_by(Package.price)
    )
    packages = packages_result.scalars().all()
    
    if not packages:
        message_text = (
            "❌ К сожалению, в данный момент нет доступных пакетов для пополнения трафика "
            f"для страны {country.name}.\n\n"
            "Пожалуйста, попробуйте позже или обратитесь в поддержку."
        ) if language_code == 'ru' else (
            "❌ Unfortunately, there are no available packages to top up data "
            f"for {country.name} at the moment.\n\n"
            "Please try again later or contact support."
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(
            text="◀️ Назад" if language_code == 'ru' else "◀️ Back",
            callback_data=f"view_esim:{esim.id}"
        )
        
        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup()
        )
        return
    
    # Сохраняем ID eSIM в состоянии
    await state.update_data(topup_esim_id=esim.id)
    
    # Устанавливаем состояние выбора длительности пакета
    await state.set_state(TopUpESim.select_duration)
    
    # Формируем сообщение с доступными длительностями
    title = (
        f"🔋 <b>Пополнение трафика для eSIM</b>\n\n"
        f"Страна: {country.flag_emoji} {country.name}\n"
        f"ICCID: <code>{esim.iccid}</code>\n\n"
        f"Выберите длительность пакета:"
    ) if language_code == 'ru' else (
        f"🔋 <b>Top Up Data for eSIM</b>\n\n"
        f"Country: {country.flag_emoji} {country.name}\n"
        f"ICCID: <code>{esim.iccid}</code>\n\n"
        f"Select package duration:"
    )
    
    # Группируем пакеты по длительности
    durations = set()
    for package in packages:
        durations.add(package.duration)
    
    # Сортируем длительности по возрастанию
    durations = sorted(durations)
    
    # Создаем клавиатуру с длительностями
    builder = InlineKeyboardBuilder()
    
    # Добавляем кнопки для каждой длительности
    for duration in durations:
        if language_code == 'ru':
            button_text = f"📅 {duration} дней"
        else:
            button_text = f"📅 {duration} days"
        
        builder.button(
            text=button_text,
            callback_data=f"topup_select_duration:{esim.id}:{duration}"
        )
    
    # Добавляем кнопку назад к выбору eSIM
    builder.button(
        text="◀️ Назад" if language_code == 'ru' else "◀️ Back",
        callback_data=f"check_esim_status:{esim.id}"
    )

    # Настраиваем расположение кнопок
    builder.adjust(2)
    
    try:
        await callback.message.edit_text(
            title,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            # Игнорируем ошибку, если сообщение не изменилось
            await callback.answer()
        else:
            # Пробрасываем другие ошибки
            raise

# Обработчик для выбора длительности пакета для пополнения
@router.callback_query(lambda c: c.data.startswith("topup_select_duration:"))
async def select_duration(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик выбора длительности пакета для пополнения трафика"""
    esim_id = int(callback.data.split(":")[1])
    duration = int(callback.data.split(":")[2])
    user_data = await state.get_data()
    language_code = user_data.get("language_code", "ru")
    
    # Получаем eSIM из БД
    result = await session.execute(
        select(ESim)
        .where(ESim.id == esim_id)
        .options(
            joinedload(ESim.order).joinedload(Order.package).joinedload(Package.country)
        )
    )
    esim = result.scalars().first()
    
    if not esim:
        logger.error(f"eSIM not found: {esim_id}")
        message_text = (
            "❌ Ошибка: eSIM не найдена.\n\n"
            "Пожалуйста, вернитесь в список eSIM и попробуйте снова."
        ) if language_code == 'ru' else (
            "❌ Error: eSIM not found.\n\n"
            "Please return to the eSIM list and try again."
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(
            text="◀️ Назад к списку" if language_code == 'ru' else "◀️ Back to list",
            callback_data="my_esims"
        )
        
        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup()
        )
        return
    
    # Получаем доступные пакеты для этой страны и выбранной длительности
    packages_result = await session.execute(
        select(Package)
        .where(
            Package.country_id == esim.order.package.country_id,
            Package.duration == duration,
            Package.is_available == True
        )
        .order_by(Package.price)
    )
    packages = packages_result.scalars().all()
    
    if not packages:
        message_text = (
            "❌ К сожалению, в данный момент нет доступных пакетов для пополнения трафика "
            f"для страны {esim.order.package.country.name} и выбранной длительности.\n\n"
            "Пожалуйста, попробуйте позже или обратитесь в поддержку."
        ) if language_code == 'ru' else (
            "❌ Unfortunately, there are no available packages to top up data "
            f"for {esim.order.package.country.name} and the selected duration at the moment.\n\n"
            "Please try again later or contact support."
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(
            text="◀️ Назад" if language_code == 'ru' else "◀️ Back",
            callback_data=f"topup_esim:{esim.id}"
        )
        
        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup()
        )
        return
    
    # Сохраняем ID eSIM и выбранную длительность в состоянии
    await state.update_data(topup_duration=duration)
    
    # Устанавливаем состояние выбора пакета
    await state.set_state(TopUpESim.select_package)
    
    # Формируем сообщение с доступными пакетами
    title = (
        f"🔋 <b>Пополнение трафика для eSIM</b>\n\n"
        f"Страна: {esim.order.package.country.flag_emoji} {esim.order.package.country.name}\n"
        f"ICCID: <code>{esim.iccid}</code>\n"
        f"Длительность: {duration} дней\n\n"
        f"Выберите пакет для пополнения трафика:"
    ) if language_code == 'ru' else (
        f"🔋 <b>Top Up Data for eSIM</b>\n\n"
        f"Country: {esim.order.package.country.flag_emoji} {esim.order.package.country.name}\n"
        f"ICCID: <code>{esim.iccid}</code>\n"
        f"Duration: {duration} days\n\n"
        f"Select a package to top up data:"
    )
    
    # Создаем клавиатуру с пакетами
    builder = InlineKeyboardBuilder()
    
    # Добавляем кнопки для каждого пакета
    for package in packages:
        # Формируем текст кнопки
        price_text = f"{package.price:.2f} USD"
        data_text = f"{package.data_amount} GB"
        
        button_text = f"{data_text} - {price_text}"
        
        builder.button(
            text=button_text,
            callback_data=f"select_topup_package:{package.id}"
        )
    
    # Добавляем кнопку назад к выбору длительности
    builder.button(
        text="◀️ Назад" if language_code == 'ru' else "◀️ Back",
        callback_data=f"back_to_duration_selection:{esim.id}"
    )
    
    # Настраиваем расположение кнопок (по две в ряд)
    builder.adjust(2)
    
    try:
        await callback.message.edit_text(
            title,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            # Игнорируем ошибку, если сообщение не изменилось
            await callback.answer()
        else:
            # Пробрасываем другие ошибки
            raise

# Обработчик выбора пакета для пополнения
@router.callback_query(TopUpESim.select_package, lambda c: c.data.startswith("select_topup_package:"))
async def select_topup_package(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик выбора пакета для пополнения трафика"""
    package_id = int(callback.data.split(":")[1])
    user_data = await state.get_data()
    language_code = user_data.get("language_code", "ru")
    esim_id = user_data.get("topup_esim_id")
    
    # Получаем пакет из БД
    result = await session.execute(
        select(Package)
        .where(Package.id == package_id)
        .options(
            joinedload(Package.country)
        )
    )
    package = result.scalars().first()
    
    if not package:
        logger.error(f"Package not found: {package_id}")
        message_text = (
            "❌ Ошибка: пакет не найден.\n\n"
            "Пожалуйста, вернитесь к выбору пакета и попробуйте снова."
        ) if language_code == 'ru' else (
            "❌ Error: package not found.\n\n"
            "Please return to package selection and try again."
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(
            text="◀️ Назад" if language_code == 'ru' else "◀️ Back",
            callback_data=f"topup_esim:{esim_id}"
        )
        
        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup()
        )
        return
    
    # Получаем eSIM из БД
    result = await session.execute(
        select(ESim)
        .where(ESim.id == esim_id)
        .options(
            joinedload(ESim.order).joinedload(Order.package).joinedload(Package.country)
        )
    )
    esim = result.scalars().first()
    
    if not esim:
        logger.error(f"eSIM not found: {esim_id}")
        message_text = (
            "❌ Ошибка: eSIM не найдена.\n\n"
            "Пожалуйста, вернитесь в список eSIM и попробуйте снова."
        ) if language_code == 'ru' else (
            "❌ Error: eSIM not found.\n\n"
            "Please return to the eSIM list and try again."
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(
            text="◀️ Назад к списку" if language_code == 'ru' else "◀️ Back to list",
            callback_data="my_esims"
        )
        
        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup()
        )
        return
    
    # Сохраняем ID пакета в состоянии
    await state.update_data(topup_package_id=package_id)
    
    # Устанавливаем состояние подтверждения оплаты
    await state.set_state(TopUpESim.confirm_payment)
    
    # Формируем сообщение с подтверждением
    price_text = f"{package.price:.2f} USD"
    data_text = f"{package.data_amount} GB"
    validity_text = f"{package.duration} дней" if language_code == 'ru' else f"{package.duration} days"
    
    message_text = (
        f"🔋 <b>Подтверждение пополнения трафика</b>\n\n"
        f"Страна: {package.country.flag_emoji} {package.country.name}\n"
        f"ICCID: <code>{esim.iccid}</code>\n\n"
        f"<b>Выбранный пакет:</b>\n"
        f"• Трафик: {data_text}\n"
        f"• Срок действия: {validity_text}\n"
        f"• Стоимость: {price_text}\n\n"
        f"Для подтверждения и перехода к оплате нажмите кнопку «Оплатить»."
    ) if language_code == 'ru' else (
        f"🔋 <b>Confirm Data Top Up</b>\n\n"
        f"Country: {package.country.flag_emoji} {package.country.name}\n"
        f"ICCID: <code>{esim.iccid}</code>\n\n"
        f"<b>Selected package:</b>\n"
        f"• Data: {data_text}\n"
        f"• Validity: {validity_text}\n"
        f"• Price: {price_text}\n\n"
        f"To confirm and proceed to payment, click the 'Pay' button."
    )
    
    # Создаем клавиатуру с кнопками подтверждения и отмены
    builder = InlineKeyboardBuilder()
    
    # Кнопка оплаты
    builder.button(
        text="💳 Оплатить" if language_code == 'ru' else "💳 Pay",
        callback_data="confirm_topup_payment"
    )
    
    # Кнопка назад к выбору пакета
    builder.button(
        text="◀️ Назад" if language_code == 'ru' else "◀️ Back",
        callback_data=f"topup_select_duration:{esim.id}:{package.duration}"
    )
    
    # Устанавливаем расположение кнопок
    builder.adjust(1)
    
    try:
        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            # Игнорируем ошибку, если сообщение не изменилось
            await callback.answer()
        else:
            # Пробрасываем другие ошибки
            raise
        
# Обработчик подтверждения оплаты пополнения трафика
@router.callback_query(F.data == "confirm_topup_payment", TopUpESim.confirm_payment)
async def confirm_topup_payment(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик подтверждения оплаты пополнения трафика"""
    user_data = await state.get_data()
    language_code = user_data.get("language_code", "ru")
    esim_id = user_data.get("topup_esim_id")
    package_id = user_data.get("topup_package_id")
    
    if not esim_id or not package_id:
        logger.error(f"Missing esim_id or package_id in state: {user_data}")
        message_text = (
            "❌ Ошибка: недостаточно данных для создания заказа.\n\n"
            "Пожалуйста, вернитесь к выбору пакета и попробуйте снова."
        ) if language_code == 'ru' else (
            "❌ Error: insufficient data to create an order.\n\n"
            "Please return to package selection and try again."
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(
            text="◀️ Назад" if language_code == 'ru' else "◀️ Back",
            callback_data=f"topup_esim:{esim_id}"
        )
        
        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup()
        )
        return
    
    # Получаем eSIM из БД
    result = await session.execute(
        select(ESim)
        .where(ESim.id == esim_id)
        .options(
            joinedload(ESim.order).joinedload(Order.package).joinedload(Package.country),
            joinedload(ESim.order).joinedload(Order.user)
        )
    )
    esim = result.scalars().first()
    
    if not esim:
        logger.error(f"eSIM not found: {esim_id}")
        message_text = (
            "❌ Ошибка: eSIM не найдена.\n\n"
            "Пожалуйста, вернитесь в список eSIM и попробуйте снова."
        ) if language_code == 'ru' else (
            "❌ Error: eSIM not found.\n\n"
            "Please return to the eSIM list and try again."
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(
            text="◀️ Назад к списку" if language_code == 'ru' else "◀️ Back to list",
            callback_data="my_esims"
        )
        
        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup()
        )
        return
    
    # Получаем пакет из БД
    result = await session.execute(
        select(Package)
        .where(Package.id == package_id)
        .options(
            joinedload(Package.country)
        )
    )
    package = result.scalars().first()
    
    if not package:
        logger.error(f"Package not found: {package_id}")
        message_text = (
            "❌ Ошибка: пакет не найден.\n\n"
            "Пожалуйста, вернитесь к выбору пакета и попробуйте снова."
        ) if language_code == 'ru' else (
            "❌ Error: package not found.\n\n"
            "Please return to package selection and try again."
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(
            text="◀️ Назад" if language_code == 'ru' else "◀️ Back",
            callback_data=f"topup_esim:{esim.id}"
        )
        
        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup()
        )
        return
    
    # Создаем новый заказ на пополнение трафика
    new_order = Order(
        user_id=esim.order.user_id,
        package_id=package.id,
        transaction_id=f"topup-{esim.iccid}-{int(datetime.utcnow().timestamp())}",
        status=OrderStatus.CREATED.value,
        amount=package.price,
        created_at=datetime.utcnow(),
        order_type=OrderType.TOPUP.value  # Указываем тип заказа как TOPUP
    )
    
    session.add(new_order)
    await session.commit()
    
    # Сообщаем пользователю информацию о пополнении трафика и перенаправляем на оплату
    country_name = package.country.name if package.country else "Неизвестная страна"
    country_flag = package.country.flag_emoji if package.country else "🌍"
    
    message_text = (
        f"� *Выбранный пакет:*\n"
        f"🌍 Страна: {country_name}\n"
        f"📱 ICCID: {esim.iccid}\n"
        f"📊 Данные: {package.data_amount} ГБ\n"
        f"⏱️ Срок действия: {package.duration} дней\n"
        f"💰 Стоимость: ${package.price:.2f}\n\n"
        f"Выберите способ оплаты:"
    ) if language_code == 'ru' else (
        f"� *Selected package:*\n"
        f"🌍 Country: {country_name}\n"
        f"📱 ICCID: {esim.iccid}\n"
        f"📊 Data: {package.data_amount} GB\n"
        f"⏱️ Duration: {package.duration} days\n"
        f"💰 Price: ${package.price:.2f}\n\n"
        f"Choose payment method:"
    )
    
    # Создаем клавиатуру для выбора способа оплаты
    builder = InlineKeyboardBuilder()
    
    if language_code == 'ru':
        builder.button(text="💳 Оплатить (CryptoBot)", callback_data=f"payment:ton:{new_order.id}")
        builder.button(text="↩️ Вернуться к выбору пакета", callback_data=f"back_to_package_selection:{esim.id}")
        builder.button(text="🏠 Главное меню", callback_data="main_menu")
    else:
        builder.button(text="💳 Pay with Crypto (CryptoBot)", callback_data=f"payment:ton:{new_order.id}")
        builder.button(text="↩️ Back to package selection", callback_data=f"back_to_package_selection:{esim.id}")
        builder.button(text="🏠 Main menu", callback_data="main_menu")
    
    builder.adjust(1)
    
    await callback.message.edit_text(
        message_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    
    # Устанавливаем состояние ожидания оплаты
    await state.update_data(order_id=new_order.id)
    await state.set_state(TopUpESim.select_payment)
    
# Обработчик для кнопки "Назад" в меню выбора пакета для пополнения
@router.callback_query(lambda c: c.data.startswith("back_to_package_select:"))
async def back_to_package_selection(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик возврата к выбору пакета"""
    esim_id = int(callback.data.split(":")[1])
    user_data = await state.get_data()
    language_code = user_data.get("language_code", "ru")
    duration = user_data.get("topup_duration")
    
    if not duration:
        logger.error("Duration not found in state")
        await callback.answer(
            "Ошибка: длительность не найдена" if language_code == 'ru' else "Error: duration not found",
            show_alert=True
        )
        return
    
    # Получаем eSIM из БД
    result = await session.execute(
        select(ESim)
        .where(ESim.id == esim_id)
        .options(
            joinedload(ESim.order).joinedload(Order.package).joinedload(Package.country)
        )
    )
    esim = result.scalars().first()
    
    if not esim:
        logger.error(f"eSIM not found: {esim_id}")
        message_text = (
            "❌ Ошибка: eSIM не найдена.\n\n"
            "Пожалуйста, вернитесь в список eSIM и попробуйте снова."
        ) if language_code == 'ru' else (
            "❌ Error: eSIM not found.\n\n"
            "Please return to the eSIM list and try again."
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(
            text="◀️ Назад к списку" if language_code == 'ru' else "◀️ Back to list",
            callback_data="my_esims"
        )
        
        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup()
        )
        return
    
    # Получаем доступные пакеты для этой страны и выбранной длительности
    packages_result = await session.execute(
        select(Package)
        .where(
            Package.country_id == esim.order.package.country_id,
            Package.duration == duration,
            Package.is_available == True
        )
        .order_by(Package.price)
    )
    packages = packages_result.scalars().all()
    
    # Устанавливаем состояние выбора пакета
    await state.set_state(TopUpESim.select_package)
    
    # Формируем сообщение с доступными пакетами
    title = (
        f"🔋 <b>Пополнение трафика для eSIM</b>\n\n"
        f"Страна: {esim.order.package.country.flag_emoji} {esim.order.package.country.name}\n"
        f"ICCID: <code>{esim.iccid}</code>\n"
        f"Длительность: {duration} дней\n\n"
        f"Выберите пакет для пополнения трафика:"
    ) if language_code == 'ru' else (
        f"🔋 <b>Top Up Data for eSIM</b>\n\n"
        f"Country: {esim.order.package.country.flag_emoji} {esim.order.package.country.name}\n"
        f"ICCID: <code>{esim.iccid}</code>\n"
        f"Duration: {duration} days\n\n"
        f"Select a package to top up data:"
    )
    
    # Создаем клавиатуру с пакетами
    builder = InlineKeyboardBuilder()
    
    # Добавляем кнопки для каждого пакета
    for package in packages:
        # Формируем текст кнопки
        price_text = f"{package.price:.2f} USD"
        data_text = f"{package.data_amount} GB"
        
        button_text = f"{data_text} - {price_text}"
        
        builder.button(
            text=button_text,
            callback_data=f"select_topup_package:{package.id}"
        )
    
    # Добавляем кнопку назад к выбору длительности
    builder.button(
        text="◀️ Назад" if language_code == 'ru' else "◀️ Back",
        callback_data=f"back_to_duration_selection:{esim.id}"
    )
    
    # Настраиваем расположение кнопок (по две в ряду)
    builder.adjust(2)
    
    await callback.message.edit_text(
        title,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


async def get_available_durations(session, country_id):
    """Получает список доступных длительностей пакетов для указанной страны"""
    result = await session.execute(
        select(Package.duration)
        .where(Package.country_id == country_id)
        .where(Package.is_available == True)
        .distinct()
        .order_by(Package.duration)
    )
    return [duration for duration, in result.all()]



# Обработчик для кнопки "Вернуться к выбору длительности" при пополнении трафика
@router.callback_query(lambda c: c.data.startswith("back_to_duration_selection:"))
async def back_to_duration_selection(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик для возврата к выбору длительности пакета при пополнении трафика"""
    esim_id = int(callback.data.split(":")[1])
    user_data = await state.get_data()
    language_code = user_data.get("language_code", "ru")
    
    # Получаем eSIM из БД с предварительной загрузкой связанных объектов
    result = await session.execute(
        select(ESim)
        .where(ESim.id == esim_id)
        .options(
            joinedload(ESim.order).joinedload(Order.package).joinedload(Package.country)
        )
    )
    esim = result.scalars().first()
    
    if not esim:
        logger.error(f"eSIM not found: {esim_id}")
        message_text = (
            "❌ Ошибка: eSIM не найдена.\n\n"
            "Пожалуйста, вернитесь в список eSIM и попробуйте снова."
        ) if language_code == 'ru' else (
            "❌ Error: eSIM not found.\n\n"
            "Please return to the eSIM list and try again."
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(
            text="◀️ Назад к списку" if language_code == 'ru' else "◀️ Back to list",
            callback_data="my_esims"
        )
        
        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup()
        )
        return
    
    # Очищаем данные о выбранной длительности
    await state.update_data(topup_duration=None)
    
    # Получаем доступные длительности пакетов
    durations = await get_available_durations(session, esim.order.package.country_id)
    
    # Устанавливаем состояние выбора длительности
    await state.set_state(TopUpESim.select_duration)
    
    # Сохраняем ID eSIM в состоянии
    await state.update_data(topup_esim_id=esim.id)
    
    # Формируем сообщение с доступными длительностями
    title = (
        f"🔋 <b>Пополнение трафика для eSIM</b>\n\n"
        f"Страна: {esim.order.package.country.flag_emoji} {esim.order.package.country.name}\n"
        f"ICCID: <code>{esim.iccid}</code>\n\n"
        f"Выберите длительность пакета:"
    ) if language_code == 'ru' else (
        f"🔋 <b>Top Up Data for eSIM</b>\n\n"
        f"Country: {esim.order.package.country.flag_emoji} {esim.order.package.country.name}\n"
        f"ICCID: <code>{esim.iccid}</code>\n\n"
        f"Select package duration:"
    )
    
    # Создаем клавиатуру с длительностями
    builder = InlineKeyboardBuilder()
    
    # Добавляем кнопки для каждой длительности
    for duration in durations:
        button_text = f"📅 {duration} дней" if language_code == 'ru' else f"📅 {duration} days"
        builder.button(
            text=button_text,
            callback_data=f"topup_select_duration:{esim.id}:{duration}"
        )
    
    # Добавляем кнопку назад
    builder.button(
        text="◀️ Назад" if language_code == 'ru' else "◀️ Back",
        callback_data=f"check_esim_status:{esim.id}"
    )
    
    # Настраиваем расположение кнопок
    builder.adjust(2)
    
    await callback.message.edit_text(
        title,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

# Обработчик для оплаты через TON (CryptoBot)
@router.callback_query(lambda c: c.data.startswith("payment:ton:"))
async def process_ton_payment(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик для оплаты через TON (CryptoBot)"""
    order_id = int(callback.data.split(":")[2])
    user_data = await state.get_data()
    language_code = user_data.get("language_code", "ru")
    
    # Получаем заказ из БД с предварительной загрузкой связанных объектов
    result = await session.execute(
        select(Order)
        .options(
            joinedload(Order.package).joinedload(Package.country),
            joinedload(Order.user)
        )
        .where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    
    if not order:
        logger.error(f"Order not found: {order_id}")
        await callback.answer(
            "❌ Заказ не найден" if language_code == 'ru' else "❌ Order not found",
            show_alert=True
        )
        return
    
    try:
        # Создаем инвойс в CryptoBot
        invoice = await crypto_bot.create_invoice(
            asset="TON",
            amount=order.package.price,
            description=(
                f"{'Пополнение трафика' if order.order_type == OrderType.TOPUP.value else 'Покупка eSIM'}\n"
                f"Страна: {order.package.country.flag_emoji} {order.package.country.name}\n"
                f"Пакет: {order.package.data_amount} GB на {order.package.duration} дней"
            ),
            payload=f"{order.id}",
            allow_anonymous=False,
            expires_in=3600
        )
        
        # Обновляем статус заказа
        order.payment_url = invoice.pay_url
        order.status = OrderStatus.PENDING.value
        await session.commit()
        
        # Отправляем сообщение с ссылкой на оплату
        message_text = (
            f"💳 <b>{'Оплата пополнения трафика' if order.order_type == OrderType.TOPUP.value else 'Оплата eSIM'}</b>\n\n"
            f"Страна: {order.package.country.flag_emoji} {order.package.country.name}\n"
            f"Пакет: {order.package.data_amount} GB на {order.package.duration} дней\n"
            f"Сумма: {order.package.price:.2f} USD\n\n"
            f"Для оплаты нажмите на кнопку ниже 👇"
        ) if language_code == 'ru' else (
           f"💳 <b>{'Data Top-Up Payment' if order.order_type == OrderType.TOPUP.value else 'eSIM Payment'}</b>\n\n"
            f"Country: {order.package.country.flag_emoji} {order.package.country.name}\n"
            f"Package: {order.package.data_amount} GB for {order.package.duration} days\n"
            f"Amount: {order.package.price:.2f} USD\n\n"
            f"Click the button below to pay 👇"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(
           text="💎 Оплатить через TON" if language_code == 'ru' else "💎 Pay with TON",
            url=invoice.pay_url
        )
        if order.order_type == OrderType.TOPUP.value:
            user_data = await state.get_data()
            esim_id = user_data.get("topup_esim_id")
            if esim_id:
                builder.button(
                    text="◀️ Назад" if language_code == 'ru' else "◀️ Back",
                    callback_data=f"back_to_package_selection:{esim_id}"
                )
            else:
                builder.button(
                    text="◀️ Назад" if language_code == 'ru' else "◀️ Back",
                    callback_data="my_esims"
                )
        else:
            builder.button(
                text="◀️ Назад" if language_code == 'ru' else "◀️ Back",
                callback_data=f"check_order_status:{order.id}"
            )
        builder.adjust(1)
        
        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Error creating TON invoice: {e}")
        await callback.answer(
            "❌ Ошибка при создании счета" if language_code == 'ru' else "❌ Error creating invoice",
            show_alert=True
        )
        return

# Обработчик для оплаты через другую криптовалюту
@router.callback_query(lambda c: c.data.startswith("payment:crypto:"))
async def process_crypto_payment(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик для оплаты через другую криптовалюту"""
    order_id = int(callback.data.split(":")[2])
    user_data = await state.get_data()
    language_code = user_data.get("language_code", "ru")
    
    # Получаем заказ из БД
    result = await session.execute(
        select(Order)
        .where(Order.id == order_id)
        .options(
            joinedload(Order.package).joinedload(Package.country),
            joinedload(Order.user)
        )
    )
    order = result.scalars().first()
    
    if not order:
        logger.error(f"Order not found: {order_id}")
        message_text = (
            "❌ Ошибка: заказ не найден.\n\n"
            "Пожалуйста, начните заново."
        ) if language_code == 'ru' else (
            "❌ Error: order not found.\n\n"
            "Please start over."
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(
            text="🏠 Главное меню" if language_code == 'ru' else "🏠 Main menu",
            callback_data="main_menu"
        )
        
        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup()
        )
        await state.set_state(MainMenu.menu)
        return
    
    # Здесь должна быть логика для создания платежа через другую криптовалюту
    # Это заглушка, которую нужно заменить на реальную интеграцию
    
    # Временное сообщение о том, что функционал в разработке
    message_text = (
        "🚧 Оплата через криптовалюту находится в разработке.\n\n"
        "Пожалуйста, выберите другой способ оплаты или вернитесь позже."
    ) if language_code == 'ru' else (
        "🚧 Payment via cryptocurrency is under development.\n\n"
        "Please choose another payment method or come back later."
    )
    
    builder = InlineKeyboardBuilder()
    
    # Получаем eSIM ID из состояния
    esim_id = user_data.get("topup_esim_id")
    
    if language_code == 'ru':
        builder.button(text="↩️ Вернуться к выбору пакета", callback_data=f"back_to_package_selection:{esim_id}")
        builder.button(text="💎 Оплатить TON (CryptoBot)", callback_data=f"payment:ton:{order_id}")
        builder.button(text="🏠 Главное меню", callback_data="main_menu")
    else:
        builder.button(text="↩️ Back to package selection", callback_data=f"back_to_package_selection:{esim_id}")
        builder.button(text="💎 Pay with TON (CryptoBot)", callback_data=f"payment:ton:{order_id}")
        builder.button(text="🏠 Main menu", callback_data="main_menu")
    
    builder.adjust(1)
    
    await callback.message.edit_text(
        message_text,
        reply_markup=builder.as_markup()
    )

# Обработчик для кнопки "Назад" в меню выбора пакета для пополнения
@router.callback_query(lambda c: c.data.startswith("back_to_package_selection:"))
async def back_to_package_selection(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик возврата к выбору пакета"""
    esim_id = int(callback.data.split(":")[1])
    user_data = await state.get_data()
    language_code = user_data.get("language_code", "ru")
    duration = user_data.get("topup_duration")
    
    if not duration:
        logger.error("Duration not found in state")
        await callback.answer(
            "Ошибка: длительность не найдена" if language_code == 'ru' else "Error: duration not found",
            show_alert=True
        )
        return
    
    # Получаем eSIM из БД
    result = await session.execute(
        select(ESim)
        .where(ESim.id == esim_id)
        .options(
            joinedload(ESim.order).joinedload(Order.package).joinedload(Package.country)
        )
    )
    esim = result.scalars().first()
    
    if not esim:
        logger.error(f"eSIM not found: {esim_id}")
        message_text = (
            "❌ Ошибка: eSIM не найдена.\n\n"
            "Пожалуйста, вернитесь в список eSIM и попробуйте снова."
        ) if language_code == 'ru' else (
            "❌ Error: eSIM not found.\n\n"
            "Please return to the eSIM list and try again."
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(
            text="◀️ Назад к списку" if language_code == 'ru' else "◀️ Back to list",
            callback_data="my_esims"
        )
        
        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup()
        )
        return
    
    # Получаем доступные пакеты для этой страны и выбранной длительности
    packages_result = await session.execute(
        select(Package)
        .where(
            Package.country_id == esim.order.package.country_id,
            Package.duration == duration,
            Package.is_available == True
        )
        .order_by(Package.price)
    )
    packages = packages_result.scalars().all()
    
    # Устанавливаем состояние выбора пакета
    await state.set_state(TopUpESim.select_package)
    
    # Формируем сообщение с доступными пакетами
    title = (
        f"🔋 <b>Пополнение трафика для eSIM</b>\n\n"
        f"Страна: {esim.order.package.country.flag_emoji} {esim.order.package.country.name}\n"
        f"ICCID: <code>{esim.iccid}</code>\n"
        f"Длительность: {duration} дней\n\n"
        f"Выберите пакет для пополнения трафика:"
    ) if language_code == 'ru' else (
        f"🔋 <b>Top Up Data for eSIM</b>\n\n"
        f"Country: {esim.order.package.country.flag_emoji} {esim.order.package.country.name}\n"
        f"ICCID: <code>{esim.iccid}</code>\n"
        f"Duration: {duration} days\n\n"
        f"Select a package to top up data:"
    )
    
    # Создаем клавиатуру с пакетами
    builder = InlineKeyboardBuilder()
    
    # Добавляем кнопки для каждого пакета
    for package in packages:
        # Формируем текст кнопки
        price_text = f"{package.price:.2f} USD"
        data_text = f"{package.data_amount} GB"
        
        button_text = f"{data_text} - {price_text}"
        
        builder.button(
            text=button_text,
            callback_data=f"select_topup_package:{package.id}"
        )
    
    # Добавляем кнопку назад к выбору длительности
    builder.button(
        text="◀️ Назад" if language_code == 'ru' else "◀️ Back",
        callback_data=f"back_to_duration_selection:{esim.id}"
    )
    
    # Настраиваем расположение кнопок (по две в ряду)
    builder.adjust(2)
    
    await callback.message.edit_text(
        title,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )