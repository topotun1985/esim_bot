import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update

from database.models import Country, Package, User
from services.esim_service import ESIMService

router = Router()
logger = logging.getLogger(__name__)

# Фильтр для администраторов
async def admin_filter(message: Message, session: AsyncSession) -> bool:
    """Проверяет, является ли пользователь администратором"""
    user = await session.execute(
        select(User).where(User.telegram_id == message.from_user.id)
    )
    user = user.scalar_one_or_none()
    return user and user.is_admin


@router.message(Command("update_packages"), admin_filter)
async def update_packages(message: Message, esim_service: ESIMService, session: AsyncSession):
    """
    Обновление списка пакетов eSIM из API провайдера
    Команда доступна только для администраторов
    """
    await message.answer("🔄 Начинаю процесс обновления пакетов в базе данных...")

    # Проверяем наличие кода страны в аргументах команды
    args = message.text.split()
    country_code = None
    if len(args) > 1:
        country_code = args[1].upper()
        await message.answer(f"📍 Буду обновлять пакеты только для страны: {country_code}")

    try:
        # Получаем все страны из базы данных
        countries_query = select(Country)
        if country_code:
            countries_query = countries_query.where(Country.code == country_code)

        countries = await session.execute(countries_query)
        countries = countries.scalars().all()

        if not countries:
            return await message.answer("❌ Страны не найдены в базе данных.")

        total_countries = len(countries)
        updated_packages = 0
        new_packages = 0

        await message.answer(f"🌍 Найдено {total_countries} стран в базе данных. Начинаю обновление пакетов...")

        # Обновляем пакеты для каждой страны
        for country in countries:
            # Получаем пакеты для страны из API
            packages = await esim_service.get_available_package_codes(country.code)

            if not packages:
                logger.warning(f"No packages found for country {country.code}")
                await message.answer(f"⚠️ Для страны {country.code} ({country.name}) не найдено пакетов в API.")
                continue

            # Получаем существующие пакеты из базы данных для этой страны
            existing_packages = await session.execute(
                select(Package).where(Package.country_id == country.id)
            )
            existing_packages = existing_packages.scalars().all()

            # Создаем словарь существующих пакетов по коду для быстрого поиска
            existing_packages_dict = {p.package_code: p for p in existing_packages}

            # Обрабатываем каждый пакет из API
            for api_package in packages:
                package_code = api_package["code"]
                package_name = api_package["name"]
                data_volume = api_package.get("data_volume", "")
                validity = api_package.get("validity", "")

                # Парсим количество данных и длительность из названия и информации
                data_amount = 0
                duration = 0

                # Попытка извлечь данные из названия пакета и data_volume
                try:
                    # Примерное определение объема данных из названия или data_volume
                    if "GB" in package_name:
                        data_str = package_name.split("GB")[0].strip().split()[-1]
                        data_amount = float(data_str)
                    elif data_volume and "GB" in data_volume:
                        data_str = data_volume.split("GB")[0].strip()
                        data_amount = float(data_str)

                    # Примерное определение длительности из названия или validity
                    if "Day" in package_name or "Days" in package_name:
                        days_str = package_name.split("Day")[0].strip().split()[-1]
                        duration = int(days_str)
                    elif validity and ("Day" in validity or "Days" in validity):
                        days_str = validity.split("Day")[0].strip()
                        duration = int(days_str)
                except Exception as e:
                    logger.warning(f"Не удалось извлечь данные из названия пакета {package_name}: {e}")

                # Если пакет уже существует в базе, обновляем информацию
                if package_code in existing_packages_dict:
                    existing_package = existing_packages_dict[package_code]

                    # Обновляем только если данные изменились
                    if (existing_package.name != package_name or
                        (data_amount > 0 and existing_package.data_amount != data_amount) or
                        (duration > 0 and existing_package.duration != duration)):

                        # Обновляем пакет
                        await session.execute(
                            update(Package)
                            .where(Package.id == existing_package.id)
                            .values(
                                name=package_name,
                                data_amount=data_amount if data_amount > 0 else existing_package.data_amount,
                                duration=duration if duration > 0 else existing_package.duration,
                                is_available=True
                            )
                        )
                        updated_packages += 1

                # Если пакет новый, добавляем его в базу данных
                else:
                    # Создаем новый пакет
                    new_package = Package(
                        country_id=country.id,
                        package_code=package_code,
                        name=package_name,
                        data_amount=data_amount if data_amount > 0 else 0,
                        duration=duration if duration > 0 else 0,
                        price=0,  # Цена должна быть установлена вручную
                        is_available=True
                    )
                    session.add(new_package)
                    new_packages += 1

            # Сохраняем изменения для каждой страны
            await session.commit()
            await message.answer(f"✅ Обновлены пакеты для страны {country.code} ({country.name})")

        # Отправляем итоговую информацию
        await message.answer(
            f"🎉 Обновление пакетов завершено!\n"
            f"📊 Статистика:\n"
            f"- Обработано стран: {total_countries}\n"
            f"- Обновлено пакетов: {updated_packages}\n"
            f"- Добавлено новых пакетов: {new_packages}\n\n"
            f"ℹ️ Цены на пакеты нужно установить вручную. Новые пакеты добавлены с ценой 0."
        )

        # Если обновляли все страны, предлагаем посмотреть список пакетов для Словении
        if not country_code:
            await message.answer(
                "💡 Для проверки доступных пакетов для Словении (SI) используйте команду:\n"
                "/packages SI"
            )

    except Exception as e:
        logger.exception(f"Ошибка при обновлении пакетов: {e}")
        await message.answer(f"❌ Произошла ошибка при обновлении пакетов: {str(e)}")
        # Отменяем все изменения в случае ошибки
        await session.rollback()


