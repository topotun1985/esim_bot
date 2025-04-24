from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import math

from sqlalchemy.ext.asyncio import AsyncSession

from database.queries import get_all_countries, get_packages_by_country, get_country_by_code, get_user_by_telegram_id, get_package_by_id
from utils.states import BuyESim, MainMenu, CallbackData

router = Router()

# Количество стран на одной странице пагинации
COUNTRIES_PER_PAGE = 30  # 3 кнопки в ряд * 10 рядов = 30 стран на странице

POPULAR_COUNTRY_CODES = ["TH", "VN", "ID", "EG", "ES", "GR", "CY", "TR", "MY", "PH", 
                        "LK", "MX", "BR", "US", "CR", "DO", "SC", "MU", "ZA", "IT", 
                        "HR", "PT", "AE", "OM", "TN", "MA", "JM", "AU", "IN", "FR"] 


def get_countries_keyboard(countries: list, page: int = 0, language_code: str = 'ru') -> InlineKeyboardBuilder:
    """Создание клавиатуры для выбора страны"""
    builder = InlineKeyboardBuilder()
    
    # Общее количество страниц
    total_pages = math.ceil(len(countries) / COUNTRIES_PER_PAGE)

    # Создаем функцию для получения названия страны с учетом языка
    def get_country_name(country):
        return country.name_ru if language_code == 'ru' and hasattr(country, 'name_ru') and country.name_ru else country.name

    # Разделяем на популярные и остальные страны
    popular = [c for c in countries if c.code in POPULAR_COUNTRY_CODES]
    others = [c for c in countries if c.code not in POPULAR_COUNTRY_CODES]
    
    # Сортируем обе группы по алфавиту в зависимости от языка
    popular.sort(key=lambda c: get_country_name(c))
    others.sort(key=lambda c: get_country_name(c))
    
    # Объединяем списки - сначала популярные, затем остальные
    countries = popular + others
    
    # Вычисляем индексы для текущей страницы
    start_idx = page * COUNTRIES_PER_PAGE
    end_idx = min(start_idx + COUNTRIES_PER_PAGE, len(countries))
    
    # Добавляем кнопки стран для текущей страницы
    for country in countries[start_idx:end_idx]:
        flag = country.flag_emoji or '🌍'
        # Используем русское название страны для русскоязычных пользователей
        country_name = get_country_name(country)
        builder.button(
            text=f"{flag} {country_name}",
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


def get_durations_keyboard(packages: list, country_code: str, language_code: str = 'ru') -> InlineKeyboardBuilder:
    """Создание клавиатуры для выбора длительности пакета"""
    builder = InlineKeyboardBuilder()
    
    # Группируем пакеты по длительности
    durations = set()
    for package in packages:
        durations.add(package.duration)
    
    # Сортируем длительности по возрастанию
    durations = sorted(durations)
    
    # Добавляем кнопки для каждой длительности
    for duration in durations:
        if language_code == 'ru':
            button_text = f"📅 {duration} дней"
        else:
            button_text = f"📅 {duration} days"
        
        builder.button(
            text=button_text,
            callback_data=f"{CallbackData.DURATION.value}:{country_code}:{duration}"
        )
    
    # Кнопка возврата к выбору страны
    back_text = "◀️ Назад к странам" if language_code == 'ru' else "◀️ Back to countries"
    builder.button(text=back_text, callback_data=f"{CallbackData.BACK.value}:countries")
    
    # Кнопка возврата в главное меню
    main_menu_text = "🏠 Главное меню" if language_code == 'ru' else "🏠 Main menu"
    builder.button(text=main_menu_text, callback_data="main_menu")
    
    # Настраиваем сетку кнопок: длительности по две в ряд, кнопки навигации в одну строку
    builder.adjust(2, 2)
    
    return builder


def get_packages_by_duration_keyboard(packages: list, country_code: str, duration: int, language_code: str = 'ru') -> InlineKeyboardBuilder:
    """Создание клавиатуры для выбора пакета с определенной длительностью"""
    builder = InlineKeyboardBuilder()
    
    # Фильтруем пакеты по длительности
    filtered_packages = [p for p in packages if p.duration == duration]
    
    # Сортируем пакеты по объему данных
    sorted_packages = sorted(filtered_packages, key=lambda p: p.data_amount)
    
    # Добавляем кнопки для каждого пакета
    for package in sorted_packages:
        # Формируем информацию о пакете
        if language_code == 'ru':
            if package.data_amount.is_integer():
                data_text = f"{int(package.data_amount)} ГБ"
            else:
                data_text = f"{package.data_amount} ГБ"
                
            price_text = f"{package.price:.2f} USD"
            button_text = f"{data_text} - {price_text}"
        else:  # Английский по умолчанию
            if package.data_amount.is_integer():
                data_text = f"{int(package.data_amount)} GB"
            else:
                data_text = f"{package.data_amount} GB"
                
            price_text = f"${package.price:.2f}"
            button_text = f"{data_text} - {price_text}"
        
        builder.button(
            text=button_text,
            callback_data=f"{CallbackData.PACKAGE.value}:{package.id}"
        )
    
    # Кнопка возврата к выбору длительности
    back_text = "◀️ Назад к выбору длительности" if language_code == 'ru' else "◀️ Back to duration selection"
    builder.button(text=back_text, callback_data=f"{CallbackData.BACK.value}:durations:{country_code}")
    
    # Кнопка возврата в главное меню
    main_menu_text = "🏠 Главное меню" if language_code == 'ru' else "🏠 Main menu"
    builder.button(text=main_menu_text, callback_data="main_menu")
    
    # Настраиваем сетку кнопок: пакеты по две в ряд, кнопки навигации в одну строку
    builder.adjust(2, 2)
    
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
    # Извлекаем код страны из callback_data
    country_code = callback.data.split(":")[1]
    
    # Получаем информацию о пользователе для определения языка
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    language_code = user.language_code if user else callback.from_user.language_code or 'ru'
    
    # Получаем информацию о выбранной стране
    country = await get_country_by_code(session, country_code)
    
    if not country:
        # Если страна не найдена, выводим сообщение об ошибке
        if language_code == 'ru':
            await callback.message.edit_text(
                "Выбранная страна не найдена. Пожалуйста, выберите другую страну.",
                reply_markup=InlineKeyboardBuilder().button(
                    text="◀️ Назад в меню",
                    callback_data="main_menu"
                ).as_markup()
            )
        else:
            await callback.message.edit_text(
                "Selected country not found. Please choose another country.",
                reply_markup=InlineKeyboardBuilder().button(
                    text="◀️ Back to menu",
                    callback_data="main_menu"
                ).as_markup()
            )
        await callback.answer()
        return
    
    # Сохраняем выбранную страну в данных состояния
    await state.update_data(selected_country_code=country_code)
    
    # Получаем доступные пакеты для выбранной страны
    packages = await get_packages_by_country(session, country.id)
    
    if not packages:
        # Если нет доступных пакетов для выбранной страны
        flag = country.flag_emoji or '🌍'
        # Используем локализованное название страны
        country_name = country.name_ru if language_code == 'ru' and hasattr(country, 'name_ru') and country.name_ru else country.name
        
        if language_code == 'ru':
            no_packages_message = (
                f"{flag} **{country_name}**\n\n"
                f"К сожалению, в данный момент нет доступных пакетов для {country_name}.\n"
                f"Пожалуйста, выберите другую страну или попробуйте позже."
            )
        else:
            no_packages_message = (
                f"{flag} **{country_name}**\n\n"
                f"Unfortunately, there are no available packages for {country_name} at the moment.\n"
                f"Please choose another country or try again later."
            )
        
        # Создаем клавиатуру с кнопкой возврата к выбору страны
        keyboard = InlineKeyboardBuilder()
        back_text = "◀️ Выбрать другую страну" if language_code == 'ru' else "◀️ Choose another country"
        keyboard.button(text=back_text, callback_data="buy_esim")
        
        # Добавляем кнопку возврата в главное меню
        menu_text = "◀️ Назад в меню" if language_code == 'ru' else "◀️ Back to menu"
        keyboard.button(text=menu_text, callback_data="main_menu")
        
        # Настраиваем сетку кнопок - по одной кнопке в ряд
        keyboard.adjust(1)
        
        await callback.message.edit_text(
            no_packages_message,
            reply_markup=keyboard.as_markup(),
            parse_mode="Markdown"
        )
        await callback.answer()
        return
    
    # Устанавливаем состояние выбора длительности пакета
    await state.set_state(BuyESim.select_duration)
    
    # Создаем клавиатуру с длительностями пакетов
    keyboard = get_durations_keyboard(packages, country_code, language_code=language_code)
    
    # Формируем сообщение с информацией о стране
    flag = country.flag_emoji or '🌍'
    # Используем локализованное название страны
    country_name = country.name_ru if language_code == 'ru' and hasattr(country, 'name_ru') and country.name_ru else country.name
    
    if language_code == 'ru':
        header = f"{flag} **{country_name}** - Выберите длительность пакета:"
        message = (
            f"{header}\n\n"
            f"Выберите длительность интернет-пакета для вашей поездки в {country_name}. "
            f"Все пакеты включают высокоскоростной интернет с поддержкой 4G/LTE и 5G (где доступно)."
        )
    else:
        header = f"{flag} **{country_name}** - Select package duration:"
        message = (
            f"{header}\n\n"
            f"Choose the duration of your internet package for your trip to {country_name}. "
            f"All packages include high-speed internet with 4G/LTE and 5G support (where available)."
        )
    
    await callback.message.edit_text(
        message,
        reply_markup=keyboard.as_markup(),
        parse_mode="Markdown"
    )
    
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackData.DURATION.value}:"))
async def process_duration_selection(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик выбора длительности пакета"""
    # Получаем код страны и длительность из callback_data
    parts = callback.data.split(':')
    country_code = parts[1]
    duration = int(parts[2])
    
    # Получаем пользователя для определения языка
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    language_code = user.language_code if user else callback.from_user.language_code or 'ru'
    
    # Получаем информацию о выбранной стране
    country = await get_country_by_code(session, country_code)
    
    if not country:
        # Если страна не найдена, возвращаемся к выбору страны
        await process_buy_esim_callback(callback, state, session)
        return
    
    # Сохраняем выбранную длительность в данных состояния
    await state.update_data(selected_duration=duration)
    
    # Получаем доступные пакеты для выбранной страны
    packages = await get_packages_by_country(session, country.id)
    
    # Фильтруем пакеты по выбранной длительности
    filtered_packages = [p for p in packages if p.duration == duration]
    
    if not filtered_packages:
        # Если нет доступных пакетов для выбранной длительности
        if language_code == 'ru':
            await callback.message.edit_text(
                f"В данный момент нет доступных тарифных планов на {duration} дней для {country.name}. "
                f"Пожалуйста, выберите другую длительность или страну.",
                reply_markup=None
            )
        else:
            await callback.message.edit_text(
                f"There are no available data plans for {duration} days in {country.name} at the moment. "
                f"Please select another duration or country.",
                reply_markup=None
            )
        
        # Возвращаемся к выбору длительности
        await process_country_selection(callback, state, session)
    else:
        # Устанавливаем состояние выбора пакета
        await state.set_state(BuyESim.select_package)
        
        # Создаем клавиатуру с пакетами для выбранной длительности
        keyboard = get_packages_by_duration_keyboard(packages, country_code, duration, language_code=language_code)
        
        # Формируем сообщение с информацией о стране, длительности и доступных пакетах
        flag = country.flag_emoji or '🌍'
        
        if language_code == 'ru':
            header = f"{flag} **{country.name}** - Пакеты на {duration} дней:"
            message = (
                f"{header}\n\n"
                f"Выберите объем интернет-трафика для вашего пакета на {duration} дней в {country.name}. "
                f"Все пакеты включают высокоскоростной интернет с поддержкой 4G/LTE и 5G (где доступно)."
            )
        else:
            header = f"{flag} **{country.name}** - {duration} days packages:"
            message = (
                f"{header}\n\n"
                f"Choose the amount of internet data for your {duration}-day package in {country.name}. "
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
    
    # Получаем информацию о пользователе для определения языка
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    language_code = user.language_code if user else callback.from_user.language_code or 'ru'
    
    # Получаем информацию о пакете и связанной стране
    package = await get_package_by_id(session, package_id)
    
    if not package:
        await callback.message.edit_text(
            "Пакет не найден. Пожалуйста, выберите другой пакет." if language_code == 'ru' else 
            "Package not found. Please select another package.",
            reply_markup=get_countries_keyboard(await get_all_countries(session), 0, language_code)
        )
        await state.set_state(BuyESim.select_country)
        return
        
    # Получаем всю необходимую информацию заранее
    country_name = package.country.name if package.country else "Неизвестная страна" if language_code == 'ru' else "Unknown country"
    package_name = package.name
    data_amount = package.data_amount
    duration = package.duration
    price = package.price
    
    # Сохраняем выбранный пакет в данных состояния
    await state.update_data(package_id=package_id, language_code=language_code)
    
    # Переходим к выбору способа оплаты
    await state.set_state(BuyESim.select_payment)
    
    # Формируем сообщение с информацией о выбранном пакете
    message_text = (
        f"📦 *Выбранный пакет:*\n"
        f"🌍 Страна: {country_name}\n"
        f"📱 Пакет: {package_name}\n"
        f"📊 Данные: {data_amount} ГБ\n"
        f"⏱ Срок действия: {duration} дней\n"
        f"💰 Стоимость: ${price:.2f}\n\n"
        f"Выберите способ оплаты:"
    ) if language_code == 'ru' else (
        f"📦 *Selected package:*\n"
        f"🌍 Country: {country_name}\n"
        f"📱 Package: {package_name}\n"
        f"📊 Data: {data_amount} GB\n"
        f"⏱ Duration: {duration} days\n"
        f"💰 Price: ${price:.2f}\n\n"
        f"Choose payment method:"
    )
    
    # Создаем клавиатуру для выбора способа оплаты
    builder = InlineKeyboardBuilder()
    
    if language_code == 'ru':
        builder.button(text="💳 Оплатить (CryptoBot)", callback_data="payment:ton")
        builder.button(text="↩️ Вернуться к выбору пакета", callback_data="back_to_packages")
        builder.button(text="🏠 Главное меню", callback_data="main_menu")
    else:
        builder.button(text="💳 Pay with Crypto (CryptoBot)", callback_data="payment:ton")
        builder.button(text="↩️ Back to package selection", callback_data="back_to_packages")
        builder.button(text="🏠 Main menu", callback_data="main_menu")
    
    builder.adjust(1)
    
    await callback.message.edit_text(
        message_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    
    await callback.answer()


@router.callback_query(F.data == f"{CallbackData.BACK.value}:countries")
async def process_back_to_countries(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик возврата к выбору страны"""
    await process_buy_esim_callback(callback, state, session)


# Добавляем детальное логирование для отладки
import logging
logger = logging.getLogger(__name__)

@router.callback_query(F.data.in_({"back_to_packages", "back_to_packages_payment"}))
async def process_back_to_packages(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик возврата к выбору пакета"""
    logger.info("\n\n==== Вызов process_back_to_packages =====")
    logger.info(f"callback.data: {callback.data}")
    
    # Получаем данные из состояния
    user_data = await state.get_data()
    logger.info(f"user_data: {user_data}")
    
    # Проверяем оба возможных ключа для кода страны
    country_code = user_data.get("country_code")
    if not country_code:  # Если country_code не найден, используем selected_country_code
        country_code = user_data.get("selected_country_code")
        # Если нашли код страны в selected_country_code, сохраняем его в country_code для совместимости
        if country_code:
            await state.update_data({"country_code": country_code})
            logger.info(f"Найден код страны в selected_country_code: {country_code}")
    
    language_code = user_data.get("language_code", "ru")
    selected_duration = user_data.get("selected_duration")  # Добавить эту строку
    
    logger.info(f"country_code: {country_code}, language_code: {language_code}, selected_duration: {selected_duration} (тип: {type(selected_duration)})")
    
    if not country_code:
        # Если нет сохраненного кода страны, возвращаемся к списку стран
        await process_buy_esim_callback(callback, state, session)
        return
    
    # Получаем страну и ее пакеты
    country = await get_country_by_code(session, country_code)
    packages = await get_packages_by_country(session, country.id) if country else []
    
    if not country or not packages:
        await callback.message.edit_text(
            "Страна не найдена или для нее нет доступных пакетов." if language_code == 'ru' else
            "Country not found or no packages available for it.",
            reply_markup=get_countries_keyboard(await get_all_countries(session), 0, language_code)
        )
        await state.set_state(BuyESim.select_country)
        return
    
    # Проверяем, есть ли выбранная длительность
    if selected_duration:
        # Преобразуем selected_duration в int, т.к. он может быть строкой
        try:
            selected_duration = int(selected_duration)
            # Фильтруем пакеты по выбранной длительности
            filtered_packages = [p for p in packages if p.duration == selected_duration]
        except (ValueError, TypeError):
            filtered_packages = []
        
        logger.info(f"filtered_packages: {filtered_packages}")
        if filtered_packages:
            logger.info("filtered_packages не пустой, показываем пакеты")
            # Устанавливаем состояние выбора пакета
            await state.set_state(BuyESim.select_package)
            
            # Создаем клавиатуру с пакетами для выбранной длительности
            keyboard = get_packages_by_duration_keyboard(packages, country_code, selected_duration, language_code)
            
            # Формируем сообщение с информацией о стране, длительности и доступных пакетах
            flag = country.flag_emoji or '🌍'
            
            if language_code == 'ru':
                header = f"{flag} **{country.name}** - Пакеты на {selected_duration} дней:"
                message = (
                    f"{header}\n\n"
                    f"Выберите объем интернет-трафика для вашего пакета на {selected_duration} дней в {country.name}. "
                    f"Все пакеты включают высокоскоростной интернет с поддержкой 4G/LTE и 5G (где доступно)."
                )
            else:
                header = f"{flag} **{country.name}** - {selected_duration} days packages:"
                message = (
                    f"{header}\n\n"
                    f"Choose the amount of internet data for your {selected_duration}-day package in {country.name}. "
                    f"All packages include high-speed internet with 4G/LTE and 5G support (where available)."
                )
            
            # Исправляем ошибку: нужно вызвать as_markup() для получения InlineKeyboardMarkup
            logger.info("Converting keyboard to markup with as_markup()")
            await callback.message.edit_text(
                message,
                reply_markup=keyboard.as_markup(),
                parse_mode="Markdown"
            )
            return
    
    # Если нет выбранной длительности или нет пакетов для нее, показываем выбор длительности
    logger.info(f"selected_duration отсутствует или filtered_packages пуст, показываем выбор длительности")
    # Достаем уникальные длительности пакетов
    durations = set(package.duration for package in packages)
    durations = sorted(durations)
    logger.info(f"durations: {durations}")
    
    # Создаем клавиатуру с длительностями
    keyboard = get_durations_keyboard(packages, country_code, language_code)
    
    # Формируем сообщение
    message_text = (
        f"🌍 *Выбранная страна: {country.name}*\n\n" 
        f"Выберите длительность пакета:"
    ) if language_code == 'ru' else (
        f"🌍 *Selected country: {country.name}*\n\n"
        f"Choose package duration:"
    )
    
    logger.info(f"Showing duration selection with message: {message_text[:30]}...")
    
    # Важно: Сначала устанавливаем состояние, затем отправляем сообщение
    await state.set_state(BuyESim.select_duration)
    logger.info("State set to BuyESim.select_duration")
    
    # Исправляем с помощью as_markup() также и для этой клавиатуры
    logger.info("Converting duration keyboard to markup with as_markup()")
    await callback.message.edit_text(
        message_text,
        reply_markup=keyboard.as_markup(),
        parse_mode="Markdown"
    )
    logger.info("Message sent with durations keyboard")


@router.callback_query(F.data.startswith(f"{CallbackData.BACK.value}:durations:"))
async def process_back_to_durations(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработчик возврата к выбору длительности пакета"""
    # Получаем код страны из callback_data
    country_code = callback.data.split(':')[2]
    
    # Вместо изменения callback.data, создаем новый callback с нужным country_code
    # и напрямую вызываем нужные действия
    
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
    
    # Устанавливаем состояние выбора длительности пакета
    await state.set_state(BuyESim.select_duration)
    
    # Создаем клавиатуру с длительностями пакетов
    keyboard = get_durations_keyboard(packages, country_code, language_code=language_code)
    
    # Формируем сообщение с информацией о стране и выборе длительности
    flag = country.flag_emoji or '🌍'
    # Используем локализованное название страны
    country_name = country.name_ru if language_code == 'ru' and hasattr(country, 'name_ru') and country.name_ru else country.name
    
    if language_code == 'ru':
        header = f"{flag} **{country_name}** - Выберите длительность пакета:"
        message = (
            f"{header}\n\n"
            f"Выберите длительность интернет-пакета для вашей поездки в {country_name}. "
            f"Все пакеты включают высокоскоростной интернет с поддержкой 4G/LTE и 5G (где доступно)."
        )
    else:
        header = f"{flag} **{country_name}** - Select package duration:"
        message = (
            f"{header}\n\n"
            f"Choose the duration of your internet package for your trip to {country_name}. "
            f"All packages include high-speed internet with 4G/LTE and 5G support (where available)."
        )
    
    await callback.message.edit_text(
        message,
        reply_markup=keyboard.as_markup(),
        parse_mode="Markdown"
    )
    
    await callback.answer()


@router.callback_query(F.data == "page_info")
async def process_page_info(callback: CallbackQuery):
    """Обработчик нажатия на информацию о странице (игнорируем, это просто информация)"""
    await callback.answer()


@router.callback_query(F.data.startswith("duration_header:"))
async def process_duration_header(callback: CallbackQuery):
    """Обработчик нажатия на заголовок группы пакетов по длительности (игнорируем, это просто заголовок)"""
    # Получаем длительность из callback_data
    duration = callback.data.split(":")[1]
    
    # Получаем язык пользователя
    language_code = callback.from_user.language_code or 'ru'
    
    # Показываем информационное сообщение
    if language_code == 'ru':
        await callback.answer(f"Пакеты на {duration} дней")
    else:
        await callback.answer(f"Packages for {duration} days")