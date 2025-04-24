from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import uuid
from datetime import datetime
import os
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from database.models import Order, Package, User, OrderStatus, ESim
from database.queries import get_user_by_telegram_id, get_package_by_id, get_all_countries
from utils.states import BuyESim, PaymentState, CallbackData, MainMenu
from services.payment_service import create_ton_invoice, create_cryptomus_invoice, check_ton_payment, create_crypto_invoice
from handlers.catalog import get_countries_keyboard
from handlers.start import get_main_menu_keyboard
from services.esim_service import esim_service

router = Router()

# Обработчики платежей

# Обработчик выбора способа оплаты
@router.callback_query(F.data == "payment:ton")
async def process_payment_selection(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user_data = await state.get_data()
    package_id = user_data.get("package_id")
    language_code = user_data.get("language_code", "ru")

    # Получаем информацию о пакете и пользователе
    package = await get_package_by_id(session, package_id)
    user = await get_user_by_telegram_id(session, callback.from_user.id)

    if not package or not user:
        await callback.message.edit_text(
            "Произошла ошибка. Пожалуйста, начните заново." if language_code == 'ru' else
            "An error occurred. Please start over.",
            reply_markup=get_main_menu_keyboard(language_code)
        )
        await state.set_state(MainMenu.menu)
        return

    # Проверяем баланс аккаунта провайдера перед созданием заказа
    checking_message = (
        "⏳ Проверяем возможность заказа eSIM...\n\n"
        "Пожалуйста, подождите."
    ) if language_code == 'ru' else (
        "⏳ Checking eSIM availability...\n\n"
        "Please wait."
    )
    
    await callback.message.edit_text(
        checking_message,
        parse_mode="Markdown"
    )
    
    # Проверяем баланс у провайдера
    has_sufficient_balance = await esim_service.check_balance_before_operation("create eSIM")
    
    if not has_sufficient_balance:
        # Если баланс недостаточен, показываем сообщение об ошибке
        error_message = (
            "❌ *Временная техническая проблема*\n\n"
            "К сожалению, в данный момент сервис недоступен из-за проблем с балансом на счете провайдера. "
            "Пожалуйста, попробуйте позже или выберите другой пакет.\n\n"
            "Наши специалисты уже работают над пополнением баланса."
        ) if language_code == 'ru' else (
            "❌ *Temporary technical issue*\n\n"
            "Unfortunately, the service is currently unavailable due to provider account balance issues. "
            "Please try again later or choose another package.\n\n"
            "Our specialists are already working to resolve this issue."
        )
        
        builder = InlineKeyboardBuilder()
        if language_code == 'ru':
            builder.button(text="↩️ Назад к выбору", callback_data="back_to_packages")
            builder.button(text="🏠 Главное меню", callback_data="main_menu")
        else:
            builder.button(text="↩️ Back to selection", callback_data="back_to_packages")
            builder.button(text="🏠 Main menu", callback_data="main_menu")
        
        builder.adjust(1)
        
        await callback.message.edit_text(
            error_message,
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
        await callback.answer()
        return
    
    # Дополнительная проверка баланса с учетом стоимости пакета
    try:
        balance_result = await esim_service.query_balance()
        if balance_result.get("success") and "balance" in balance_result:
            current_balance = balance_result.get("balance", 0)
            min_operational_balance = float(os.getenv("MIN_OPERATIONAL_BALANCE", 5.0))
            
            # Проверяем, хватит ли баланса после покупки пакета
            remaining_balance = current_balance - package.price
            
            if remaining_balance < min_operational_balance:
                # Если баланс после покупки будет ниже минимального, показываем сообщение
                error_message = (
                    f"❌ *Временно недоступно*\n\n"
                    f"К сожалению, в данный момент оплата данного пакета недоступна по техническим причинам. "
                    f"Пожалуйста, выберите другой пакет или попробуйте позже.\n\n"
                    f"Приносим извинения за неудобства."
                ) if language_code == 'ru' else (
                    f"❌ *Temporarily Unavailable*\n\n"
                    f"Unfortunately, payment for this package is currently unavailable due to technical reasons. "
                    f"Please select another package or try again later.\n\n"
                    f"We apologize for the inconvenience."
                )
                
                # Логирование для администратора, но не показывать пользователю
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Невозможно выполнить заказ: недостаточный баланс после покупки. "
                    f"Текущий баланс: ${current_balance:.2f}, Стоимость пакета: ${package.price:.2f}, "
                    f"Мин. остаток: ${min_operational_balance:.2f}, Остаток после покупки: ${remaining_balance:.2f}"
                )
                
                # Отправка уведомления администратору
                admin_chat_id = os.getenv("ADMIN_CHAT_ID")
                if admin_chat_id:
                    try:
                        # Импортируем Bot из aiogram для отправки сообщения
                        from aiogram import Bot
                        
                        # Получаем токен бота
                        bot_token = os.getenv("BOT_TOKEN")
                        if not bot_token:
                            logger.error("❌ Не удалось получить токен бота для отправки уведомления администратору")
                        else:
                            # Создаем экземпляр бота
                            bot = Bot(token=bot_token)
                            
                            # Формируем сообщение
                            admin_message = (
                                f"⚠️ ВНИМАНИЕ! Заблокирована попытка покупки пакета из-за недостаточного баланса:\n\n"
                                f"📊 Стоимость пакета: ${package.price:.2f}\n"
                                f"💰 Текущий баланс: ${current_balance:.2f}\n"
                                f"💵 Мин. требуемый остаток: ${min_operational_balance:.2f}\n"
                                f"📉 Баланс после покупки: ${remaining_balance:.2f}\n\n"
                                f"👤 Пользователь: {user.full_name} (@{callback.from_user.username or 'без имени пользователя'})\n"
                                f"🆔 ID пользователя: {user.telegram_id}\n"
                                f"🌍 Выбранный пакет: {package.name} ({package.country.name if package.country else 'неизвестная страна'})\n\n"
                                f"⏱ Время: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
                            )
                            
                            # Отправляем сообщение администратору
                            await bot.send_message(admin_chat_id, admin_message)
                            logger.info(f"📨 Уведомление о недостаточном балансе отправлено администратору (chat_id: {admin_chat_id})")
                    except Exception as e:
                        logger.error(f"❌ Ошибка при отправке уведомления администратору: {str(e)}")
                else:
                    logger.warning("⚠️ ADMIN_CHAT_ID не установлен. Невозможно отправить уведомление о недостаточном балансе.")
                
                builder = InlineKeyboardBuilder()
                if language_code == 'ru':
                    builder.button(text="↩️ Назад к выбору", callback_data="back_to_packages")
                    builder.button(text="🏠 Главное меню", callback_data="main_menu")
                else:
                    builder.button(text="↩️ Back to selection", callback_data="back_to_packages")
                    builder.button(text="🏠 Main menu", callback_data="main_menu")
                
                builder.adjust(1)
                
                await callback.message.edit_text(
                    error_message,
                    reply_markup=builder.as_markup(),
                    parse_mode="Markdown"
                )
                await callback.answer()
                return
    except Exception as e:
        # В случае ошибки логируем ее, но продолжаем обработку
        logger = logging.getLogger(__name__)
        logger.error(f"Ошибка при проверке баланса с учетом стоимости пакета: {e}")
    
    # Создаем запись заказа в БД
    transaction_id = str(uuid.uuid4())

    new_order = Order(
        user_id=user.id,
        package_id=package_id,
        transaction_id=transaction_id,
        status=OrderStatus.AWAITING_PAYMENT.value,
        amount=package.price,
        created_at=datetime.utcnow()
    )

    session.add(new_order)
    await session.commit()

    # Получаем ID заказа после добавления в БД
    await session.refresh(new_order)  # Обновляем объект для получения ID

    # Сохраняем ID заказа в состоянии
    await state.update_data(order_id=new_order.id)

    payment_method = callback.data.split(":")[1]

    # Пока поддерживается один способ оплаты через CryptoBot.
    # Предлагаем выбрать криптоактив.
    await state.set_state(PaymentState.select_method)

    message_text = (
        "💰 *Выберите криптовалюту для оплаты*" if language_code == 'ru' else
        "💰 *Choose a cryptocurrency to pay*"
    )

    builder = InlineKeyboardBuilder()
    for asset, label in [("TON", "💎 TON"), ("USDT", "💵 USDT"), ("BTC", "₿ BTC")]:
        builder.button(text=label, callback_data=f"payment_asset:{asset}:{new_order.id}")
    builder.button(
        text="❌ Отменить" if language_code == 'ru' else "❌ Cancel",
        callback_data="cancel_payment"
    )
    builder.adjust(1)

    await callback.message.edit_text(
        message_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

    # Завершаем дальнейшую обработку функции (TON/crypto детали ниже больше не нужны)
    return

# -----------------------------------------------------------------------------
# Обработчик выбора криптоактива (TON / USDT / BTC) после создания заказа
@router.callback_query(lambda c: c.data.startswith("payment_asset:"))
async def payment_asset_selected(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    _, asset, order_id = callback.data.split(":")
    user_data = await state.get_data()
    language_code = user_data.get("language_code", "ru")
    
    order = await session.get(Order, int(order_id))
    if order is None:
        await callback.answer("Order not found", show_alert=True)
        return
    # Создаем инвойс в выбранной криптовалюте через CryptoBot
    invoice = await create_crypto_invoice(order.id, order.amount, asset)
    if not invoice:
        await callback.answer("Failed to create invoice", show_alert=True)
        return

    # Форматируем отображение суммы платежа
    amount_display = invoice["amount"]
    asset_emoji = "💰"  # Эмодзи по умолчанию
    
    if asset == "BTC":
        asset_emoji = "₿"  # Эмодзи для Bitcoin
        if invoice["amount"] < 0.0001:
            amount_display = f"{invoice['amount']:.8f}"
        else:
            amount_display = f"{invoice['amount']:.6f}"
    elif asset == "USDT":
        asset_emoji = "💵"  # Эмодзи для USDT
        amount_display = f"{invoice['amount']:.2f}"
    elif asset == "TON":
        asset_emoji = "💎"  # Эмодзи для TON
        amount_display = f"{invoice['amount']:.4f}"
    
    text = f"{asset_emoji} Оплатите {amount_display} {asset} по кнопке ниже:"
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Перейти к оплате", url=invoice["payment_url"])
    kb.button(
        text="↩️ Назад" if language_code == 'ru' else "↩️ Back",
        callback_data=f"back_to_crypto_selection:{order_id}"
    )
    kb.adjust(1)

    await callback.message.edit_text(text, reply_markup=kb.as_markup())

    # Конвертируем invoice_id в строку перед сохранением в базу данных
    order.invoice_id = str(invoice["invoice_id"])
    order.payment_method = f"crypto_{asset.lower()}"
    await session.commit()
    await state.set_state(PaymentState.awaiting_payment)

# Обработчик для возврата к выбору криптовалюты
@router.callback_query(lambda c: c.data.startswith("back_to_crypto_selection:"))
async def back_to_crypto_selection(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    order_id = callback.data.split(":")[1]
    
    # Получаем заказ и данные пользователя
    order = await session.get(Order, int(order_id))
    user_data = await state.get_data()
    language_code = user_data.get("language_code", "ru")
    
    if order is None:
        await callback.answer("Order not found", show_alert=True)
        return
    
    # Возвращаемся к выбору криптовалюты
    await state.set_state(PaymentState.select_method)
    
    message_text = (
        "💰 *Выберите криптовалюту для оплаты*" if language_code == 'ru' else
        "💰 *Choose a cryptocurrency to pay*"
    )
    
    builder = InlineKeyboardBuilder()
    for asset, label in [("TON", "💎 TON"), ("USDT", "💵 USDT"), ("BTC", "₿ BTC")]:
        builder.button(text=label, callback_data=f"payment_asset:{asset}:{order_id}")
    builder.button(
        text="❌ Отменить" if language_code == 'ru' else "❌ Cancel",
        callback_data="cancel_payment"
    )
    builder.adjust(1)
    
    await callback.message.edit_text(
        message_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

# Обработчик проверки статуса оплаты
@router.callback_query(lambda c: c.data.startswith("check_payment:"))
async def check_payment_status(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    import logging
    logger = logging.getLogger(__name__)
    order_id = int(callback.data.split(":")[1])
    logger.info(f"Checking payment status for order_id: {order_id}")

    user_data = await state.get_data()
    language_code = user_data.get("language_code", "ru")

    # Показываем сообщение о проверке
    message_text = (
        "⏳ Проверяем статус оплаты...\n\n"
        "Этот процесс может занять некоторое время. Пожалуйста, подождите."
    ) if language_code == 'ru' else (
        "⏳ Checking payment status...\n\n"
        "This process may take some time. Please wait."
    )

    await callback.message.edit_text(
        message_text,
        reply_markup=None
    )

    # Получаем заказ из БД
    order = await session.get(Order, order_id)
    if not order:
        logger.error(f"Order not found: {order_id}")
        message_text = (
            "\u274c Ошибка: Заказ не найден. Пожалуйста, начните процесс заново."
        ) if language_code == 'ru' else (
            "\u274c Error: Order not found. Please start the process again."
        )

        builder = InlineKeyboardBuilder()
        builder.button(
            text="Вернуться в меню" if language_code == 'ru' else "Return to menu",
            callback_data="main_menu"
        )

        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup()
        )
        return

    if not order.invoice_id:
        logger.error(f"Order {order_id} has no invoice_id")
        await callback.message.edit_text(
            "❌ Ошибка: заказ не содержит данных об оплате. Пожалуйста, начните заново.",
            reply_markup=get_main_menu_keyboard(language_code)
        )
        return

    # Проверяем статус платежа в CryptoBot
    logger.info(f"Checking payment with invoice_id: {order.invoice_id}")
    payment_info = await check_ton_payment(order.invoice_id)

    if payment_info and payment_info.get("paid"):
        # Платеж успешен
        logger.info(f"Payment successful for order {order_id}, updating status to PAID")

        # Обновляем статус заказа в БД
        order.status = OrderStatus.PAID.value
        order.paid_at = datetime.utcnow()
        order.payment_details = str(payment_info)
        await session.commit()

        # Получаем информацию о пакете
        package = await get_package_by_id(session, order.package_id)
        if not package:
            logger.error(f"Package not found for order {order_id}")
            message_text = (
                "✅ *Оплата успешно получена!*\n\n"
                "К сожалению, возникла проблема при активации eSIM. "
                "Наша служба поддержки свяжется с вами в ближайшее время."
            ) if language_code == 'ru' else (
                "✅ *Payment successfully received!*\n\n"
                "Unfortunately, there was an issue with activating your eSIM. "
                "Our support team will contact you soon."
            )

            builder = InlineKeyboardBuilder()
            builder.button(
                text="🏠 Главное меню" if language_code == 'ru' else "🏠 Main menu",
                callback_data="main_menu"
            )

            await callback.message.edit_text(
                message_text,
                reply_markup=builder.as_markup(),
                parse_mode="Markdown"
            )
            await state.set_state(MainMenu.menu)
            return

        # Обновляем сообщение о статусе
        processing_message = (
            "✅ *Оплата успешно получена!*\n\n"
            "Заказываем eSIM у провайдера. Это может занять некоторое время..."
        ) if language_code == 'ru' else (
            "✅ *Payment successfully received!*\n\n"
            "Ordering eSIM from provider. This may take some time..."
        )

        await callback.message.edit_text(
            processing_message,
            parse_mode="Markdown"
        )

        # Заказываем eSIM через API провайдера
        logger.info(f"Ordering eSIM for order {order_id}, package code: {package.package_code}")

        # Обновляем статус заказа на PROCESSING
        order.status = OrderStatus.PROCESSING.value
        await session.commit()

        # Получаем пользователя для email (если есть)
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        email = user.email if user and user.email else "customer@example.com"  # Используем email пользователя, если он указан, иначе используем email по умолчанию

        # Создаем eSIM
        esim_result = await esim_service.create_esim(order_id, package.package_code, email)

        if esim_result.get('success'):
            # eSIM успешно создана
            logger.info(f"eSIM successfully created for order {order_id}")

            # Обновляем статус заказа в БД
            order.status = OrderStatus.COMPLETED.value

            # Сохраняем номер заказа у провайдера, если он есть
            if esim_result.get('order_no'):
                order.order_no = esim_result.get('order_no')

            # Создаем запись в таблице ESim
            from database.models import ESim

            # Проверяем, существует ли уже запись ESim для этого заказа
            esim_query = select(ESim).where(ESim.order_id == order_id)
            existing_esim_result = await session.execute(esim_query)
            existing_esim = existing_esim_result.scalars().first()

            if existing_esim:
                # Обновляем существующую запись
                existing_esim.iccid = esim_result.get('esim_iccid', '')
                existing_esim.activation_code = esim_result.get('activation_code', '')
                existing_esim.qr_code_url = esim_result.get('qr_code_url', '')
                existing_esim.esim_status = esim_result.get('esim_status', 'ACTIVATED')
                existing_esim.esim_tran_no = esim_result.get('order_no', '')
                existing_esim.imsi = esim_result.get('imsi', '')
                existing_esim.msisdn = esim_result.get('msisdn', '')
                existing_esim.active_type = esim_result.get('active_type', 0)
                existing_esim.expired_time = None  # Требуется конвертация строки в datetime
                existing_esim.total_volume = esim_result.get('total_volume', 0)
                existing_esim.total_duration = esim_result.get('total_duration', 0)
                existing_esim.duration_unit = esim_result.get('duration_unit', 'DAY')
                existing_esim.order_usage = esim_result.get('order_usage', 0)
                existing_esim.pin = esim_result.get('pin', '')
                existing_esim.puk = esim_result.get('puk', '')
                existing_esim.apn = esim_result.get('apn', '')
                existing_esim.raw_data = esim_result.get('api_response', {})
                existing_esim.updated_at = datetime.utcnow()
            else:
                # Создаем новую запись ESim
                new_esim = ESim(
                    order_id=order_id,
                    esim_tran_no=esim_result.get('order_no', ''),
                    iccid=esim_result.get('esim_iccid', ''),
                    imsi=esim_result.get('imsi', ''),
                    msisdn=esim_result.get('msisdn', ''),
                    activation_code=esim_result.get('activation_code', ''),
                    qr_code_url=esim_result.get('qr_code_url', ''),
                    esim_status=esim_result.get('esim_status', 'ACTIVATED'),
                    active_type=esim_result.get('active_type', 0),
                    # expired_time требует конвертации строки в datetime
                    total_volume=esim_result.get('total_volume', 0),
                    total_duration=esim_result.get('total_duration', 0),
                    duration_unit=esim_result.get('duration_unit', 'DAY'),
                    order_usage=esim_result.get('order_usage', 0),
                    pin=esim_result.get('pin', ''),
                    puk=esim_result.get('puk', ''),
                    apn=esim_result.get('apn', ''),
                    raw_data=esim_result.get('api_response', {}),
                    created_at=datetime.utcnow()
                )
                session.add(new_esim)

            # Сохраняем изменения в БД
            await session.commit()

            # Формируем сообщение с информацией о eSIM
            message_text = (
                "🎉 *Ваша eSIM готова!*\n\n"
                f"*ICCID:* `{esim_result.get('esim_iccid', 'Недоступно')}`\n"
            ) if language_code == 'ru' else (
                "🎉 *Your eSIM is ready!*\n\n"
                f"*ICCID:* `{esim_result.get('esim_iccid', 'Not available')}`\n"
            )

            # Добавляем информацию о пакете
            message_text += (
                f"*Страна:* {package.country.name}\n"
                f"*Пакет:* {package.data_amount} ГБ на {package.duration} дней\n\n"
            ) if language_code == 'ru' else (
                f"*Country:* {package.country.name}\n"
                f"*Package:* {package.data_amount} GB for {package.duration} days\n\n"
            )

            # Добавляем QR-код, если доступен
            if esim_result.get('qr_code_url'):
                message_text += (
                    "QR-код для активации отправлен отдельным сообщением.\n\n"
                ) if language_code == 'ru' else (
                    "QR code for activation has been sent in a separate message.\n\n"
                )

            # Добавляем код ручной активации, если доступен
            if esim_result.get('manual_activation_code'):
                message_text += (
                    f"*Код для ручной активации:* `{esim_result.get('manual_activation_code')}`\n\n"
                ) if language_code == 'ru' else (
                    f"*Manual activation code:* `{esim_result.get('manual_activation_code')}`\n\n"
                )

            # Добавляем APN, если доступен
            if esim_result.get('apn'):
                message_text += (
                    f"*APN:* `{esim_result.get('apn')}`\n\n"
                ) if language_code == 'ru' else (
                    f"*APN:* `{esim_result.get('apn')}`\n\n"
                )

            # Добавляем инструкции по активации
            message_text += (
                "*Инструкции по активации:*\n"
                "1. Откройте настройки вашего телефона\n"
                "2. Перейдите в раздел 'Сотовая связь' или 'SIM-карты'\n"
                "3. Выберите 'Добавить eSIM' или 'Добавить тарифный план'\n"
                "4. Отсканируйте QR-код или введите код активации вручную\n"
                "5. Следуйте инструкциям на экране\n\n"
                "Если у вас возникли проблемы с активацией, обратитесь в нашу службу поддержки."
            ) if language_code == 'ru' else (
                "*Activation instructions:*\n"
                "1. Open your phone settings\n"
                "2. Go to 'Cellular' or 'SIM cards' section\n"
                "3. Select 'Add eSIM' or 'Add cellular plan'\n"
                "4. Scan the QR code or enter the activation code manually\n"
                "5. Follow the on-screen instructions\n\n"
                "If you have any issues with activation, please contact our support team."
            )
        else:
            # Проблема с созданием eSIM
            error_message = esim_result.get('error', 'Unknown error')
            logger.error(f"Failed to create eSIM for order {order_id}: {error_message}")

            # Обновляем статус заказа в БД
            order.status = OrderStatus.FAILED.value
            await session.commit()

            message_text = (
                "✅ *Оплата успешно получена!*\n\n"
                "К сожалению, возникла проблема при активации eSIM. "
                f"Ошибка: {error_message}\n\n"
                "Наша служба поддержки свяжется с вами в ближайшее время."
            ) if language_code == 'ru' else (
                "✅ *Payment successfully received!*\n\n"
                "Unfortunately, there was an issue with activating your eSIM. "
                f"Error: {error_message}\n\n"
                "Our support team will contact you soon."
            )

        builder = InlineKeyboardBuilder()
        builder.button(
            text="👤 Личный кабинет" if language_code == 'ru' else "👤 My Account",
            callback_data="account"
        )
        builder.button(
            text="🏠 Главное меню" if language_code == 'ru' else "🏠 Main menu",
            callback_data="main_menu"
        )
        builder.adjust(1)

        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )

        # Если есть QR-код, отправляем его отдельным сообщением
        if esim_result.get('success') and esim_result.get('qr_code_url'):
            try:
                await callback.message.answer_photo(
                    photo=esim_result.get('qr_code_url'),
                    caption=(
                        "QR-код для активации вашей eSIM. Отсканируйте его в настройках телефона."
                    ) if language_code == 'ru' else (
                        "QR code for activating your eSIM. Scan it in your phone settings."
                    )
                )
            except Exception as e:
                logger.error(f"Error sending QR code: {e}")
                # Отправляем ссылку на QR-код, если не удалось отправить изображение
                await callback.message.answer(
                    (
                        "Ссылка на QR-код для активации вашей eSIM:\n"
                        f"{esim_result.get('qr_code_url')}"
                    ) if language_code == 'ru' else (
                        "Link to QR code for activating your eSIM:\n"
                        f"{esim_result.get('qr_code_url')}"
                    )
                )

        # Устанавливаем состояние главного меню
        await state.set_state(MainMenu.menu)
    else:
        # Если платеж не подтвержден
        message_text = (
            "❗ *Оплата не найдена*\n\n"
            "Мы не смогли найти вашу оплату. Возможно, требуется больше времени для обработки. "
            "Попробуйте проверить статус позже или свяжитесь с поддержкой."
        ) if language_code == 'ru' else (
            "❗ *Payment not found*\n\n"
            "We couldn't find your payment. It may take more time to process. "
            "Try checking the status later or contact support."
        )

        builder = InlineKeyboardBuilder()
        builder.button(
            text="🔄 Проверить снова" if language_code == 'ru' else "🔄 Check again",
            callback_data=f"check_payment:{order_id}"
        )
        builder.button(
            text="❓ Связаться с поддержкой" if language_code == 'ru' else "❓ Contact support",
            callback_data="support"
        )
        builder.button(
            text="❌ Отменить" if language_code == 'ru' else "❌ Cancel",
            callback_data="cancel_payment"
        )
        builder.adjust(1)

        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )

# Обработчик отмены платежа
@router.callback_query(F.data == "cancel_payment")
async def cancel_payment(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    # Получаем и сохраняем все данные состояния
    user_data = await state.get_data()
    order_id = user_data.get("order_id")
    language_code = user_data.get("language_code", "ru")
    country_code = user_data.get("country_code")
    selected_duration = user_data.get("selected_duration")
    package_id = user_data.get("package_id")

    # Обновляем статус заказа
    if order_id:
        order = await session.get(Order, order_id)
        if order:
            order.status = OrderStatus.CANCELED.value
            await session.commit()

    message_text = (
        "❌ Оплата отменена.\n\n"
        "Вы можете выбрать другой пакет или вернуться в главное меню."
    ) if language_code == 'ru' else (
        "❌ Payment canceled.\n\n"
        "You can choose another package or return to the main menu."
    )

    builder = InlineKeyboardBuilder()
    builder.button(
        text="🌎 Выбрать другой пакет" if language_code == 'ru' else "🌎 Choose another package",
        callback_data="back_to_packages_payment"
    )
    builder.button(
        text="🏠 Главное меню" if language_code == 'ru' else "🏠 Main menu",
        callback_data="main_menu"
    )
    builder.adjust(1)

    # Явно сохраняем все данные снова, чтобы быть уверенными что они будут доступны
    await state.update_data({
        "country_code": country_code,
        "selected_duration": selected_duration,
        "package_id": package_id,
        "language_code": language_code
    })

    # Устанавливаем состояние выбора пакета, чтобы обработчик back_to_packages работал правильно
    await state.set_state(BuyESim.select_package)

    await callback.message.edit_text(
        message_text,
        reply_markup=builder.as_markup()
    )