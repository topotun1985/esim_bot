from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, desc, and_, or_
from sqlalchemy.orm import joinedload
from .models import User, Country, Package, Order, ESim, FAQ, SupportTicket, SupportMessage, OrderStatus
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)

# Пользователи

async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User:
    """Получение пользователя по telegram_id"""
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalars().first()

async def create_user(session: AsyncSession, telegram_id: int, username: str = None, 
                    first_name: str = None, last_name: str = None, language_code: str = 'ru') -> User:
    """Создание нового пользователя"""
    user = User(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        language_code=language_code
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user

async def get_or_create_user(session: AsyncSession, telegram_id: int, username: str = None, 
                           first_name: str = None, last_name: str = None, language_code: str = 'ru') -> User:
    """Получение пользователя или его создание, если не существует"""
    user = await get_user_by_telegram_id(session, telegram_id)
    if not user:
        user = await create_user(session, telegram_id, username, first_name, last_name, language_code)
    return user

async def update_user_language(session: AsyncSession, user_id: int, language_code: str) -> User:
    """Обновление языка пользователя"""
    await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(language_code=language_code, updated_at=datetime.utcnow())
    )
    await session.commit()
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalars().first()

async def get_admin_users(session: AsyncSession) -> list[User]:
    """Получение списка администраторов"""
    result = await session.execute(select(User).where(User.is_admin == True))
    return result.scalars().all()

# Страны

async def get_all_countries(session: AsyncSession, available_only: bool = True) -> list[Country]:
    """Получение списка всех стран"""
    query = select(Country)
    if available_only:
        query = query.where(Country.is_available == True)
    result = await session.execute(query)
    return result.scalars().all()

async def get_country_by_code(session: AsyncSession, code: str) -> Country:
    """Получение страны по коду"""
    result = await session.execute(select(Country).where(Country.code == code))
    return result.scalars().first()

# Пакеты

async def get_packages_by_country(session: AsyncSession, country_id: int, available_only: bool = True) -> list[Package]:
    """Получение списка пакетов для страны"""
    query = select(Package).where(Package.country_id == country_id)
    if available_only:
        query = query.where(Package.is_available == True)
    result = await session.execute(query)
    return result.scalars().all()

async def get_package_by_id(session: AsyncSession, package_id: int) -> Package:
    """Получение пакета по ID с загрузкой связанной страны"""
    result = await session.execute(
        select(Package)
        .where(Package.id == package_id)
        .options(joinedload(Package.country))
    )
    return result.scalars().first()

async def get_package_by_code(session: AsyncSession, package_code: str) -> Package:
    """Получение пакета по коду"""
    try:
        if not package_code:
            logger.warning(f"Попытка получить пакет с пустым кодом")
            return None
            
        result = await session.execute(select(Package).where(Package.package_code == package_code))
        return result.scalars().first()
    except Exception as e:
        logger.error(f"Ошибка при получении пакета по коду {package_code}: {e}")
        return None

async def get_package_by_slug(session: AsyncSession, slug: str) -> Package:
    """Получение пакета по slug"""
    result = await session.execute(select(Package).where(Package.slug == slug))
    return result.scalars().first()

# Заказы

