import os
import logging
import aiohttp
import pycountry
from typing import Dict, List, Optional, Any, Union
from sqlalchemy.ext.asyncio import AsyncSession
from dotenv import load_dotenv

from database.models import Country, Package
from database.queries import get_all_countries, get_country_by_code, get_packages_by_country

# Загружаем переменные окружения
load_dotenv()

# Настраиваем логирование
logger = logging.getLogger(__name__)

class ESIMService:
    """Сервис для работы с API поставщика eSIM"""
    
    def __init__(self):
        """Инициализация сервиса"""
        self.api_key = os.getenv("ESIM_API_KEY", "")
        # Получаем базовый URL без /api/v1
        self.api_base_url = os.getenv("ESIM_API_URL", "https://api.esimaccess.com")
        
        if not self.api_key:
            logger.warning("ESIM_API_KEY не установлен. Функциональность API будет ограничена.")
            
        logger.info(f"Используемый базовый URL API: {self.api_base_url}")
    
    async def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None, json_data: Optional[Dict] = None) -> Dict:
        """Базовый метод для выполнения запросов к API"""
        # Добавляем префикс /api/v1 к URL
        api_path = "/api/v1/"
        
        # Очищаем эндпоинт от лишних слешей
        if endpoint.startswith("/"):
            endpoint = endpoint[1:]
            
        # Формируем полный URL
        url = f"{self.api_base_url}{api_path}{endpoint}"
        
        # Подробно логируем запрос
        logger.info(f"★★★ Полный запрос к API ★★★")
        logger.info(f"Метод: {method.upper()}")
        logger.info(f"Базовый URL: {self.api_base_url}")
        logger.info(f"Путь API: {api_path}")
        logger.info(f"Эндпоинт: {endpoint}")
        logger.info(f"Полный URL: {url}")
        logger.info(f"Параметры: {params}")
        logger.info(f"JSON данные: {json_data}")
        
        # Используем стандартный способ авторизации с RT-AccessCode
        headers = {
            "RT-AccessCode": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        logger.info(f"API заголовки: {headers}")
        
        try:
            async with aiohttp.ClientSession() as session:
                logger.debug(f"Отправка {method} запроса к {url}")
                
                if method.lower() == "get":
                    async with session.get(url, headers=headers, params=params) as response:
                        return await self._process_response(response)
                elif method.lower() == "post":
                    async with session.post(url, headers=headers, json=json_data) as response:
                        return await self._process_response(response)
                elif method.lower() == "put":
                    async with session.put(url, headers=headers, json=json_data) as response:
                        return await self._process_response(response)
                elif method.lower() == "delete":
                    async with session.delete(url, headers=headers) as response:
                        return await self._process_response(response)
                else:
                    raise ValueError(f"Неподдерживаемый метод HTTP: {method}")
        except aiohttp.ClientError as e:
            logger.error(f"Ошибка соединения с API: {e}")
            raise
    
    async def _process_response(self, response: aiohttp.ClientResponse) -> Dict:
        """Обработка ответа от API"""
        if response.status == 204:  # No content
            return {}
        
        try:
            # Логируем статус ответа и заголовки для отладки
            logger.info(f"Статус ответа API: {response.status}")
            logger.info(f"Заголовки ответа: {response.headers}")
            
            # Получаем текст ответа для логирования
            text = await response.text()
            logger.info(f"Тело ответа: {text[:500]}" + ('...' if len(text) > 500 else ''))
            
            # Пробуем распарсить JSON
            try:
                data = await response.json(content_type=None)  # Игнорируем content-type
            except:
                # Если не удалось распарсить JSON, пробуем еще раз из текста
                import json
                try:
                    data = json.loads(text)
                except:
                    logger.error(f"Не удалось распарсить JSON: {text[:200]}")
                    return {"error": "Не удалось распарсить ответ", "text": text[:200]}
            
            # Проверяем на ошибки
            if response.status >= 400:
                error_message = data.get("message", data.get("error", "Неизвестная ошибка"))
                error_code = data.get("code", "unknown")
                logger.error(f"API вернул ошибку: {response.status} - {error_message} (код: {error_code})")
                return {"error": error_message, "code": error_code}
                
            return data
        except Exception as e:
            logger.error(f"Ошибка при обработке ответа API: {e}")
            return {"error": str(e)}
    

    
    async def check_balance(self) -> Dict:
        """Проверка баланса API для проверки работоспособности API"""
        try:
            logger.info("Проверка баланса API - тест подключения")
            # Используем эндпоинт из документации для проверки API
            response = await self._make_request("post", "open/balance/query")
            
            if response.get("success"):
                logger.info(f"Успешное подключение к API! Баланс: {response.get('obj', {}).get('balance', '0')}")
                return response
            else:
                logger.error(f"API вернул ошибку при проверке баланса: {response.get('errorMsg')}")
                return {}
        except Exception as e:
            logger.error(f"Ошибка при проверке баланса API: {e}")
            return {}

    def _get_hardcoded_countries(self) -> List[Dict]:
        """Возвращает хардкод список стран на случай недоступности API"""
        logger.info("Возвращаем хардкод список стран")
        return [
            {"code": "US", "name": "United States", "flag_emoji": "🇺🇸", "is_available": True},
            {"code": "GB", "name": "United Kingdom", "flag_emoji": "🇬🇧", "is_available": True},
            {"code": "DE", "name": "Germany", "flag_emoji": "🇩🇪", "is_available": True},
            {"code": "FR", "name": "France", "flag_emoji": "🇫🇷", "is_available": True},
            {"code": "IT", "name": "Italy", "flag_emoji": "🇮🇹", "is_available": True},
            {"code": "ES", "name": "Spain", "flag_emoji": "🇪🇸", "is_available": True},
            {"code": "TR", "name": "Turkey", "flag_emoji": "🇹🇷", "is_available": True},
            {"code": "AE", "name": "United Arab Emirates", "flag_emoji": "🇦🇪", "is_available": True},
            {"code": "TH", "name": "Thailand", "flag_emoji": "🇹🇭", "is_available": True},
            {"code": "JP", "name": "Japan", "flag_emoji": "🇯🇵", "is_available": True},
            {"code": "CN", "name": "China", "flag_emoji": "🇨🇳", "is_available": True},
            {"code": "SG", "name": "Singapore", "flag_emoji": "🇸🇬", "is_available": True},
            {"code": "AU", "name": "Australia", "flag_emoji": "🇦🇺", "is_available": True},
            {"code": "CA", "name": "Canada", "flag_emoji": "🇨🇦", "is_available": True},
            {"code": "MX", "name": "Mexico", "flag_emoji": "🇲🇽", "is_available": True},
            {"code": "BR", "name": "Brazil", "flag_emoji": "🇧🇷", "is_available": True},
            {"code": "EG", "name": "Egypt", "flag_emoji": "🇪🇬", "is_available": True},
            {"code": "ZA", "name": "South Africa", "flag_emoji": "🇿🇦", "is_available": True},
            {"code": "RU", "name": "Russia", "flag_emoji": "🇷🇺", "is_available": True},
            {"code": "IN", "name": "India", "flag_emoji": "🇮🇳", "is_available": True},
        ]
    
    async def get_countries(self) -> List[Dict]:
        """Получение списка стран из доступных пакетов API"""
        logger.info("Получаем список стран из доступных пакетов")
        try:
            # Пробуем сначала GET запрос без параметров
            response = await self._make_request("GET", "/open/package/list")
            
            # Если GET запрос не сработал, пробуем POST запрос
            if response.get("error") or ("result" not in response and "obj" not in response):
                logger.warning("GET запрос не сработал, пробуем POST запрос")
                data = {
                    "locationCode": "",  # пустой параметр для получения всех пакетов
                    "type": "BASE"       # только базовые пакеты, не пополнения
                }
                response = await self._make_request("POST", "/open/package/list", json_data=data)
            
            # Проверяем на ошибки
            if response.get("error"):
                logger.error(f"Ошибка при получении списка пакетов: {response.get('error')}")
                return self._get_hardcoded_countries()
                
            # Пробуем разные структуры ответа
            packages_list = []
            if "result" in response:
                packages_list = response.get("result", [])
            elif "obj" in response and "packageList" in response["obj"]:
                packages_list = response["obj"]["packageList"]
                
            if not packages_list:
                logger.warning("Получен пустой список пакетов от API")
                return self._get_hardcoded_countries()
                
            logger.info(f"Получено {len(packages_list)} пакетов от API")
            
            # Создаем словарь стран для исключения дубликатов
            countries_dict = {}
            
            # Добавляем специальные значения для глобальных и региональных пакетов
            countries_dict["!GL"] = {
                "code": "!GL", 
                "name": "Global Packages", 
                "flag_emoji": "🌎", 
                "is_available": True
            }
            
            countries_dict["!RG"] = {
                "code": "!RG", 
                "name": "Regional Packages", 
                "flag_emoji": "🌍", 
                "is_available": True
            }
            
            # Обрабатываем каждый пакет и извлекаем страны
            for package in packages_list:
                # Получаем код страны из пакета
                country_code = package.get("country", "")
                if not country_code:
                    # Пробуем альтернативные поля
                    country_code = package.get("location", "")
                
                # Если локация указана как список стран через запятую
                if country_code:
                    country_codes = [loc.strip() for loc in country_code.split(",")]
                    
                    # Обрабатываем каждый код страны
                    for code in country_codes:
                        # Пропускаем пустые коды
                        if not code:
                            continue
                            
                        # Проверяем, есть ли уже такая страна в словаре
                        if code not in countries_dict:
                            try:
                                # Пробуем получить название страны через pycountry
                                country = pycountry.countries.get(alpha_2=code)
                                if country:
                                    countries_dict[code] = {
                                        "code": code,
                                        "name": country.name,
                                        "flag_emoji": self._create_flag_emoji(code),
                                        "is_available": True
                                    }
                            except Exception as e:
                                logger.warning(f"Не удалось получить информацию о стране {code}: {e}")
            
            # Преобразуем словарь в список
            countries = list(countries_dict.values())
            
            # Если список пуст, возвращаем хардкод
            if not countries:
                logger.warning("Не удалось извлечь страны из пакетов")
                return self._get_hardcoded_countries()
                
            # Сортируем по имени
            countries.sort(key=lambda x: x["name"])  
            
            # Перемещаем глобальные и региональные пакеты в начало списка
            if "!GL" in countries_dict:
                countries = [countries_dict["!GL"]] + [c for c in countries if c["code"] != "!GL"]
            if "!RG" in countries_dict:
                countries = [countries_dict["!RG"]] + [c for c in countries if c["code"] != "!RG" and c["code"] != "!GL"]
            
            logger.info(f"Получено {len(countries)} уникальных стран из API")
            return countries
        except Exception as e:
            logger.error(f"Общая ошибка при получении стран: {e}")
            return self._get_hardcoded_countries()
            

    
    async def get_packages(self, country_code: str) -> List[Dict]:
        """Получение списка пакетов для страны"""
        try:
            logger.info(f"Запрос пакетов для страны {country_code} с использованием API open/package/list")
            
            # Пробуем разные варианты параметров для API
            # Вариант 1: используем параметр country
            response = await self._make_request(
                "GET", 
                "/open/package/list", 
                params={"country": country_code}
            )
            
            # Проверяем на ошибки и пробуем альтернативный вариант
            if response.get("error") or "result" not in response:
                logger.warning(f"Первый метод не сработал, пробуем альтернативный для {country_code}")
                # Вариант 2: используем параметр locationCode
                response = await self._make_request(
                    "POST", 
                    "/open/package/list", 
                    json_data={"locationCode": country_code, "type": "BASE"}
                )
            
            # Проверяем ответ и извлекаем данные
            if response.get("error"):
                logger.error(f"Ошибка при получении пакетов для {country_code}: {response.get('error')}")
                return []
            
            # Пробуем разные структуры ответа
            packages_list = []
            if "result" in response:
                packages_list = response.get("result", [])
            elif "obj" in response and "packageList" in response["obj"]:
                packages_list = response["obj"]["packageList"]
                
            logger.info(f"Получено {len(packages_list)} пакетов для {country_code} от API")
            
            result = []
            for item in packages_list:
                # Извлекаем данные из структуры API
                data_amount_bytes = item.get("volume", 0)
                
                # Получаем цену и логируем её для отладки
                price_value = item.get("amount", 0)
                price_currency = item.get("currency", "USD")
                logger.info(f"Цена пакета в API: {price_value} {price_currency}, тип: {type(price_value).__name__}")
                
                duration_days = item.get("duration", 0)
                package_name = f"{self._convert_to_gb(data_amount_bytes)}GB / {duration_days} дней"
                description = item.get("description", "")
                
                # Логируем всю структуру пакета для отладки
                logger.info(f"Структура пакета: {item}")
                
                # Получаем код пакета - пробуем разные варианты полей
                package_code = item.get("packageCode", "")  # Сначала пробуем packageCode
                if not package_code:
                    package_code = item.get("packageId", "")  # Если нет, пробуем packageId
                if not package_code:
                    package_code = item.get("code", "")  # Если нет, пробуем code
                
                # Если нет кода, создаем уникальный на основе страны, трафика и длительности
                if not package_code:
                    data_gb = self._convert_to_gb(data_amount_bytes)
                    package_code = f"{country_code}-{data_gb:.1f}GB-{duration_days}D"
                    logger.info(f"Создан уникальный код пакета: {package_code}")
                
                # Формируем объект пакета с правильными ключами для соответствия модели БД
                result.append({
                    "package_code": package_code,
                    "slug": f"{country_code.lower()}-{package_code.lower()}",
                    "name": package_name,
                    "data_amount": self._convert_to_gb(data_amount_bytes),
                    "duration": duration_days,
                    "price": self._convert_price(price_value),
                    "description": description,
                    "is_available": True
                })
            
            logger.info(f"Обработано и возвращено {len(result)} пакетов для {country_code}")
            return result
        except Exception as e:
            logger.error(f"Ошибка при получении списка пакетов для {country_code}: {e}")
            return []
    
    async def sync_countries_and_packages(self, session: AsyncSession) -> bool:
        """Синхронизация стран и пакетов из API в базу данных"""
        try:
            logger.info("🔄 Начинаем синхронизацию стран и пакетов из API в базу данных")
            
            # Получаем списки стран от API
            countries_data = await self.get_countries()
            logger.info(f"📋 Получено {len(countries_data)} стран от API")
            
            if not countries_data:
                logger.warning("❌ Не удалось получить страны от API или список пуст")
                return False
            
            countries_updated = 0
            countries_created = 0
            packages_updated = 0
            packages_created = 0
            packages_failed = 0
            countries_with_packages = 0
            
            # Обновляем страны в базе данных
            for country_data in countries_data:
                code = country_data.get("code")
                if not code:
                    logger.warning(f"⚠️ Страна без кода: {country_data}")
                    continue
                
                # Проверяем, существует ли уже страна
                existing_country = await get_country_by_code(session, code)
                
                if existing_country:
                    # Обновляем существующую страну
                    existing_country.name = country_data.get("name", existing_country.name)
                    existing_country.flag_emoji = country_data.get("flag_emoji", existing_country.flag_emoji)
                    existing_country.is_available = country_data.get("is_available", True)
                    countries_updated += 1
                    logger.info(f"✏️ Обновлена страна: {code} - {existing_country.name}")
                else:
                    # Создаем новую страну
                    new_country = Country(
                        code=code,
                        name=country_data.get("name", ""),
                        flag_emoji=country_data.get("flag_emoji", ""),
                        is_available=country_data.get("is_available", True)
                    )
                    session.add(new_country)
                    countries_created += 1
                    logger.info(f"➕ Создана новая страна: {code} - {new_country.name}")
                
                # Сохраняем изменения, чтобы получить ID страны
                await session.flush()
                
                # Получаем пакеты для страны с несколькими попытками
                logger.info(f"🔍 Запрашиваем пакеты для страны {code}")
                
                # Делаем до 3 попыток получения пакетов для каждой страны
                max_package_attempts = 3
                package_attempt = 1
                packages_data = None
                
                while package_attempt <= max_package_attempts and not packages_data:
                    logger.info(f"Попытка {package_attempt} из {max_package_attempts} получения пакетов для {code}")
                    packages_data = await self.get_packages(code)
                    
                    if not packages_data:
                        logger.warning(f"⚠️ Попытка {package_attempt}: Нет пакетов для страны {code} или не удалось их получить")
                        package_attempt += 1
                        if package_attempt <= max_package_attempts:
                            # Ждем перед следующей попыткой
                            await asyncio.sleep(1)
                
                if not packages_data:
                    logger.warning(f"⚠️ Все попытки получения пакетов для страны {code} не удались")
                    continue
                
                logger.info(f"📦 Получено {len(packages_data)} пакетов для страны {code}")
                country_id = existing_country.id if existing_country else new_country.id
                
                # Увеличиваем счетчик стран с пакетами
                countries_with_packages += 1
                
                # Получаем существующие пакеты для страны один раз
                existing_packages = await get_packages_by_country(session, country_id)
                logger.info(f"💾 В базе данных уже есть {len(existing_packages)} пакетов для страны {code}")
                
                # Создаем список всех существующих кодов пакетов для быстрого поиска
                existing_package_codes = {p.package_code for p in existing_packages}
                
                # Дополнительно получаем все коды пакетов из базы данных для проверки уникальности
                from database.queries import get_package_by_code
                
                # Обновляем пакеты в базе данных
                for package_data in packages_data:
                    package_code = package_data.get("package_code")
                    if not package_code:
                        logger.warning(f"⚠️ Пакет без кода: {package_data}")
                        packages_failed += 1
                        continue
                    
                    # Проверяем, что пакет с таким кодом уже существует в другой стране
                    if package_code not in existing_package_codes:
                        # Проверяем глобально по всей базе
                        existing_global_package = await get_package_by_code(session, package_code)
                        if existing_global_package and existing_global_package.country_id != country_id:
                            # Если пакет с таким кодом уже существует в другой стране, создаем уникальный код
                            data_gb = package_data.get("data_amount", 0)
                            duration_days = package_data.get("duration", 0)
                            original_code = package_code
                            package_code = f"{code}-{data_gb:.1f}GB-{duration_days}D-{original_code}"
                            logger.warning(f"⚠️ Код пакета {original_code} уже существует в другой стране, создан новый код: {package_code}")
                            package_data["package_code"] = package_code
                    
                    # Ищем пакет по коду в базе данных
                    existing_package = next((p for p in existing_packages if p.package_code == package_code), None)
                    
                    if existing_package:
                        # Обновляем существующий пакет
                        existing_package.name = package_data.get("name", existing_package.name)
                        existing_package.data_amount = package_data.get("data_amount", existing_package.data_amount)
                        existing_package.duration = package_data.get("duration", existing_package.duration)
                        existing_package.price = package_data.get("price", existing_package.price)
                        existing_package.description = package_data.get("description", existing_package.description)
                        existing_package.is_available = package_data.get("is_available", True)
                        packages_updated += 1
                        logger.info(f"✏️ Обновлен пакет: {package_code} для страны {code}")
                    else:
                        # Создаем новый пакет
                        new_package = Package(
                            country_id=country_id,
                            package_code=package_code,
                            slug=package_data.get("slug", f"{code.lower()}-{package_code.lower()}"),
                            name=package_data.get("name", ""),
                            data_amount=package_data.get("data_amount", 0.0),
                            duration=package_data.get("duration", 0),
                            price=package_data.get("price", 0.0),
                            description=package_data.get("description", ""),
                            is_available=package_data.get("is_available", True)
                        )
                        session.add(new_package)
                        packages_created += 1
                        logger.info(f"➕ Создан новый пакет: {package_code} для страны {code}")
                
                # Делаем промежуточный коммит после каждой страны
                await session.flush()
            
            # Сохраняем все изменения в базе данных
            await session.commit()
            
            # Итоговая статистика
            logger.info("✅ Синхронизация стран и пакетов завершена успешно")
            logger.info(f"📊 Статистика синхронизации:")
            logger.info(f"   - Стран обновлено: {countries_updated}")
            logger.info(f"   - Стран создано: {countries_created}")
            logger.info(f"   - Стран с пакетами: {countries_with_packages} из {len(countries_data)}")
            logger.info(f"   - Пакетов обновлено: {packages_updated}")
            logger.info(f"   - Пакетов создано: {packages_created}")
            logger.info(f"   - Пакетов с ошибками: {packages_failed}")
            
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка при синхронизации стран и пакетов: {e}")
            await session.rollback()
            return False


    def _create_flag_emoji(self, country_code: str) -> str:
        """Создание эмодзи флага из двухбуквенного кода страны ISO 3166-1 alpha-2"""
        if not country_code or len(country_code) != 2:
            return ""
        # Сдвиг символов для создания эмодзи флага
        # Региональные индикаторы символов начинаются с U+1F1E6 (🇦) для буквы A
        # и заканчиваются U+1F1FF (🇿) для буквы Z
        return "".join(chr(ord('\U0001F1E6') + ord(c) - ord('A')) for c in country_code.upper())
    
    def _convert_to_gb(self, bytes_value: int) -> float:
        """Конвертация байтов в гигабайты"""
        if not bytes_value:
            return 0.0
        return round(bytes_value / (1024 * 1024 * 1024), 2)
    
    def _convert_price(self, price_value: Any) -> float:
        """Конвертация цены из формата API в доллары
        
        Поддерживает разные форматы цены в API:
        - Целое число (10000 = $1.00)
        - Строка с числом ("10.99")
        - Число с плавающей точкой (10.99)
        """
        if not price_value:
            return 0.0
            
        # Логируем тип и значение для отладки
        logger.info(f"Конвертация цены: {price_value}, тип: {type(price_value).__name__}")
        
        try:
            # Если цена пришла как строка, преобразуем в число
            if isinstance(price_value, str):
                # Удаляем символы валюты и пробелы
                price_value = price_value.replace('$', '').replace(' ', '').strip()
                return float(price_value)
            
            # Если цена в формате 10000 = $1.00
            if isinstance(price_value, int) and price_value > 100:
                return round(price_value / 10000, 2)
                
            # Если цена уже в долларах (например, 10.99)
            return float(price_value)
        except (ValueError, TypeError) as e:
            logger.error(f"Ошибка при конвертации цены {price_value}: {e}")
            return 0.0


# Создаем синглтон экземпляр сервиса для использования в других модулях
esim_service = ESIMService()
