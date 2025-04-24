from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy.ext.asyncio import AsyncSession

from database.queries import get_or_create_user
from utils.states import MainMenu, BuyESim, AccountMenu, SupportMenu, CallbackData

router = Router()


def get_main_menu_keyboard(language_code: str = 'ru'):
    """Создание клавиатуры для главного меню"""
    builder = InlineKeyboardBuilder()
    
    if language_code == 'ru':
        builder.button(text="🌎 Купить eSIM", callback_data="buy_esim")
        builder.button(text="👤 Личный кабинет", callback_data="account")
        builder.button(text="❓ Помощь", callback_data="support")
        builder.button(text="ℹ️ О тарифах", callback_data="about_tariffs")
    else:  # Английский по умолчанию
        builder.button(text="🌎 Buy eSIM", callback_data="buy_esim")
        builder.button(text="👤 My Account", callback_data="account")
        builder.button(text="❓ Support", callback_data="support")
        builder.button(text="ℹ️ About Tariffs", callback_data="about_tariffs")
    
    builder.adjust(1)  # Размещаем кнопки в один столбец
    return builder.as_markup()


async def get_welcome_message(language_code: str = 'ru'):
    """Получение приветственного сообщения в зависимости от языка"""
    if language_code == 'ru':
        return (
            "👋 Добро пожаловать в бот по продаже eSIM!\n\n"
            "Этот бот поможет вам приобрести eSIM для путешествий по всему миру. "
            "Просто выберите нужную страну, тарифный план и способ оплаты.\n\n"
            "🔹 Что такое eSIM?\n"
            "eSIM (embedded SIM) - это цифровая SIM-карта, встроенная в ваше устройство. "
            "Она позволяет подключаться к сотовым сетям без необходимости использовать физическую SIM-карту.\n\n"
            "Выберите одну из опций ниже:"
        )
    else:  # Английский по умолчанию
        return (
            "👋 Welcome to the eSIM selling bot!\n\n"
            "This bot will help you purchase eSIMs for travel all around the world. "
            "Simply select the country, data plan, and payment method.\n\n"
            "🔹 What is an eSIM?\n"
            "eSIM (embedded SIM) is a digital SIM card built into your device. "
            "It allows you to connect to cellular networks without needing a physical SIM card.\n\n"
            "Please select one of the options below:"
        )


@router.message(CommandStart())
async def command_start(message: Message, state: FSMContext, session: AsyncSession):
    """Обработчик команды /start"""
    # Получаем или создаем пользователя
    user = await get_or_create_user(
        session, 
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name,
        message.from_user.language_code or 'ru'
    )
    
    # Сбрасываем предыдущее состояние, если есть
    await state.clear()
    
    # Устанавливаем состояние главного меню
    await state.set_state(MainMenu.menu)
    
    # Отправляем приветственное сообщение с клавиатурой
    welcome_message = await get_welcome_message(user.language_code)
    await message.answer(
        welcome_message,
        reply_markup=get_main_menu_keyboard(user.language_code)
    )


@router.message(Command("menu"))
async def command_menu(message: Message, state: FSMContext, session: AsyncSession):
    """Обработчик команды /menu для возврата в главное меню"""
    # Получаем пользователя
    user = await get_or_create_user(
        session, 
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name,
        message.from_user.language_code or 'ru'
    )
    
    # Сбрасываем предыдущее состояние, если есть
    await state.clear()
    
    # Устанавливаем состояние главного меню
    await state.set_state(MainMenu.menu)
    
    # Отправляем сообщение с клавиатурой главного меню
    if user.language_code == 'ru':
        await message.answer(
            "Главное меню:",
            reply_markup=get_main_menu_keyboard(user.language_code)
        )
    else:
        await message.answer(
            "Main Menu:",
            reply_markup=get_main_menu_keyboard(user.language_code)
        )


