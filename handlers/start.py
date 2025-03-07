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
    
    # Отправляем сообщение с клавиатурой главного меню
    if user.language_code == 'ru':
        await callback.message.edit_text(
            "Главное меню:",
            reply_markup=get_main_menu_keyboard(user.language_code)
        )
    else:
        await callback.message.edit_text(
            "Main Menu:",
            reply_markup=get_main_menu_keyboard(user.language_code)
        )
    
    await callback.answer()


@router.callback_query(F.data == "buy_esim")
async def process_buy_esim_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик нажатия на кнопку 'Купить eSIM'"""
    # Устанавливаем состояние выбора страны
    await state.set_state(BuyESim.select_country)
    
    # Здесь будет переход к выбору страны
    # Реализация будет в отдельном файле handlers/buy_esim.py
    if callback.from_user.language_code == 'ru':
        await callback.message.edit_text(
            "Выберите страну для покупки eSIM:",
            reply_markup=None  # Здесь будет клавиатура со странами
        )
    else:
        await callback.message.edit_text(
            "Select a country for your eSIM:",
            reply_markup=None  # Здесь будет клавиатура со странами
        )
    
    await callback.answer()


@router.callback_query(F.data == "account")
async def process_account_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик нажатия на кнопку 'Личный кабинет'"""
    # Устанавливаем состояние личного кабинета
    await state.set_state(AccountMenu.menu)
    
    # Здесь будет переход в личный кабинет
    # Реализация будет в отдельном файле handlers/account.py
    if callback.from_user.language_code == 'ru':
        await callback.message.edit_text(
            "Личный кабинет:",
            reply_markup=None  # Здесь будет клавиатура личного кабинета
        )
    else:
        await callback.message.edit_text(
            "My Account:",
            reply_markup=None  # Здесь будет клавиатура личного кабинета
        )
    
    await callback.answer()


@router.callback_query(F.data == "support")
async def process_support_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик нажатия на кнопку 'Помощь'"""
    # Устанавливаем состояние помощи
    await state.set_state(SupportMenu.menu)
    
    # Здесь будет переход в раздел поддержки
    # Реализация будет в отдельном файле handlers/support.py
    if callback.from_user.language_code == 'ru':
        await callback.message.edit_text(
            "Раздел поддержки:",
            reply_markup=None  # Здесь будет клавиатура раздела поддержки
        )
    else:
        await callback.message.edit_text(
            "Support Section:",
            reply_markup=None  # Здесь будет клавиатура раздела поддержки
        )
    
    await callback.answer()


@router.callback_query(F.data == "about_tariffs")
async def process_about_tariffs_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик нажатия на кнопку 'О тарифах'"""
    # Здесь будет информация о тарифах
    if callback.from_user.language_code == 'ru':
        await callback.message.edit_text(
            "ℹ️ Информация о тарифах:\n\n"
            "Мы предлагаем eSIM для более чем 100 стран мира с различными тарифными планами.\n\n"
            "Наши преимущества:\n"
            "✅ Быстрая активация eSIM сразу после оплаты\n"
            "✅ Удобная оплата через Telegram Pay и криптовалюты\n"
            "✅ Круглосуточная поддержка на русском и английском языках\n"
            "✅ Высокая скорость мобильного интернета\n\n"
            "Выберите страну в разделе 'Купить eSIM' чтобы узнать подробнее о доступных тарифах.",
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 Вернуться в главное меню", callback_data="main_menu"
            ).as_markup()
        )
    else:
        await callback.message.edit_text(
            "ℹ️ Tariff Information:\n\n"
            "We offer eSIMs for more than 100 countries with various data plans.\n\n"
            "Our advantages:\n"
            "✅ Fast eSIM activation immediately after payment\n"
            "✅ Convenient payment via Telegram Pay and cryptocurrencies\n"
            "✅ 24/7 support in Russian and English\n"
            "✅ High-speed mobile internet\n\n"
            "Select a country in the 'Buy eSIM' section to learn more about available tariffs.",
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 Back to Main Menu", callback_data="main_menu"
            ).as_markup()
        )
    
    await callback.answer()