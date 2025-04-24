import asyncio
import logging
import psycopg2
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Настраиваем логгер
logging.basicConfig(
    level=logging.INFO, 
    format='[%(asctime)s] #%(levelname)-8s %(filename)s:%(lineno)d - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Получаем параметры подключения к БД
DB_NAME = os.getenv("POSTGRES_DB", "esim_bot")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "Vadim22021985")
DB_HOST = os.getenv("POSTGRES_HOST", "db")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

# Словарь с русскими названиями стран
COUNTRY_NAME_RU = {
    "ES": "Испания",
    "HK": "Гонконг",
    "MO": "Макао",
    "TH": "Таиланд",
    "NL": "Нидерланды",
    "IL": "Израиль",
    "TR": "Турция",
    "JO": "Иордания",
    "KW": "Кувейт",
    "OM": "Оман",
    "QA": "Катар",
    "AM": "Армения",
    "AE": "ОАЭ",
    "AZ": "Азербайджан",
    "GE": "Грузия",
    "BH": "Бахрейн",
    "SA": "Саудовская Аравия",
    "AT": "Австрия",
    "BE": "Бельгия",
    "BG": "Болгария",
    "HR": "Хорватия",
    "CY": "Кипр",
    "CZ": "Чехия",
    "DK": "Дания",
    "EE": "Эстония",
    "FI": "Финляндия",
    "FR": "Франция",
    "DE": "Германия",
    "GR": "Греция",
    "HU": "Венгрия",
    "IS": "Исландия",
    "IE": "Ирландия",
    "IT": "Италия",
    "LV": "Латвия",
    "LT": "Литва",
    "LU": "Люксембург",
    "MT": "Мальта",
    "PL": "Польша",
    "PT": "Португалия",
    "RO": "Румыния",
    "SK": "Словакия",
    "SI": "Словения",
    "SE": "Швеция",
    "CH": "Швейцария",
    "UA": "Украина",
    "GB": "Великобритания",
    "AX": "Аландские острова",
    "IM": "Остров Мэн",
    "JE": "Джерси",
    "RU": "Россия",
    "GG": "Гернси",
    "LI": "Лихтенштейн",
    "NO": "Норвегия",
    "RS": "Сербия",
    "GI": "Гибралтар",
    "AU": "Австралия",
    "MY": "Малайзия",
    "NZ": "Новая Зеландия",
    "PH": "Филиппины",
    "SG": "Сингапур",
    "LK": "Шри-Ланка",
    "VN": "Вьетнам",
    "CN": "Китай",
    "ID": "Индонезия",
    "IN": "Индия",
    "JP": "Япония",
    "KR": "Южная Корея",
    "YE": "Йемен",
    "AR": "Аргентина",
    "BO": "Боливия",
    "BR": "Бразилия",
    "CL": "Чили",
    "CO": "Колумбия",
    "CR": "Коста-Рика",
    "EC": "Эквадор",
    "SV": "Сальвадор",
    "GT": "Гватемала",
    "HN": "Гондурас",
    "NI": "Никарагуа",
    "PA": "Панама",
    "PY": "Парагвай",
    "PE": "Перу",
    "PR": "Пуэрто-Рико",
    "UY": "Уругвай",
    "RE": "Реюньон",
    "MG": "Мадагаскар",
    "MW": "Малави",
    "BW": "Ботсвана",
    "CF": "Центральноафриканская Республика",
    "TD": "Чад",
    "CG": "Конго",
    "CI": "Кот-д'Ивуар",
    "EG": "Египет",
    "GA": "Габон",
    "KE": "Кения",
    "LR": "Либерия",
    "ML": "Мали",
    "MA": "Марокко",
    "NE": "Нигер",
    "NG": "Нигерия",
    "SN": "Сенегал",
    "SC": "Сейшельские острова",
    "ZA": "ЮАР",
    "SD": "Судан",
    "SZ": "Эсватини",
    "TZ": "Танзания",
    "TN": "Тунис",
    "UG": "Уганда",
    "ZM": "Замбия",
    "KH": "Камбоджа",
    "DZ": "Алжир",
    "BD": "Бангладеш",
    "CA": "Канада",
    "MK": "Северная Македония",
    "MX": "Мексика",
    "MZ": "Мозамбик",
    "PK": "Пакистан",
    "BF": "Буркина-Фасо",
    "MD": "Молдова",
    "MC": "Монако",
    "AL": "Албания",
    "CM": "Камерун",
    "UZ": "Узбекистан",
    "NP": "Непал",
    "XK": "Косово",
    "MN": "Монголия",
    "BA": "Босния и Герцеговина",
    "ME": "Черногория",
    "KZ": "Казахстан",
    "KG": "Киргизия",
    "DO": "Доминиканская Республика",
    "GP": "Гваделупа",
    "BN": "Бруней",
    "BY": "Беларусь",
    "US": "США",
    "IQ": "Ирак",
    "GU": "Гуам",
    "MU": "Маврикий",
    "JM": "Ямайка"
}

def update_country_names_ru():
    """Обновляет русские названия стран в базе данных"""
    try:
        # Подключаемся к базе данных
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        
        # Создаем курсор
        cursor = conn.cursor()
        
        # Проверяем, существует ли столбец name_ru
        cursor.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'countries' AND column_name = 'name_ru'
        """)
        
        if cursor.fetchone() is None:
            logger.info("Column name_ru doesn't exist. Adding it...")
            cursor.execute("ALTER TABLE countries ADD COLUMN name_ru VARCHAR(255)")
        
        # Получаем все страны из базы
        cursor.execute("SELECT id, code, name FROM countries")
        countries = cursor.fetchall()
        
        updated_count = 0
        for country in countries:
            country_id, country_code, country_name = country
            
            if country_code in COUNTRY_NAME_RU:
                # Экранируем одинарные кавычки в русских названиях
                ru_name = COUNTRY_NAME_RU[country_code].replace("'", "''")
                cursor.execute(f"UPDATE countries SET name_ru = '{ru_name}' WHERE id = {country_id}")
                updated_count += 1
            else:
                # Экранируем одинарные кавычки в английских названиях
                en_name = country_name.replace("'", "''")
                cursor.execute(f"UPDATE countries SET name_ru = '{en_name}' WHERE id = {country_id}")
        
        # Сохраняем изменения
        conn.commit()
        logger.info(f"Updated {updated_count} country names with Russian translations")
        
    except Exception as e:
        logger.error(f"Error during country name updates: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == "__main__":
    update_country_names_ru()