@router.message(Command("packages"), admin_filter)
async def list_packages(message: Message, esim_service: ESIMService, session: AsyncSession):
    """Получение списка доступных пакетов eSIM"""

    location_code = ""  # Пустая строка для получения всех пакетов

    # Проверяем, был ли указан код страны
    if len(message.text.split()) > 1:
        location_code = message.text.split()[1].upper()

    await message.answer(f"🔍 Запрашиваю список пакетов для локации: {location_code or 'все'}")

    try:
        # Получаем список пакетов
        packages = await esim_service.get_available_package_codes(location_code)

        if not packages:
            return await message.answer("❌ Не найдено доступных пакетов для указанной локации.")

        # Формируем сообщение с информацией о пакетах (ограничиваем до 20 пакетов)
        max_packages = min(20, len(packages))

        result_msg = f"📦 Найдено {len(packages)} пакетов. Показаны первые {max_packages}:\n\n"

        for i, package in enumerate(packages[:max_packages]):
            result_msg += (
                f"{i+1}. *Код:* `{package['code']}`\n"
                f"   *Название:* {package['name']}\n"
                f"   *Объем:* {package['data_volume']}\n"
                f"   *Срок:* {package['validity']}\n\n"
            )

        # Если пакетов слишком много, добавляем подсказку
        if len(packages) > max_packages:
            result_msg += f"\n⚠️ Показаны только первые {max_packages} из {len(packages)} пакетов."

        # Добавляем подсказку по использованию
        result_msg += "\n\nДля обновления пакетов в базе данных используйте команду:\n/update_packages [код_страны]"

        await message.answer(result_msg, parse_mode="Markdown")

    except Exception as e:
        logger.exception(f"Ошибка при получении пакетов: {e}")
        await message.answer(f"❌ Произошла ошибка при получении списка пакетов: {str(e)}")


@router.message(Command("sync_packages"), admin_filter)
async def sync_packages(message: Message, esim_service: ESIMService, session: AsyncSession):
    """Синхронизировать пакеты eSIM с API"""
    country_code = message.text.split()[1].upper() if len(message.text.split()) > 1 else ""

    if country_code:
        await message.answer(f"🔄 Начинаю синхронизацию пакетов для страны {country_code}...")
    else:
        await message.answer("🔄 Начинаю синхронизацию пакетов для всех стран...")

    # Запускаем полную синхронизацию пакетов
    async with message.bot.get('db_session')() as session:
        result = await esim_service.sync_packages_with_api(session, country_code if country_code else None)

        if result["success"]:
            # Формируем подробное сообщение по каждой стране
            country_stats = []

            for country_result in result["processed_countries"]:
                country_stats.append(
                    f"🌍 {country_result['country_name']} ({country_result['country_code']}):\n"
                    f"  • Добавлено: {country_result['packages_added']}\n"
                    f"  • Обновлено: {country_result['packages_updated']}\n"
                    f"  • Деактивировано: {country_result['packages_deactivated']}"
                )

            # Общая статистика
            stats_message = (
                f"✅ Синхронизация пакетов успешно завершена.\n\n"
                f"📊 Общая статистика:\n"
                f"• Обработано стран: {result['countries_processed']}\n"
                f"• Добавлено пакетов: {result['packages_added']}\n"
                f"• Обновлено пакетов: {result['packages_updated']}\n"
                f"• Деактивировано пакетов: {result['packages_deactivated']}"
            )

            await message.answer(stats_message)

            # Если была синхронизация только одной страны, показываем подробности сразу
            if country_code and len(country_stats) == 1:
                await message.answer(country_stats[0])
            # Если было много стран, отправляем подробную статистику отдельным сообщением
            elif len(country_stats) > 1:
                await message.answer("📋 Детальная статистика по странам:")

                # Отправляем не более 10 стран, чтобы не перегружать чат
                for i in range(0, min(10, len(country_stats))):
                    await message.answer(country_stats[i])

                if len(country_stats) > 10:
                    await message.answer(f"... и еще {len(country_stats) - 10} стран")
        else:
            error_message = "❌ Ошибка при синхронизации пакетов:\n"
            error_message += "\n".join([f"• {err}" for err in result["errors"][:5]])

            if len(result["errors"]) > 5:
                error_message += f"\n... и еще {len(result['errors']) - 5} ошибок"

            await message.answer(error_message)