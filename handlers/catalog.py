from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import math

from sqlalchemy.ext.asyncio import AsyncSession

from database.queries import get_all_countries, get_packages_by_country, get_country_by_code, get_user_by_telegram_id
from utils.states import BuyESim, MainMenu, CallbackData

router = Router()

# Количество стран на одной странице пагинации
COUNTRIES_PER_PAGE = 30  # 3 кнопки в ряд * 10 рядов = 30 стран на странице


def get_countries_keyboard(countries: list, page: int = 0, language_code: str = 'ru') -> InlineKeyboardBuilder:
    """Создание клавиатуры для выбора страны"""
    builder = InlineKeyboardBuilder()
    
    # Общее количество страниц
    total_pages = math.ceil(len(countries) / COUNTRIES_PER_PAGE)
    
    # Вычисляем индексы для текущей страницы
    start_idx = page * COUNTRIES_PER_PAGE
    end_idx = min(start_idx + COUNTRIES_PER_PAGE, len(countries))
    
    # Добавляем кнопки стран для текущей страницы
    for country in countries[start_idx:end_idx]:
        flag = country.flag_emoji or '🌍'
        builder.button(
            text=f"{flag} {country.name}",
            callback_data=f"{CallbackData.COUNTRY.value}:{country.code}"
        )
    
    # Добавляем навигационные кнопки, если есть несколько страниц
    if total_pages > 1:
        # Кнопка назад
        if page > 0:
            prev_text = "⬅️ Назад" if language_code == 'ru' else "⬅️ Back"
            builder.button(
                text=prev_text,
                callback_data=f"{CallbackData.PAGE.value}:{page-1}"
            )
        
        # Номер страницы
        page_text = f"{page+1}/{total_pages}"
        builder.button(
            text=page_text,
            callback_data="page_info"
        )
        
        # Кнопка вперед
        if page < total_pages - 1:
            next_text = "Вперед ➡️" if language_code == 'ru' else "Next ➡️"
            builder.button(
                text=next_text,
                callback_data=f"{CallbackData.PAGE.value}:{page+1}"
            )
    
    # Кнопка возврата в главное меню
    back_text = "◀️ Назад в меню" if language_code == 'ru' else "◀️ Back to menu"
    builder.button(text=back_text, callback_data="main_menu")
    
    # Настраиваем сетку кнопок
    # Сначала определяем количество кнопок разных типов
    country_buttons_count = min(end_idx - start_idx, COUNTRIES_PER_PAGE)
    
    # Определяем количество навигационных кнопок
    nav_buttons_count = 0
    if total_pages > 1:
        if page > 0:  # Кнопка "Назад"
            nav_buttons_count += 1
        nav_buttons_count += 1  # Номер страницы
        if page < total_pages - 1:  # Кнопка "Вперед"
            nav_buttons_count += 1
    
    # Настраиваем расположение кнопок
    # Страны располагаем по 3 в ряд
    rows = [3] * (country_buttons_count // 3)
    if country_buttons_count % 3 > 0:
        rows.append(country_buttons_count % 3)
    
    # Добавляем строку для навигационных кнопок, если они есть
    if nav_buttons_count > 0:
        rows.append(nav_buttons_count)
    
    # Добавляем строку для кнопки возврата в главное меню
    rows.append(1)
    
    # Применяем настройку расположения
    builder.adjust(*rows)
    
    return builder


def get_packages_keyboard(packages: list, country_code: str, language_code: str = 'ru') -> InlineKeyboardBuilder:
    """Создание клавиатуры для выбора тарифного плана"""
    builder = InlineKeyboardBuilder()
    
    for package in packages:
        # Формируем информацию о пакете
        if language_code == 'ru':
            if package.data_amount.is_integer():
                data_text = f"{int(package.data_amount)} ГБ"
            else:
                data_text = f"{package.data_amount} ГБ"
                
            duration_text = f"{package.duration} дней"
            price_text = f"{package.price:.2f} USD"
            button_text = f"{data_text}, {duration_text} - {price_text}"
        else:  # Английский по умолчанию
            if package.data_amount.is_integer():
                data_text = f"{int(package.data_amount)} GB"
            else:
                data_text = f"{package.data_amount} GB"
                
            duration_text = f"{package.duration} days"
            price_text = f"${package.price:.2f}"
            button_text = f"{data_text}, {duration_text} - {price_text}"
        
        builder.button(
            text=button_text,
            callback_data=f"{CallbackData.PACKAGE.value}:{package.id}"
        )
    
    # Кнопка возврата к выбору страны
    back_text = "◀️ Назад к странам" if language_code == 'ru' else "◀️ Back to countries"
    builder.button(text=back_text, callback_data=f"{CallbackData.BACK.value}:countries")
    
    # Кнопка возврата в главное меню
    main_menu_text = "🏠 Главное меню" if language_code == 'ru' else "🏠 Main menu"
    builder.button(text=main_menu_text, callback_data="main_menu")
    
    # Настраиваем сетку кнопок: тарифы в одну колонку, кнопки навигации в одну строку
    builder.adjust(1, repeat=True)
    
    return builder


@router.callback_query(F.data == "buy_esim")
async def process_buy_esim_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик нажатия на кнопку 'Купить eSIM'"""
    # Получаем пользователя для определения языка
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    language_code = user.language_code if user else callback.from_user.language_code or 'ru'
    
    # Получаем все доступные страны
    countries = await get_all_countries(session)
    
    if not countries:
        # Если стран нет, сообщаем об этом
        if language_code == 'ru':
            await callback.message.edit_text(
                "В данный момент нет доступных стран для покупки eSIM. Пожалуйста, попробуйте позже.",
                reply_markup=None
            )
        else:
            await callback.message.edit_text(
                "There are no available countries for eSIM purchase at the moment. Please try again later.",
                reply_markup=None
            )
        await state.set_state(MainMenu.menu)
    else:
        # Устанавливаем состояние выбора страны
        await state.set_state(BuyESim.select_country)
        
        # Отображаем список стран с пагинацией
        keyboard = get_countries_keyboard(countries, page=0, language_code=language_code)
        
        if language_code == 'ru':
            await callback.message.edit_text(
                "Выберите страну для покупки eSIM:",
                reply_markup=keyboard.as_markup()
            )
        else:
            await callback.message.edit_text(
                "Select a country for your eSIM:",
                reply_markup=keyboard.as_markup()
            )
    
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackData.PAGE.value}:"))
async def process_page_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик нажатия на кнопки пагинации при выборе страны"""
    # Получаем номер страницы из callback_data
    page = int(callback.data.split(':')[1])
    
    # Получаем пользователя для определения языка
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    language_code = user.language_code if user else callback.from_user.language_code or 'ru'
    
    # Получаем все доступные страны
    countries = await get_all_countries(session)
    
    # Создаем клавиатуру для выбранной страницы
    keyboard = get_countries_keyboard(countries, page=page, language_code=language_code)
    
    # Обновляем сообщение с новой клавиатурой
    if language_code == 'ru':
        await callback.message.edit_text(
            "Выберите страну для покупки eSIM:",
            reply_markup=keyboard.as_markup()
        )
    else:
        await callback.message.edit_text(
            "Select a country for your eSIM:",
            reply_markup=keyboard.as_markup()
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackData.COUNTRY.value}:"))
async def process_country_selection(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик выбора страны"""
    # Получаем код страны из callback_data
    country_code = callback.data.split(':')[1]
    
    # Получаем пользователя для определения языка
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    language_code = user.language_code if user else callback.from_user.language_code or 'ru'
    
    # Получаем информацию о выбранной стране
    country = await get_country_by_code(session, country_code)
    
    if not country:
        # Если страна не найдена, возвращаемся к выбору страны
        await process_buy_esim_callback(callback, state, session)
        return
    
    # Сохраняем выбранную страну в данных состояния
    await state.update_data(selected_country_code=country_code)
    
    # Получаем доступные пакеты для выбранной страны
    packages = await get_packages_by_country(session, country.id)
    
    if not packages:
        # Если нет доступных пакетов для выбранной страны
        if language_code == 'ru':
            await callback.message.edit_text(
                f"В данный момент нет доступных тарифных планов для {country.name}. "
                f"Пожалуйста, выберите другую страну или попробуйте позже.",
                reply_markup=None
            )
        else:
            await callback.message.edit_text(
                f"There are no available data plans for {country.name} at the moment. "
                f"Please select another country or try again later.",
                reply_markup=None
            )
        
        # Возвращаемся к выбору страны
        await process_buy_esim_callback(callback, state, session)
    else:
        # Устанавливаем состояние выбора пакета
        await state.set_state(BuyESim.select_package)
        
        # Создаем клавиатуру с пакетами
        keyboard = get_packages_keyboard(packages, country_code, language_code=language_code)
        
        # Формируем сообщение с информацией о стране и доступных пакетах
        flag = country.flag_emoji or '🌍'
        
        if language_code == 'ru':
            header = f"{flag} **{country.name}** - Выберите тарифный план:"
            message = (
                f"{header}\n\n"
                f"Выберите подходящий тарифный план для вашей поездки в {country.name}. "
                f"Все пакеты включают высокоскоростной интернет с поддержкой 4G/LTE и 5G (где доступно)."
            )
        else:
            header = f"{flag} **{country.name}** - Select a data plan:"
            message = (
                f"{header}\n\n"
                f"Choose a suitable data plan for your trip to {country.name}. "
                f"All packages include high-speed internet with 4G/LTE and 5G support (where available)."
            )
        
        await callback.message.edit_text(
            message,
            reply_markup=keyboard.as_markup(),
            parse_mode="Markdown"
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackData.PACKAGE.value}:"))
async def process_package_selection(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик выбора тарифного плана"""
    # Получаем ID пакета из callback_data
    package_id = int(callback.data.split(':')[1])
    
    # Сохраняем выбранный пакет в данных состояния
    await state.update_data(selected_package_id=package_id)
    
    # Переходим к подтверждению покупки в payment.py
    await state.set_state(BuyESim.confirm_purchase)
    
    # Здесь будет переход к подтверждению покупки
    # Реализация будет в отдельном файле handlers/payment.py, но пока просто выведем сообщение
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    language_code = user.language_code if user else callback.from_user.language_code or 'ru'
    
    if language_code == 'ru':
        await callback.message.edit_text(
            "Переход к подтверждению покупки и выбору способа оплаты...",
            reply_markup=None
        )
    else:
        await callback.message.edit_text(
            "Proceeding to purchase confirmation and payment method selection...",
            reply_markup=None
        )
    
    await callback.answer()


@router.callback_query(F.data == f"{CallbackData.BACK.value}:countries")
async def process_back_to_countries(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик возврата к выбору страны"""
    await process_buy_esim_callback(callback, state, session)


@router.callback_query(F.data == "page_info")
async def process_page_info(callback: CallbackQuery):
    """Обработчик нажатия на информацию о странице (игнорируем, это просто информация)"""
    await callback.answer()