async def create_order(session: AsyncSession, user_id: int, package_id: int, amount: float) -> Order:
    """Создание нового заказа"""
    transaction_id = f"txn_{uuid.uuid4().hex[:16]}_{int(datetime.utcnow().timestamp())}"
    order = Order(
        user_id=user_id,
        package_id=package_id,
        transaction_id=transaction_id,
        status=OrderStatus.CREATED.value,
        amount=amount
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order

async def get_order_by_id(session: AsyncSession, order_id: int) -> Order:
    """Получение заказа по ID"""
    result = await session.execute(
        select(Order).where(Order.id == order_id).options(joinedload(Order.package))
    )
    return result.scalars().first()

async def get_order_by_transaction_id(session: AsyncSession, transaction_id: str) -> Order:
    """Получение заказа по transaction_id"""
    result = await session.execute(
        select(Order).where(Order.transaction_id == transaction_id).options(joinedload(Order.package))
    )
    return result.scalars().first()

async def get_order_by_order_no(session: AsyncSession, order_no: str) -> Order:
    """Получение заказа по order_no (номеру заказа от провайдера)"""
    result = await session.execute(
        select(Order).where(Order.order_no == order_no).options(joinedload(Order.package))
    )
    return result.scalars().first()

async def get_user_orders(session: AsyncSession, user_id: int, limit: int = 10, offset: int = 0) -> list[Order]:
    """Получение заказов пользователя"""
    result = await session.execute(
        select(Order)
        .where(Order.user_id == user_id)
        .options(joinedload(Order.package))
        .order_by(desc(Order.created_at))
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()

async def update_order_status(session: AsyncSession, order_id: int, status: str) -> Order:
    """Обновление статуса заказа"""
    await session.execute(
        update(Order)
        .where(Order.id == order_id)
        .values(status=status, updated_at=datetime.utcnow())
    )
    await session.commit()
    result = await session.execute(select(Order).where(Order.id == order_id))
    return result.scalars().first()

async def update_order_payment_info(session: AsyncSession, order_id: int, payment_method: str, payment_id: str) -> Order:
    """Обновление информации об оплате заказа"""
    await session.execute(
        update(Order)
        .where(Order.id == order_id)
        .values(
            payment_method=payment_method, 
            payment_id=payment_id,
            status=OrderStatus.AWAITING_PAYMENT.value,
            updated_at=datetime.utcnow()
        )
    )
    await session.commit()
    result = await session.execute(select(Order).where(Order.id == order_id))
    return result.scalars().first()

async def update_order_provider_info(session: AsyncSession, order_id: int, order_no: str) -> Order:
    """Обновление информации о заказе от провайдера"""
    await session.execute(
        update(Order)
        .where(Order.id == order_id)
        .values(order_no=order_no, updated_at=datetime.utcnow())
    )
    await session.commit()
    result = await session.execute(select(Order).where(Order.id == order_id))
    return result.scalars().first()

# eSim

async def create_esim(session: AsyncSession, order_id: int, esim_data: dict) -> ESim:
    """Создание новой eSIM из данных от провайдера"""
    esim = ESim(
        order_id=order_id,
        esim_tran_no=esim_data.get('esimTranNo'),
        iccid=esim_data.get('iccid'),
        imsi=esim_data.get('imsi'),
        msisdn=esim_data.get('msisdn'),
        activation_code=esim_data.get('ac'),
        qr_code_url=esim_data.get('qrCodeUrl'),
        short_url=esim_data.get('shortUrl'),
        smdp_status=esim_data.get('smdpStatus'),
        esim_status=esim_data.get('esimStatus'),
        active_type=esim_data.get('activeType'),
        expired_time=datetime.fromisoformat(esim_data.get('expiredTime').replace('Z', '+00:00')) if esim_data.get('expiredTime') else None,
        total_volume=esim_data.get('totalVolume'),
        total_duration=esim_data.get('totalDuration'),
        duration_unit=esim_data.get('durationUnit'),
        order_usage=esim_data.get('orderUsage', 0),
        pin=esim_data.get('pin'),
        puk=esim_data.get('puk'),
        apn=esim_data.get('apn'),
        raw_data=esim_data
    )
    session.add(esim)
    await session.commit()
    await session.refresh(esim)
    return esim

async def get_esim_by_order_id(session: AsyncSession, order_id: int) -> ESim:
    """Получение eSIM по ID заказа"""
    result = await session.execute(select(ESim).where(ESim.order_id == order_id))
    return result.scalars().first()

async def get_esim_by_iccid(session: AsyncSession, iccid: str) -> ESim:
    """Получение eSIM по ICCID"""
    result = await session.execute(select(ESim).where(ESim.iccid == iccid))
    return result.scalars().first()

async def update_esim_usage(session: AsyncSession, esim_id: int, order_usage: int, esim_status: str = None) -> ESim:
    """Обновление информации об использовании трафика eSIM"""
    values = {'order_usage': order_usage, 'updated_at': datetime.utcnow()}
    if esim_status:
        values['esim_status'] = esim_status
    
    await session.execute(
        update(ESim)
        .where(ESim.id == esim_id)
        .values(**values)
    )
    await session.commit()
    result = await session.execute(select(ESim).where(ESim.id == esim_id))
    return result.scalars().first()

# FAQ

async def get_faqs(session: AsyncSession, language_code: str = None) -> list[FAQ]:
    """Получение списка FAQ"""
    query = select(FAQ).where(FAQ.is_active == True).order_by(FAQ.order)
    result = await session.execute(query)
    faqs = result.scalars().all()
    
    # Если указан язык, возвращаем вопросы и ответы на этом языке (если доступны)
    if language_code == 'ru':
        for faq in faqs:
            if faq.question_ru and faq.answer_ru:
                faq.display_question = faq.question_ru
                faq.display_answer = faq.answer_ru
            else:
                faq.display_question = faq.question_en
                faq.display_answer = faq.answer_en
    else:  # По умолчанию английский
        for faq in faqs:
            faq.display_question = faq.question_en
            faq.display_answer = faq.answer_en
            
    return faqs

# Support Tickets

async def create_support_ticket(session: AsyncSession, user_id: int, subject: str, message: str) -> SupportTicket:
    """Создание нового запроса в поддержку"""
    ticket = SupportTicket(
        user_id=user_id,
        subject=subject,
        message=message,
        status='open'
    )
    session.add(ticket)
    await session.commit()
    await session.refresh(ticket)
    
    # Создаем первое сообщение в чате от пользователя
    support_message = SupportMessage(
        ticket_id=ticket.id,
        sender_type='user',
        text=message
    )
    session.add(support_message)
    await session.commit()
    
    return ticket

async def get_user_tickets(session: AsyncSession, user_id: int) -> list[SupportTicket]:
    """Получение запросов в поддержку от пользователя"""
    result = await session.execute(
        select(SupportTicket)
        .where(SupportTicket.user_id == user_id)
        .order_by(desc(SupportTicket.created_at))
    )
    return result.scalars().all()

async def add_message_to_ticket(session: AsyncSession, ticket_id: int, sender_type: str, text: str) -> SupportMessage:
    """Добавление сообщения в чат запроса в поддержку"""
    message = SupportMessage(
        ticket_id=ticket_id,
        sender_type=sender_type,
        text=text
    )
    session.add(message)
    
    # Обновляем время последнего обновления тикета
    await session.execute(
        update(SupportTicket)
        .where(SupportTicket.id == ticket_id)
        .values(updated_at=datetime.utcnow())
    )
    
    await session.commit()
    await session.refresh(message)
    return message

async def get_ticket_messages(session: AsyncSession, ticket_id: int) -> list[SupportMessage]:
    """Получение сообщений для запроса в поддержку"""
    result = await session.execute(
        select(SupportMessage)
        .where(SupportMessage.ticket_id == ticket_id)
        .order_by(SupportMessage.created_at)
    )
    return result.scalars().all()

async def close_support_ticket(session: AsyncSession, ticket_id: int) -> SupportTicket:
    """Закрытие запроса в поддержку"""
    await session.execute(
        update(SupportTicket)
        .where(SupportTicket.id == ticket_id)
        .values(status='closed', updated_at=datetime.utcnow())
    )
    await session.commit()
    result = await session.execute(select(SupportTicket).where(SupportTicket.id == ticket_id))
    return result.scalars().first()

async def get_open_support_tickets(session: AsyncSession) -> list[SupportTicket]:
    """Получение открытых запросов в поддержку"""
    result = await session.execute(
        select(SupportTicket)
        .where(SupportTicket.status == 'open')
        .order_by(SupportTicket.created_at)
        .options(joinedload(SupportTicket.user))
    )
    return result.scalars().all()