@router.callback_query(F.data == "main_menu")
async def process_main_menu_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик нажатия на кнопку возврата в главное меню"""
    # Получаем пользователя
    user = await get_or_create_user(
        session, 
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name,
        callback.from_user.last_name,
        callback.from_user.language_code or 'ru'
    )
    
    # Сбрасываем предыдущее состояние, если есть
    await state.clear()
    
    # Устанавливаем состояние главного меню
    await state.set_state(MainMenu.menu)
    
    # Получаем полное приветственное сообщение
    welcome_message = await get_welcome_message(user.language_code)
    
    # Отправляем полное приветственное сообщение с клавиатурой главного меню
    await callback.message.edit_text(
        welcome_message,
        reply_markup=get_main_menu_keyboard(user.language_code)
    )
    
    await callback.answer()


# Обработчик нажатия на кнопку 'Купить eSIM' перенесен в handlers/catalog.py


# @router.callback_query(F.data == "account")
# async def process_account_callback(callback: CallbackQuery, state: FSMContext):
#     """Обработчик нажатия на кнопку 'Личный кабинет'"""
#     # Устанавливаем состояние личного кабинета
#     await state.set_state(AccountMenu.menu)
#     
#     # Здесь будет переход в личный кабинет
#     # Реализация будет в отдельном файле handlers/account.py
#     if callback.from_user.language_code == 'ru':
#         await callback.message.edit_text(
#             "Личный кабинет:",
#             reply_markup=None  # Здесь будет клавиатура личного кабинета
#         )
#     else:
#         await callback.message.edit_text(
#             "My Account:",
#             reply_markup=None  # Здесь будет клавиатура личного кабинета
#         )
#     
#     await callback.answer()


@router.callback_query(F.data == "support")
async def process_support_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик нажатия на кнопку 'Помощь'"""
    # Устанавливаем состояние помощи
    await state.set_state(SupportMenu.menu)
    
    # Получаем язык пользователя
    user_data = await state.get_data()
    language_code = user_data.get("language_code", callback.from_user.language_code or "ru")
    
    # Создаем клавиатуру для раздела помощи
    builder = InlineKeyboardBuilder()
    
    if language_code == 'ru':
        # Добавляем кнопки для русскоязычных пользователей
        builder.button(text="📲 Как активировать eSIM", callback_data="help_activation")
        builder.button(text="⚙️ Процесс установки и активации", callback_data="help_payment")
        builder.button(text="❓ Часто задаваемые вопросы", callback_data="help_faq")
        builder.button(text="📞 Связаться с поддержкой", callback_data="help_contact")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        
        # Формируем текст помощи
        help_text = (
            "📚 *Раздел помощи*\n\n"
            "Здесь вы найдете ответы на часто задаваемые вопросы и инструкции по использованию eSIM.\n\n"
            "🔹 *Что такое eSIM?*\n"
            "eSIM (embedded SIM) - это цифровая SIM-карта, встроенная в ваше устройство. "
            "Она позволяет подключаться к сотовым сетям без необходимости использовать физическую SIM-карту.\n\n"
            "🔹 *Как проверить совместимость устройства?*\n"
            "Большинство современных смартфонов поддерживают eSIM. Проверьте в настройках вашего устройства "
            "наличие раздела 'Сотовая связь' или 'SIM-карты' с опцией добавления eSIM.\n\n"
            "🔹 *Как долго активна eSIM?*\n"
            "Срок действия eSIM зависит от выбранного тарифного плана. После активации eSIM будет работать "
            "в течение указанного периода или до исчерпания трафика.\n\n"
            "Выберите интересующий вас раздел:"
        )
    else:
        # Добавляем кнопки для англоязычных пользователей
        builder.button(text="📲 How to Activate eSIM", callback_data="help_activation")
        builder.button(text="⚙️ Installation and Activation Process", callback_data="help_payment")
        builder.button(text="❓ Frequently Asked Questions", callback_data="help_faq")
        builder.button(text="📞 Contact Support", callback_data="help_contact")
        builder.button(text="◀️ Back", callback_data="main_menu")
        
        # Формируем текст помощи
        help_text = (
            "📚 *Help Section*\n\n"
            "Here you'll find answers to frequently asked questions and instructions on using eSIM.\n\n"
            "🔹 *What is an eSIM?*\n"
            "eSIM (embedded SIM) is a digital SIM card built into your device. "
            "It allows you to connect to cellular networks without needing a physical SIM card.\n\n"
            "🔹 *How to check device compatibility?*\n"
            "Most modern smartphones support eSIM. Check your device settings "
            "for a 'Cellular' or 'SIM cards' section with an option to add an eSIM.\n\n"
            "🔹 *How long is the eSIM active?*\n"
            "The validity period of the eSIM depends on the selected data plan. After activation, the eSIM will work "
            "for the specified period or until the data is exhausted.\n\n"
            "Please select a section you're interested in:"
        )
    
    # Настраиваем расположение кнопок
    builder.adjust(1)  # Размещаем кнопки в один столбец
    
    # Отправляем сообщение с информацией и клавиатурой
    await callback.message.edit_text(
        help_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    
    await callback.answer()

# Обработчик для раздела "Как активировать eSIM"
@router.callback_query(F.data == "help_activation")
async def process_help_activation_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик для раздела активации eSIM"""
    # Получаем язык пользователя
    user_data = await state.get_data()
    language_code = user_data.get("language_code", callback.from_user.language_code or "ru")
    
    # Создаем клавиатуру для возврата
    builder = InlineKeyboardBuilder()
    
    if language_code == 'ru':
        builder.button(text="◀️ Назад к помощи", callback_data="support")
        
        activation_text = (
            "📲 *Инструкция по активации eSIM*\n\n"
            "*Шаг 1:* Убедитесь, что ваше устройство поддерживает eSIM и подключено к Wi-Fi или мобильной сети.\n\n"
            "*Шаг 2:* После покупки eSIM вы получите QR-код. Его можно найти в разделе 'Личный кабинет'.\n\n"
            "*Шаг 3:* Откройте настройки вашего устройства:\n"
            "• *iPhone:* Настройки → Сотовая связь → Добавить тарифный план\n"
            "• *Android:* Настройки → Сеть и Интернет → SIM-карты → Добавить eSIM\n\n"
            "*Шаг 4:* Отсканируйте QR-код с помощью камеры устройства.\n\n"
            "*Шаг 5:* Следуйте инструкциям на экране для завершения активации.\n\n"
            "*Шаг 6:* После активации включите 'Роуминг данных' в настройках устройства.\n\n"
            "*Важно:* Сохраните QR-код, он может понадобиться для повторной активации eSIM."
        )
    else:
        builder.button(text="◀️ Back to Help", callback_data="support")
        
        activation_text = (
            "📲 *eSIM Activation Instructions*\n\n"
            "*Step 1:* Make sure your device supports eSIM and is connected to Wi-Fi or mobile network.\n\n"
            "*Step 2:* After purchasing an eSIM, you will receive a QR code. You can find it in the 'My Account' section.\n\n"
            "*Step 3:* Open your device settings:\n"
            "• *iPhone:* Settings → Cellular → Add Cellular Plan\n"
            "• *Android:* Settings → Network & Internet → SIM cards → Add eSIM\n\n"
            "*Step 4:* Scan the QR code using your device's camera.\n\n"
            "*Step 5:* Follow the on-screen instructions to complete the activation.\n\n"
            "*Step 6:* After activation, enable 'Data Roaming' in your device settings.\n\n"
            "*Important:* Save the QR code, you may need it for eSIM reactivation."
        )
    
    # Настраиваем расположение кнопок
    builder.adjust(1)  # Размещаем кнопки в один столбец
    
    # Отправляем сообщение с информацией и клавиатурой
    await callback.message.edit_text(
        activation_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    
    await callback.answer()

# Обработчик для раздела "Процесс установки и активации"
@router.callback_query(F.data == "help_payment")
async def process_help_payment_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик для раздела о процессе установки и активации"""
    # Получаем язык пользователя
    user_data = await state.get_data()
    language_code = user_data.get("language_code", callback.from_user.language_code or "ru")
    
    # Создаем клавиатуру для возврата
    builder = InlineKeyboardBuilder()
    
    if language_code == 'ru':
        builder.button(text="◀️ Назад к помощи", callback_data="support")
        
        payment_text = (
            "� *Процесс установки и активации eSIM*\n\n"
            "Шаг 1: Выберите страну и тарифный план в разделе 'Купить eSIM'.\n\n"
            "Шаг 2: Проверьте детали заказа и нажмите 'Продолжить'.\n\n"
            "Шаг 3: Выберите способ оплаты - криптовалюта. Мы принимаем TON, BTC, ETH и USDT.\n\n"
            "Шаг 4: Вы будете перенаправлены в криптобот для оплаты. Следуйте инструкциям для завершения оплаты.\n\n"
            "Шаг 5: После успешной оплаты вы получите QR-код для активации eSIM.\n\n"
            "Шаг 6: Отсканируйте QR-код с помощью камеры устройства:\n"
            "• iPhone: Настройки → Сотовая связь → Добавить тарифный план\n"
            "• Android: Настройки → Сеть и Интернет → SIM-карты → Добавить eSIM\n\n"
            "Шаг 7: Следуйте инструкциям на экране для завершения активации eSIM.\n\n"
            "Шаг 8: После активации включите 'Роуминг данных' в настройках устройства.\n\n"
            "Важно: Сохраните QR-код, он может понадобиться для повторной активации eSIM."
        )
    else:
        builder.button(text="◀️ Back to Help", callback_data="support")
        
        payment_text = (
            "� *eSIM Installation and Activation Process*\n\n"
            "Step 1: Select a country and data plan in the 'Buy eSIM' section.\n\n"
            "Step 2: Review your order details and click 'Continue'.\n\n"
            "Step 3: Choose cryptocurrency as your payment method. We accept TON, BTC, ETH, and USDT.\n\n"
            "Step 4: You will be redirected to a crypto bot to complete the payment. Follow the instructions to complete the payment.\n\n"
            "Step 5: After successful payment, you will receive a QR code to activate your eSIM.\n\n"
            "Step 6: Scan the QR code using your device's camera:\n"
            "• iPhone: Settings → Cellular → Add Cellular Plan\n"
            "• Android: Settings → Network & Internet → SIM cards → Add eSIM\n\n"
            "Step 7: Follow the on-screen instructions to complete the eSIM activation.\n\n"
            "Step 8: After activation, enable 'Data Roaming' in your device settings.\n\n"
            "Important: Save your QR code as it may be needed for reinstallation of your eSIM."
        )
    
    # Настраиваем расположение кнопок
    builder.adjust(1)  # Размещаем кнопки в один столбец
    
    # Отправляем сообщение с информацией и клавиатурой
    await callback.message.edit_text(
        payment_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    
    await callback.answer()

# Обработчик для раздела "Часто задаваемые вопросы"
@router.callback_query(F.data == "help_faq")
async def process_help_faq_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик для раздела часто задаваемых вопросов"""
    # Получаем язык пользователя
    user_data = await state.get_data()
    language_code = user_data.get("language_code", callback.from_user.language_code or "ru")
    
    # Создаем клавиатуру для возврата
    builder = InlineKeyboardBuilder()
    
    if language_code == 'ru':
        builder.button(text="◀️ Назад к помощи", callback_data="support")
        
        faq_text = (
            "❓ *Часто задаваемые вопросы*\n\n"
            
            "*В: Что такое eSIM?*\n"
            "О: eSIM — это встроенная электронная SIM-карта в вашем телефоне. После загрузки и установки вы можете использовать её для подключения к интернету.\n\n"
            
            "*В: Как узнать, поддерживает ли мое устройство eSIM?*\n"
            "О: Большинство современных iPhone (XR, XS и новее), Google Pixel (3 и новее), Samsung Galaxy (S20 и новее) "
            "и многие другие устройства поддерживают eSIM. Проверьте в настройках вашего устройства или на сайте производителя.\n\n"
            
            "*В: Когда активируется мой тарифный план eSIM?*\n"
            "О: Он активируется, как только подключится к поддерживаемой сети. Мы рекомендуем установить его до отправления.\n\n"
            
            "*В: Что такое ежедневный план?*\n"
            "О: Например: если активирован в 9 утра, он будет действовать до 9 утра следующего дня. Если вы израсходуете дневной объем данных, скорость будет снижена до 128 кбит/с, так что не нужно беспокоиться о внезапном прекращении данных.\n\n"
            
            "*В: Мой eSIM включает номер телефона и SMS?*\n"
            "О: Мы предоставляем только услуги передачи данных, но вы можете использовать такие приложения, как Telegram, WhatsApp, для общения.\n\n"
            
            "*В: Могу ли я получать SMS с моей оригинальной SIM-карты?*\n"
            "О: Да, вы можете одновременно активировать eSIM и вашу оригинальную SIM-карту для получения SMS, например, уведомлений по кредитной карте, во время путешествий.\n\n"
            
            "*В: Когда я получу свой eSIM?*\n"
            "О: Вы получите доступ к своему eSIM сразу же после покупки в разделе 'Личный кабинет'.\n\n"
            
            "*В: Могу ли я продолжать использовать Telegram, WhatsApp?*\n"
            "О: Да, ваш номер Telegram, WhatsApp, контакты и чаты останутся без изменений.\n\n"
            
            "*В: Насколько быстрая сеть eSIM?*\n"
            "О: Скорость поддерживаемой сети можно увидеть в деталях продукта. Сила сети зависит от местного оператора.\n\n"
            
            "*В: Как включить роуминг данных для eSIM?*\n"
            "О: Перейдите в настройки устройства, откройте 'Сотовая связь' или 'Мобильные услуги' и включите 'Роуминг данных'.\n\n"
            
            "*В: Что делать, если установка не удалась?*\n"
            "О: Убедитесь, что eSIM уже не установлен на вашем устройстве, так как каждый eSIM может быть установлен только один раз. Если проблема сохраняется, свяжитесь со службой поддержки.\n\n"
            
            "*В: Что делать, если данные истекают или заканчиваются?*\n"
            "О: Вы можете пополнить баланс или приобрести новый план после его истечения.\n\n"
            
            "*В: Как выбрать подходящий тарифный план?*\n"
            "О: eSIM предлагает стандартные планы, такие как 1 ГБ/7 дней или (3 ГБ, 5 ГБ, 10 ГБ, 20 ГБ)/30 дней. Вы можете выбрать подходящий в зависимости от ваших потребностей и пополнить его в любое время.\n\n"
            
            "*В: Могу ли я продлить использование данных?*\n"
            "О: Да, вы можете приобрести новый план, который автоматически активируется после истечения текущего плана.\n\n"
            
            "*В: Могу ли я делиться данными с другими устройствами?*\n"
            "О: Да, вы можете делиться своей сетью с другими устройствами, и использование данных будет таким же, как на вашем телефоне.\n\n"
            
            "*В: Могу ли я установить eSIM заранее?*\n"
            "О: Да, мы рекомендуем установить и настроить его до отправления, чтобы вы могли сразу использовать его по прибытии.\n\n"
            
            "*В: Как проверить использование данных?*\n"
            "О: Вы можете проверить использование данных в разделе 'Личный кабинет' в нашем боте.\n\n"
            
            "*В: Могу ли я использовать eSIM на нескольких устройствах?*\n"
            "О: Нет, каждый eSIM может быть установлен только на одном устройстве. Свяжитесь со службой поддержки для переноса.\n\n"
            
            "*В: Могу ли я удалить eSIM после истечения данных?*\n"
            "О: Да, но вы также можете сохранить его для пополнения при будущих поездках в тот же регион.\n\n"
            
            "*В: Могу ли я использовать физическую SIM-карту и eSIM одновременно?*\n"
            "О: Да, но активируйте мобильные данные только на eSIM, чтобы избежать дополнительных расходов на роуминг с физической SIM-карты.\n\n"
            
            "*В: Как запросить возврат средств?*\n"
            "О: Если ваше устройство не совместимо, поездка отменена или возникли технические проблемы, вы можете запросить возврат. Средства будут возвращены на ваш исходный счёт в течение 5–7 рабочих дней.\n\n"
            
            "*В: Почему стоит выбрать eSIM?*\n"
            "О: Мы предоставляем гибкие тарифные планы, надежные скорости сети и отличную поддержку клиентов, что делает нас вашим надёжным спутником в путешествиях."
        )
    else:
        builder.button(text="◀️ Back to Help", callback_data="support")
        
        faq_text = (
            "❓ *Frequently Asked Questions*\n\n"
            
            "*Q: What is eSIM?*\n"
            "A: eSIM is an embedded electronic SIM card in your phone. After downloading and installing, you can use it to connect to the internet.\n\n"
            
            "*Q: How do I know if my device supports eSIM?*\n"
            "A: Most modern iPhones (XR, XS and newer), Google Pixel (3 and newer), Samsung Galaxy (S20 and newer) "
            "and many other devices support eSIM. Check your device settings or the manufacturer's website.\n\n"
            
            "*Q: When does my eSIM data plan activate?*\n"
            "A: It activates once connected to a supported network. We recommend setting it up before departing.\n\n"
            
            "*Q: What is a daily plan?*\n"
            "A: For example: if activated at 9 AM, it will be valid until 9 AM the next day. If you use up the daily data allowance, the speed will be reduced to 128 Kbps, so you don't have to worry about sudden data cutoffs.\n\n"
            
            "*Q: Does my eSIM include a phone number and SMS?*\n"
            "A: We provide data services only, but you can use apps like Telegram, WhatsApp for communication.\n\n"
            
            "*Q: Can I receive SMS from my original SIM card?*\n"
            "A: Yes, you can activate both eSIM and your original SIM card simultaneously to receive SMS, such as credit card notifications, while traveling.\n\n"
            
            "*Q: When will I receive my eSIM?*\n"
            "A: You can access your eSIM immediately after purchase in the 'My Account' section.\n\n"
            
            "*Q: Can I continue using Telegram, WhatsApp?*\n"
            "A: Yes, your Telegram, WhatsApp number, contacts, and chats will remain unchanged.\n\n"
            
            "*Q: How fast is the eSIM network?*\n"
            "A: The speed of the supported network can be seen in the product details. Network strength depends on the local operator.\n\n"
            
            "*Q: How do I enable data roaming for eSIM?*\n"
            "A: Go to your device settings, open 'Cellular' or 'Mobile Services', and enable 'Data Roaming'.\n\n"
            
            "*Q: What if installation fails?*\n"
            "A: Make sure the eSIM is not already installed on your device, as each eSIM can only be installed once. If the problem persists, contact support.\n\n"
            
            "*Q: What if my data expires or runs out?*\n"
            "A: You can top up your balance or purchase a new plan after it expires.\n\n"
            
            "*Q: How do I choose the right data plan?*\n"
            "A: eSIM offers standard plans such as 1GB/7 days or (3GB, 5GB, 10GB, 20GB)/30 days. You can choose the appropriate one based on your needs and top it up at any time.\n\n"
            
            "*Q: Can I extend my data usage?*\n"
            "A: Yes, you can purchase a new plan that will automatically activate after your current plan expires.\n\n"
            
            "*Q: Can I share data with other devices?*\n"
            "A: Yes, you can share your network with other devices, and data usage will be the same as on your phone.\n\n"
            
            "*Q: Can I install the eSIM in advance?*\n"
            "A: Yes, we recommend installing and setting it up before departure so you can use it immediately upon arrival.\n\n"
            
            "*Q: How do I check data usage?*\n"
            "A: You can check data usage in the 'My Account' section of our bot.\n\n"
            
            "*Q: Can I use eSIM on multiple devices?*\n"
            "A: No, each eSIM can only be installed on one device. Contact support for transfer options.\n\n"
            
            "*Q: Can I delete the eSIM after the data expires?*\n"
            "A: Yes, but you can also keep it for topping up during future trips to the same region.\n\n"
            
            "*Q: Can I use a physical SIM card and eSIM simultaneously?*\n"
            "A: Yes, but activate mobile data only on the eSIM to avoid additional roaming costs from your physical SIM card.\n\n"
            
            "*Q: How do I request a refund?*\n"
            "A: If your device is incompatible, your trip is canceled, or you experience technical issues, you can request a refund. Funds will be returned to your original account within 5-7 business days.\n\n"
            
            "*Q: Why choose eSIM?*\n"
            "A: We offer flexible data plans, reliable network speeds, and excellent customer support, making us your reliable travel companion."
        )
    
    # Настраиваем расположение кнопок
    builder.adjust(1)
    
    # Отправляем сообщение с информацией и клавиатурой
    await callback.message.edit_text(
        faq_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    
    await callback.answer()

# Обработчик для раздела "Связаться с поддержкой"
@router.callback_query(F.data == "help_contact")
async def process_help_contact_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик для раздела контактов поддержки"""
    # Получаем язык пользователя
    user_data = await state.get_data()
    language_code = user_data.get("language_code", callback.from_user.language_code or "ru")
    
    # Создаем клавиатуру для возврата
    builder = InlineKeyboardBuilder()
    
    if language_code == 'ru':
        builder.button(text="◀️ Назад к помощи", callback_data="support")
        builder.button(text="📧 Написать в поддержку", url="https://t.me/support_esim_bot")
        
        contact_text = (
            "📞 *Связаться с поддержкой*\n\n"
            "Если у вас возникли вопросы или проблемы с использованием eSIM, наша команда поддержки готова помочь.\n\n"
            "*Способы связи:*\n"
            "• Telegram: @support_esim_bot\n"
            "• Email: support@esim-service.com\n"
            "*Время работы поддержки:*\n"
            "ПН-Вс: 10:00 - 18:00 (МСК)\n\n"
            "Мы стараемся отвечать на все запросы в течение 24 часов."
        )
    else:
        builder.button(text="◀️ Back to Help", callback_data="support")
        builder.button(text="📧 Contact Support", url="https://t.me/support_esim_bot")
        
        contact_text = (
            "📞 *Contact Support*\n\n"
            "If you have any questions or issues with using your eSIM, our support team is ready to help.\n\n"
            "*Contact Methods:*\n"
            "• Telegram: @support_esim_bot\n"
            "• Email: support@esim-service.com\n"
            "*Support Hours:*\n"
            "Mon-Sun: 10:00 AM - 6:00 PM (MSK)\n\n"
            "We aim to respond to all inquiries within 24 hours."
        )
    
    # Настраиваем расположение кнопок
    builder.adjust(2)  # Размещаем кнопки в один столбец
    
    # Отправляем сообщение с информацией и клавиатурой
    await callback.message.edit_text(
        contact_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    
    await callback.answer()


@router.callback_query(F.data == "about_tariffs")
async def process_about_tariffs_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик нажатия на кнопку 'О тарифах'"""
    if callback.from_user.language_code == 'ru':
        await callback.message.edit_text(
            "ℹ️ *Революция в мире связи: наши eSIM тарифы*\n\n"
            "Мы разрушаем стереотипы о высоких ценах на роуминг! Наши тарифы начинаются от *$0,2* за eSIM пакеты.\n\n"
            
            "🔸 *Для экономных путешественников*\n"
            "От $0,2 за минимальные пакеты данных\n"
            "Идеально для обмена сообщениями и навигации\n\n"
            
            "🔸 *Для активных исследователей*\n"
            "От $0,5 за пакеты на неделю\n"
            "Достаточно для фото и видео в социальных сетях\n\n"
            
            "🔸 *Для цифровых кочевников*\n"
            "От $3,5 за месячные пакеты\n"
            "Комфортный объем для работы и развлечений\n\n"
            
            "✨ *Наши преимущества*:\n"
            "• Мгновенная активация после оплаты\n"
            "• Действительно доступные цены от $0,2\n"
            "• Более 100 стран без роуминга\n"
            "• Удобная оплата криптовалютой\n"
            "• Персональная поддержка 24/7\n\n"
            
            "💡 *Популярные решения*:\n"
            "• Европа: от $0,5 за день интернета\n"
            "• Азия: от $0,2 за компактные пакеты\n"
            "• Америка: от $0,7 за стабильное соединение\n\n"
            
            "Выберите страну в разделе 'Купить eSIM' и откройте мир без границ и переплат!",
            reply_markup=InlineKeyboardBuilder().button(
                text="◀️ Вернуться в главное меню", callback_data="main_menu"
            ).as_markup(),
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text(
            "ℹ️ *The Connectivity Revolution: Our eSIM Plans*\n\n"
            "We're breaking the stereotypes about expensive roaming! Our tariffs start from just *$0.2* for eSIM packages.\n\n"
            
            "🔸 *For Budget Travelers*\n"
            "From $0.2 for minimal data packages\n"
            "Perfect for messaging and navigation\n\n"
            
            "🔸 *For Active Explorers*\n"
            "From $0,5 for weekly packages\n"
            "Enough for photos and videos on social media\n\n"
            
            "🔸 *For Digital Nomads*\n"
            "From $3,5 for monthly packages\n"
            "Comfortable volume for work and entertainment\n\n"
            
            "✨ *Our Advantages*:\n"
            "• Instant activation after payment\n"
            "• Truly affordable prices from $0.2\n"
            "• Over 100 countries without roaming\n"
            "• Convenient cryptocurrency payment\n"
            "• Personal support 24/7\n\n"
            
            "💡 *Popular Solutions*:\n"
            "• Europe: from $0.5 per day of internet\n"
            "• Asia: from $0.2 for compact packages\n"
            "• Americas: from $0.7 for stable connection\n\n"
            
            "Select a country in the 'Buy eSIM' section and discover a world without borders or overcharges!",
            reply_markup=InlineKeyboardBuilder().button(
                text="◀️ Back to Main Menu", callback_data="main_menu"
            ).as_markup(),
            parse_mode="Markdown"
        )
    
    await callback.answer()