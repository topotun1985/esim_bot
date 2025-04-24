import os
import logging
import aiohttp
import pycountry
import os
import asyncio
import uuid
import json
import time
from typing import Dict, List, Optional, Any, Union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select
from dotenv import load_dotenv
from datetime import datetime

from database.models import Country, Package
from database.queries import get_all_countries, get_country_by_code, get_packages_by_country, get_package_by_code

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
        
        # Инициализируем логгер
        self.logger = logging.getLogger(__name__)
        
        if not self.api_key:
            self.logger.warning("ESIM_API_KEY не установлен. Функциональность API будет ограничена.")
            
        self.logger.info(f"Используемый базовый URL API: {self.api_base_url}")
        
    async def _make_request(self, method: str, endpoint: str, json_data: Dict = None, params: Dict = None, content_type: str = "application/json") -> Dict:
        """
        Выполняет HTTP-запрос к API
        
        Args:
            method: HTTP-метод (GET, POST, PUT, DELETE)
            endpoint: Конечная точка API
            json_data: JSON-данные для отправки в теле запроса
            params: Параметры запроса
            content_type: Тип содержимого запроса (application/json или text/plain)
            
        Returns:
            Dict: Ответ API
        """
        # Формируем полный URL
        url = f"{self.api_base_url}/api/v1/{endpoint}"
        
        # Генерируем необходимые значения для заголовков
        import uuid
        import time
        import hashlib
        
        request_id = str(uuid.uuid4())
        timestamp = str(int(time.time()))
        
        # Добавляем API-ключ в заголовки согласно документации API
        headers = {
            "Content-Type": content_type,
            "Accept": "application/json",
            "RT-AccessCode": self.api_key,
            "RT-Timestamp": timestamp,
            "RT-RequestID": request_id
        }
        
        # Создаем подпись для запроса, если требуется
        # Обычно это конкатенация API-ключа и временной метки, хешированная с помощью MD5/SHA-256
        # Пример: signature = hashlib.md5((self.api_key + timestamp).encode()).hexdigest()
        # headers["RT-Signature"] = signature
        
        # Подробное логирование запроса
        import json
        log_data = {
            "method": method,
            "url": url,
            "headers": {k: v if k != "RT-AccessCode" else "***" for k, v in headers.items()},
            "json_data": json_data,
            "params": params,
            "content_type": content_type
        }
        self.logger.info(f"API Request: {json.dumps(log_data, indent=2, ensure_ascii=False)}")
        
        try:
            # Создаем сессию для запроса
            async with aiohttp.ClientSession() as session:
                # Выполняем запрос в зависимости от метода
                if method.upper() == "GET":
                    async with session.get(url, headers=headers, params=params) as response:
                        # Получаем статус и текст ответа
                        status = response.status
                        try:
                            response_json = await response.json()
                        except:
                            response_text = await response.text()
                            self.logger.error(f"Не удалось распарсить JSON ответ: {response_text}")
                            response_json = {"error": f"Invalid JSON response: {response_text}"}
                    
                elif method.upper() == "POST":
                    # Проверяем тип содержимого и соответствующим образом отправляем данные
                    if content_type == "text/plain" and json_data:
                        # Для text/plain отправляем данные как строку
                        data_str = json.dumps(json_data)
                        async with session.post(url, headers=headers, data=data_str, params=params) as response:
                            status = response.status
                            try:
                                response_json = await response.json()
                            except:
                                response_text = await response.text()
                                self.logger.error(f"Не удалось распарсить JSON ответ: {response_text}")
                                response_json = {"error": f"Invalid JSON response: {response_text}"}
                    else:
                        # Стандартный JSON-запрос
                        async with session.post(url, headers=headers, json=json_data, params=params) as response:
                            status = response.status
                            try:
                                response_json = await response.json()
                            except:
                                response_text = await response.text()
                                self.logger.error(f"Не удалось распарсить JSON ответ: {response_text}")
                                response_json = {"error": f"Invalid JSON response: {response_text}"}
                    
                elif method.upper() == "PUT":
                    async with session.put(url, headers=headers, json=json_data, params=params) as response:
                        # Получаем статус и текст ответа
                        status = response.status
                        try:
                            response_json = await response.json()
                        except:
                            response_text = await response.text()
                            self.logger.error(f"Не удалось распарсить JSON ответ: {response_text}")
                            response_json = {"error": f"Invalid JSON response: {response_text}"}
                    
                elif method.upper() == "DELETE":
                    async with session.delete(url, headers=headers, params=params) as response:
                        # Получаем статус и текст ответа
                        status = response.status
                        try:
                            response_json = await response.json()
                        except:
                            response_text = await response.text()
                            self.logger.error(f"Не удалось распарсить JSON ответ: {response_text}")
                            response_json = {"error": f"Invalid JSON response: {response_text}"}
                    
                else:
                    self.logger.error(f"❌ Неподдерживаемый HTTP-метод: {method}")
                    return {"error": f"Unsupported HTTP method: {method}"}
                
                # Логируем ответ API
                try:
                    self.logger.info(f"API Response Status: {status}")
                    self.logger.info(f"API Response: {json.dumps(response_json, indent=2, ensure_ascii=False)}")
                except:
                    self.logger.info(f"Не удалось логировать ответ API как JSON")
                
                return response_json
                
        except Exception as e:
            self.logger.exception(f"❌ Ошибка при выполнении запроса к API: {e}")
            return {"error": f"Request error: {str(e)}"}
            
    async def _handle_api_error(self, response: Dict, operation_name: str) -> Dict:
        """
        Унифицированная обработка ошибок API
        
        Args:
            response: Ответ API
            operation_name: Название операции для логирования
            
        Returns:
            Dict: Стандартизированный формат ошибки
        """
        # Проверяем наличие ошибки в ответе
        if "error" in response:
            error_msg = response.get("error", "Unknown error")
            self.logger.error(f"Ошибка при {operation_name}: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "api_response": response
            }
            
        # Проверяем успешность ответа в формате API
        if not response.get("success", False):
            error_msg = response.get("errorMsg", response.get("msg", "Unknown error"))
            error_code = response.get("errorCode", response.get("code", "Unknown code"))
            self.logger.error(f"Ошибка при {operation_name}: {error_code} - {error_msg}")
            return {
                "success": False,
                "error": f"{error_code} - {error_msg}",
                "api_response": response
            }
            
        # Если нет явных ошибок, но и нет данных
        if not response.get("data") and not response.get("obj"):
            self.logger.warning(f"В ответе API отсутствуют данные при {operation_name}")
            return {
                "success": False,
                "error": "No data in API response",
                "api_response": response
            }
            
        # Если все проверки пройдены, значит ответ успешный
        return None
            
    async def create_esim(self, order_id: str, package_code: str, email: str, phone_number: str = "", country_code: str = "") -> Dict:
        """
        Создает новую eSIM через API провайдера
        
        Args:
            order_id: ID заказа
            package_code: Код пакета
            email: Email пользователя
            phone_number: Номер телефона пользователя
            country_code: Код страны
            
        Returns:
            Dict: Результат создания eSIM
        """
        self.logger.info(f"Создание eSIM для заказа #{order_id}, код пакета: {package_code}")
        
        # Проверяем баланс аккаунта перед операцией
        if not await self.check_balance_before_operation("create eSIM"):
            self.logger.error(f"❌ Недостаточный баланс для создания eSIM с кодом пакета: {package_code}")
            return {
                "success": False,
                "error": "Недостаточный баланс аккаунта для создания eSIM"
            }
        
        # Проверяем, что email не пустой
        if not email or email == "None" or email is None:
            email = "no-email@example.com"
            self.logger.info(f"Email не указан для заказа #{order_id}, используем значение по умолчанию: {email}")
            
        # Получаем только суффикс кода пакета (последнюю часть)
        # Например, из "SI-0.3GB-1D-P82Y6VYRL" получаем "P82Y6VYRL"
        if "-" in package_code:
            package_code = package_code.split("-")[-1]
            self.logger.info(f"Используем модифицированный код пакета: {package_code}")
        
        # Формируем данные для запроса
        transaction_id = f"order-{order_id}-{uuid.uuid4().hex[:8]}"
        
        data = {
            "transactionId": transaction_id,
            "packageInfoList": [
                {
                    "packageCode": package_code,
                    "count": 1
                }
            ]
        }
        
        # Добавляем дополнительные параметры, если они указаны
        if email:
            data["email"] = email
        
        if country_code:
            data["countryCode"] = country_code
            
        if phone_number:
            data["phoneNumber"] = phone_number
        
        self.logger.info(f"Отправляем запрос на создание eSIM с данными: {json.dumps(data, indent=2)}")
        
        try:
            # Отправляем запрос на создание eSIM
            response = await self._make_request("POST", "open/esim/order", json_data=data)
            self.logger.info(f"Получен ответ от API при создании eSIM: {json.dumps(response, indent=2)}")
            
            # Обрабатываем ошибку API
            error_response = await self._handle_api_error(response, "create eSIM")
            if error_response:
                return error_response
            
            # Проверяем наличие данных в ответе
            result_data = response.get("data", {})
            if not result_data:
                # Проверяем альтернативный формат ответа
                result_data = response.get("obj", {})
                
                # Если есть orderNo в obj, это успешный ответ с асинхронным созданием eSIM
                if "orderNo" in result_data:
                    order_no = result_data.get("orderNo", "")
                    transaction_id = result_data.get("transactionId", "")
                    self.logger.info(f"Получен ответ с асинхронным созданием eSIM: orderNo={order_no}, transactionId={transaction_id}")
                    
                    return {
                        "success": True,
                        "order_no": order_no,
                        "transaction_id": transaction_id,
                        "async_creation": True,
                        "raw_response": response
                    }
                
                self.logger.error("В ответе API отсутствуют данные eSIM")
                return {
                    "success": False,
                    "error": "No data in API response",
                    "api_response": response
                }
                
            # Получаем номер заказа
            order_no = result_data.get("esimTranNo", "")
            if not order_no:
                self.logger.warning("В ответе API отсутствует номер заказа eSIM")
            
            # Проверяем наличие данных eSIM в ответе
            esim_info_list = result_data.get("esimInfoList", [])
            if not esim_info_list:
                self.logger.error("В ответе API отсутствует список eSIM")
                self.logger.info(f"Проверяем статус заказа eSIM: {order_no}")
                status_response = await self.check_esim_status(order_no)
                
                if status_response.get("success"):
                    return status_response
                
                return {
                    "success": False,
                    "error": "No eSIM data in API response",
                    "order_no": order_no,
                    "api_response": response
                }
                
            # Получаем данные первой eSIM из списка
            esim_info = esim_info_list[0]
            self.logger.info(f"Получены данные eSIM: {json.dumps(esim_info, indent=2)}")
            
            # Извлекаем необходимые данные
            iccid = esim_info.get("iccid", "")
            activation_code = esim_info.get("activationCode", "")
            qr_code = esim_info.get("qrCode", "")
            
            if not iccid:
                self.logger.warning("В ответе API отсутствует ICCID")
            
            if not activation_code:
                self.logger.warning("В ответе API отсутствует код активации")
                
            if not qr_code:
                self.logger.warning("В ответе API отсутствует QR-код")
            
            # Формируем результат
            result = {
                "success": True,
                "order_no": order_no,
                "esim_iccid": iccid,
                "activation_code": activation_code,
                "manual_activation_code": activation_code,  # Добавляем для совместимости с интерфейсом
                "qr_code_url": qr_code,
                "api_response": response
            }
            
            # Добавляем дополнительные данные, если они есть
            if "imsi" in esim_info:
                result["imsi"] = esim_info.get("imsi")
                
            if "msisdn" in esim_info:
                result["msisdn"] = esim_info.get("msisdn")
                
            if "apn" in esim_info:
                result["apn"] = esim_info.get("apn")
                
            self.logger.info(f"eSIM успешно создана для заказа #{order_id}")
            return result
            
        except Exception as e:
            self.logger.exception(f"Ошибка при создании eSIM: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
            
    async def check_esim_status(self, order_no: str, iccid: str = "") -> Dict:
        """
        Проверяет статус eSIM через API провайдера
        
        Args:
            order_no: Номер заказа у провайдера
            iccid: ICCID eSIM (опционально)
            
        Returns:
            Dict: Статус eSIM
        """
        self.logger.info(f"Проверка статуса eSIM для заказа {order_no}")
        
        try:
            # Формируем запрос для проверки статуса
            query_data = {
                "orderNo": order_no,
                "iccid": iccid or "",
                "pager": {
                    "pageNum": 1,
                    "pageSize": 20
                }
            }
            
            # Выполняем запрос к API
            response = await self._make_request("POST", "open/esim/query", json_data=query_data)
            
            # Обрабатываем ошибку API
            error_response = await self._handle_api_error(response, "check eSIM status")
            if error_response:
                return error_response
            
            # Извлекаем информацию о eSIM из ответа
            esim_data = {}
            
            # Проверяем различные форматы ответа API
            if "result" in response:
                esim_list = response.get("result", {}).get("list", [])
                if esim_list and len(esim_list) > 0:
                    esim_data = esim_list[0]
            elif "obj" in response:
                # Проверяем наличие esimList в obj
                if "esimList" in response.get("obj", {}):
                    esim_list = response.get("obj", {}).get("esimList", [])
                    if esim_list and len(esim_list) > 0:
                        esim_data = esim_list[0]
                # Проверяем наличие list в obj (старый формат)
                elif "list" in response.get("obj", {}):
                    esim_list = response.get("obj", {}).get("list", [])
                    if esim_list and len(esim_list) > 0:
                        esim_data = esim_list[0]
            
            # Проверяем, есть ли необходимые данные
            if not esim_data:
                self.logger.error(f"❌ API вернул пустой ответ на запрос статуса eSIM")
                return {
                    "success": False,
                    "error": "No eSIM data found",
                    "api_response": response
                }
                
            # Получаем статус eSIM из ответа
            esim_status = esim_data.get("esimStatus", "UNKNOWN")
            
            # Маппинг статусов провайдера на статусы в нашей системе
            status_mapping = {
                "IN_USE": "ACTIVATED",
                "INSTALLATION": "PROCESSING",
                "ENABLED": "ACTIVATED",  
                "GOT_RESOURCE": "ACTIVATED",
                "CANCEL": "CANCELED",
                "RELEASED": "CANCELED"
            }
            
            # Применяем маппинг статусов
            if esim_status in status_mapping:
                mapped_status = status_mapping[esim_status]
                self.logger.info(f"Mapped status from {esim_status} to {mapped_status}")
                esim_status = mapped_status
            
            # Извлекаем необходимые данные из ответа
            esim_info = {
                "success": True,
                "order_no": order_no,
                "iccid": esim_data.get("iccid", ""),
                "imsi": esim_data.get("imsi", ""),
                "msisdn": esim_data.get("msisdn", ""),
                "activation_code": esim_data.get("ac", ""),
                "qr_code": esim_data.get("qrCodeUrl", ""),
                "short_url": esim_data.get("shortUrl", ""),
                "esim_status": esim_status,
                "active_type": esim_data.get("activeType", 0),
                "expired_time": esim_data.get("expiredTime", ""),
                "total_volume": esim_data.get("totalVolume", 0),
                "total_duration": esim_data.get("totalDuration", 0),
                "duration_unit": esim_data.get("durationUnit", "DAY"),
                "order_usage": esim_data.get("orderUsage", 0),
                "pin": esim_data.get("pin", ""),
                "puk": esim_data.get("puk", ""),
                "apn": esim_data.get("apn", ""),
                "esim_list": [esim_data],
                "raw_response": response
            }
            
            self.logger.info(f"✅ Получена информация о eSIM: ICCID {esim_info['iccid']}")
            
            return esim_info
        except Exception as e:
            self.logger.exception(f"❌ Ошибка при проверке статуса eSIM: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "order_no": order_no
            }
            
    async def check_esim_order_status(self, order_no: str) -> Dict:
        """
        Проверяет статус заказа eSIM по номеру заказа
        
        Args:
            order_no: Номер заказа у провайдера
            
        Returns:
            Dict: Информация о статусе eSIM
        """
        self.logger.info(f"Проверка статуса заказа eSIM: {order_no}")
        
        # Вызываем существующий метод для проверки статуса
        status_result = await self.check_esim_status(order_no)
        
        # Преобразуем результат в формат, ожидаемый скриптом retry_failed_orders.py
        if status_result.get("success"):
            return {
                "success": True,
                "iccid": status_result.get("iccid", ""),
                "qr_code": status_result.get("qr_code", ""),
                "activation_code": status_result.get("activation_code", ""),
                "esim_tran_no": status_result.get("order_no", ""),
                "raw_response": status_result.get("raw_response", {})
            }
        else:
            # Если eSIM еще создается, возвращаем флаг async_creation
            if "No eSIM data found" in status_result.get("error", ""):
                return {
                    "success": True,
                    "async_creation": True,
                    "order_no": order_no,
                    "error": "eSIM is still being created"
                }
            
            # Иначе возвращаем ошибку
            return {
                "success": False,
                "error": status_result.get("error", "Unknown error"),
                "order_no": order_no
            }
            
    async def get_countries(self, session: AsyncSession) -> List[Dict]:
        """
        Получает список стран из базы данных
        
        Args:
            session: Сессия базы данных
            
        Returns:
            List[Dict]: Список стран
        """
        try:
            # Получаем список стран из базы данных
            countries = await get_all_countries(session)
            
            # Преобразуем список стран в список словарей
            countries_list = []
            for country in countries:
                # Добавляем эмодзи флага
                flag_emoji = self._create_flag_emoji(country.code)
                
                # Формируем словарь с информацией о стране
                country_info = {
                    "id": country.id,
                    "code": country.code,
                    "name": country.name,
                    "flag_emoji": flag_emoji,
                    "has_packages": bool(country.packages_count > 0)
                }
                
                countries_list.append(country_info)
                
            return countries_list
        except Exception as e:
            self.logger.exception(f"❌ Ошибка при получении списка стран: {e}")
            return []
            
    async def get_packages(self, session: AsyncSession, country_code: str) -> List[Dict]:
        """
        Получает список пакетов для указанной страны из базы данных
        
        Args:
            session: Сессия базы данных
            country_code: Код страны
            
        Returns:
            List[Dict]: Список пакетов
        """
        try:
            # Получаем страну из базы данных
            country = await get_country_by_code(session, country_code)
            if not country:
                self.logger.error(f"❌ Страна с кодом {country_code} не найдена")
                return []
                
            # Получаем список пакетов для страны из базы данных
            packages = await get_packages_by_country(session, country.id)
            
            # Преобразуем список пакетов в список словарей
            packages_list = []
            for package in packages:
                # Форматируем информацию о пакете
                package_info = {
                    "id": package.id,
                    "code": package.code,
                    "name": package.name,
                    "description": package.description,
                    "country_code": country_code,
                    "country_name": country.name,
                    "data_volume_gb": package.data_volume_gb,
                    "duration_days": package.duration_days,
                    "price_usd": package.price_usd,
                    "is_popular": package.is_popular,
                    "is_unlimited": package.is_unlimited
                }
                
                packages_list.append(package_info)
                
            return packages_list
        except Exception as e:
            self.logger.exception(f"❌ Ошибка при получении списка пакетов для страны {country_code}: {e}")
            return []
            
    async def get_package(self, session: AsyncSession, package_code: str) -> Optional[Dict]:
        """
        Получает информацию о пакете по его коду из базы данных
        
        Args:
            session: Сессия базы данных
            package_code: Код пакета
            
        Returns:
            Optional[Dict]: Информация о пакете или None, если пакет не найден
        """
        try:
            # Получаем пакет из базы данных
            package = await get_package_by_code(session, package_code)
            if not package:
                self.logger.error(f"❌ Пакет с кодом {package_code} не найден")
                return None
                
            # Получаем страну из базы данных
            country = await get_country_by_code(session, package.country_code)
            if not country:
                self.logger.error(f"❌ Страна с кодом {package.country_code} не найдена")
                return None
                
            # Форматируем информацию о пакете
            package_info = {
                "id": package.id,
                "code": package.code,
                "name": package.name,
                "description": package.description,
                "country_code": package.country_code,
                "country_name": country.name,
                "data_volume_gb": package.data_volume_gb,
                "duration_days": package.duration_days,
                "price_usd": package.price_usd,
                "is_popular": package.is_popular,
                "is_unlimited": package.is_unlimited
            }
            
            return package_info
        except Exception as e:
            self.logger.exception(f"❌ Ошибка при получении информации о пакете {package_code}: {e}")
            return None
            
    async def sync_countries(self, session: AsyncSession) -> Dict:
        """
        Синхронизирует список стран с API
        
        Args:
            session: Сессия базы данных
            
        Returns:
            Dict: Результат синхронизации
        """
        self.logger.info("Синхронизация списка стран с API")
        
        try:
            # Поскольку API не предоставляет прямой эндпоинт для стран,
            # получаем список всех пакетов и извлекаем из них список стран
            request_data = {}  # Запрос без параметров для получения всех пакетов
            response = await self._make_request("POST", "open/package/list", json_data=request_data)
            
            # Обрабатываем ошибку API
            error_response = await self._handle_api_error(response, "sync countries")
            if error_response:
                return error_response
            
            # Извлекаем данные пакетов из ответа с учетом разных структур ответа
            packages_data = []
            
            # Проверяем разные варианты структуры ответа
            if "obj" in response and isinstance(response["obj"], list):
                packages_data = response["obj"]
            elif "obj" in response and isinstance(response["obj"], dict) and "packageList" in response["obj"]:
                if isinstance(response["obj"]["packageList"], list):
                    packages_data = response["obj"]["packageList"]
            elif "data" in response and isinstance(response["data"], list):
                packages_data = response["data"]
            elif "list" in response and isinstance(response["list"], list):
                packages_data = response["list"]
            elif "result" in response and isinstance(response["result"], dict) and "list" in response["result"]:
                if isinstance(response["result"]["list"], list):
                    packages_data = response["result"]["list"]
            
            if not packages_data:
                self.logger.error("❌ Не удалось получить данные пакетов для извлечения стран")
                return {
                    "success": False,
                    "error": "No packages data available"
                }
            
            # Извлекаем уникальные коды стран из пакетов
            countries_data = []
            country_codes = set()
            
            for package in packages_data:
                location = package.get("location", "")
                if location and len(location) == 2 and location not in ["!GL", "!RG"]:
                    # Если это код страны (2 символа) и не глобальный/региональный пакет
                    if location not in country_codes:
                        country_codes.add(location)
                        country_name = self._get_country_name(location)
                        countries_data.append({
                            "code": location,
                            "name": country_name,
                            "flagEmoji": self._get_country_flag(location)
                        })
            
            # Проверяем, есть ли необходимые данные
            if not countries_data:
                self.logger.error(f"❌ API вернул пустой список стран")
                return {
                    "success": False,
                    "error": "No countries data found",
                    "api_response": response
                }
                
            # Обрабатываем список стран
            countries_count = 0
            for country_data in countries_data:
                country_code = country_data.get("code", "")
                country_name = country_data.get("name", "")
                
                if not country_code or not country_name:
                    self.logger.warning(f"Пропуск страны без кода или имени: {country_data}")
                    continue
                    
                # Проверяем, существует ли страна в базе данных
                country = await get_country_by_code(session, country_code)
                
                if country:
                    # Обновляем существующую странуcountry.flag_emoji = self._get_country_flag(country_code)
                    country.name = country_name
                    country.flag_emoji = self._get_country_flag(country_code)
                    self.logger.info(f"Обновлена страна: {country_code} - {country_name} с флагом {country.flag_emoji}")
                else:
                    # Создаем новую страну
                    country = Country(
                        code=country_code,
                        name=country_name,
                        flag_emoji=self._get_country_flag(country_code)
                    )
                    session.add(country)
                    self.logger.info(f"Добавлена новая страна: {country_code} - {country_name} с флагом {country.flag_emoji}")
                    
                countries_count += 1
                
            # Сохраняем изменения в базе данных
            await session.commit()
            
            self.logger.info(f"✅ Синхронизация стран завершена. Обработано {countries_count} стран.")
            
            return {
                "success": True,
                "countries_count": countries_count
            }
        except Exception as e:
            self.logger.exception(f"❌ Ошибка при синхронизации стран: {e}")
            return {
                "success": False,
                "error": str(e)
            }
            
    async def sync_packages(self, session: AsyncSession, country_code: str) -> Dict:
        """
        Синхронизирует все пакеты для указанной страны.
        
        Args:
            session: Сессия для работы с БД
            country_code: Код страны (двухбуквенный ISO)
            
        Returns:
            Словарь с результатами синхронизации
        """
        try:
            self.logger.info(f"Начинаем синхронизацию пакетов для страны {country_code}")
            
            # Получаем страну из БД
            country = await get_country_by_code(session, country_code)
            if not country:
                self.logger.error(f"❌ Страна с кодом {country_code} не найдена в БД")
                return {
                    "success": False,
                    "error": f"Country {country_code} not found in database"
                }
            
            self.logger.info(f"Найдена страна {country.name} (ID: {country.id})")
            
            # Пробуем разные форматы API-запросов
            api_tries = []
            
            try:
                # ПОПЫТКА 1: Только с кодом страны
                self.logger.info("=== ПОПЫТКА 1: Только с кодом страны ===")
                request_data_1 = {
                    "locationCode": country_code
                }
                self.logger.info(f"Отправка запроса с данными: {json.dumps(request_data_1)}")
                response_1 = await self._make_request("POST", "open/package/list", json_data=request_data_1, content_type="text/plain")
                self.logger.info(f"Ответ на запрос 1: {json.dumps(response_1, ensure_ascii=False)}")
                api_tries.append({"data": request_data_1, "response": response_1})
                
                # ПОПЫТКА 2: С полем type=BASE
                self.logger.info("=== ПОПЫТКА 2: С полем type=BASE ===")
                request_data_2 = {
                    "locationCode": country_code,
                    "type": "BASE"
                }
                self.logger.info(f"Отправка запроса с данными: {json.dumps(request_data_2)}")
                response_2 = await self._make_request("POST", "open/package/list", json_data=request_data_2, content_type="text/plain")
                self.logger.info(f"Ответ на запрос 2: {json.dumps(response_2, ensure_ascii=False)}")
                api_tries.append({"data": request_data_2, "response": response_2})
                
                # ПОПЫТКА 3: Все поля согласно документации
                self.logger.info("=== ПОПЫТКА 3: Все поля согласно документации ===")
                request_data_3 = {
                    "locationCode": country_code,
                    "type": "BASE",
                    "packageCode": "",
                    "iccid": ""
                }
                self.logger.info(f"Отправка запроса с данными: {json.dumps(request_data_3)}")
                response_3 = await self._make_request("POST", "open/package/list", json_data=request_data_3, content_type="text/plain")
                self.logger.info(f"Ответ на запрос 3: {json.dumps(response_3, ensure_ascii=False)}")
                api_tries.append({"data": request_data_3, "response": response_3})
                
                # ВАЖНО: Запрос с TOPUP удален, так как он вызывает ошибку 200057
                
                # Выбираем лучший ответ из всех попыток
                best_response = None
                best_data = None
                
                for try_data in api_tries:
                    current_response = try_data["response"]
                    request_data = try_data["data"]
                    
                    # Проверяем наличие данных в ответе
                    has_data = False
                    
                    if "obj" in current_response and isinstance(current_response["obj"], list) and len(current_response["obj"]) > 0:
                        has_data = True
                    elif "obj" in current_response and isinstance(current_response["obj"], dict) and "packageList" in current_response["obj"]:
                        # Новая структура ответа - пакеты находятся внутри obj.packageList
                        if isinstance(current_response["obj"]["packageList"], list):
                            has_data = True
                    elif "data" in current_response and isinstance(current_response["data"], list) and len(current_response["data"]) > 0:
                        has_data = True
                    elif "list" in current_response and isinstance(current_response["list"], list) and len(current_response["list"]) > 0:
                        has_data = True
                    elif "result" in current_response and isinstance(current_response["result"], dict) and "list" in current_response["result"]:
                        if isinstance(current_response["result"]["list"], list) and len(current_response["result"]["list"]) > 0:
                            has_data = True
                    
                    if has_data and not best_response:
                        best_response = current_response
                        best_data = request_data
                
                # Если найден ответ с данными, используем его
                if best_response:
                    self.logger.info(f"Найден успешный запрос с данными! Формат запроса: {json.dumps(best_data)}")
                    response = best_response
                else:
                    # Используем документированный ответ, если ни один не содержит данных
                    self.logger.warning("Ни один из запросов не вернул данные. Используем ответ с BASE параметром.")
                    response = response_3  # Используем ответ на документированный запрос
            except Exception as e:
                self.logger.exception(f"Исключение при запросе к API: {str(e)}")
                return {
                    "success": False,
                    "error": f"API request error: {str(e)}"
                }
                
            # Обрабатываем ошибку API
            error_response = await self._handle_api_error(response, "sync packages")
            if error_response:
                return error_response
            
            # Извлекаем данные пакетов из ответа с учетом разных структур ответа
            packages_data = []
            if "obj" in response and isinstance(response["obj"], list):
                packages_data = response["obj"]
            elif "obj" in response and isinstance(response["obj"], dict) and "packageList" in response["obj"]:
                # Новая структура ответа - пакеты находятся внутри obj.packageList
                if isinstance(response["obj"]["packageList"], list):
                    packages_data = response["obj"]["packageList"]
                    self.logger.info(f"Найдено {len(packages_data)} пакетов в структуре obj.packageList")
            elif "data" in response and isinstance(response["data"], list):
                packages_data = response["data"]
            elif "list" in response and isinstance(response["list"], list):
                packages_data = response["list"]
            elif "result" in response and isinstance(response["result"], dict) and "list" in response["result"]:
                if isinstance(response["result"]["list"], list):
                    packages_data = response["result"]["list"]
            
            # Проверяем, есть ли необходимые данные
            if not packages_data:
                self.logger.error(f"❌ API вернул пустой список пакетов для страны {country_code}")
                return {
                    "success": False,
                    "error": "No packages data found",
                    "api_response": response
                }
                
            # ВАЖНО: Фильтруем пакеты, оставляя только относящиеся к этой стране
            # (исключаем глобальные и региональные)
            country_specific_packages = []
            global_packages = []
            regional_packages = []
            
            for package in packages_data:
                # Логируем каждый пакет, чтобы видеть, что мы получаем
                self.logger.info(f"Анализ пакета: {json.dumps(package, ensure_ascii=False)}")
                
                # Проверяем признаки пакета
                package_code = package.get("packageCode", "") or package.get("slug", "")
                package_name = package.get("name", "")
                
                # Логируем важные поля пакета для анализа
                self.logger.info(f"Код пакета: {package_code}, Название: {package_name}, Location: {package.get('location', '')}")
                
                # ПРОСТАЯ ЛОГИКА: Пакет относится к стране, только если location точно равен коду страны
                if package.get("location", "") == country_code:
                    country_specific_packages.append(package)
                    self.logger.info(f"Пакет {package_code} добавлен как СТРАНОВОЙ для {country_code}")
                # Глобальные пакеты (содержат список стран через запятую) - ПРОПУСКАЕМ ВСЕ
                elif "," in str(package.get("location", "")):
                    # Пропускаем все глобальные пакеты
                    global_packages.append(package)
                    self.logger.info(f"Пакет {package_code} пропущен как ГЛОБАЛЬНЫЙ (location содержит список стран)")
                # Другие пакеты (региональные) также пропускаем
                else:
                    regional_packages.append(package)
                    self.logger.info(f"Пакет {package_code} пропущен как РЕГИОНАЛЬНЫЙ для {package.get('location', '')} (не совпадает с {country_code})")
            
            # Логируем результаты фильтрации
            self.logger.info(f"Всего получено пакетов: {len(packages_data)}")
            self.logger.info(f"Отфильтровано страновых пакетов: {len(country_specific_packages)}")
            self.logger.info(f"Отфильтровано глобальных пакетов: {len(global_packages)}")
            self.logger.info(f"Отфильтровано региональных пакетов: {len(regional_packages)}")
            
            # Используем только страновые пакеты для обновления БД
            filtered_packages = country_specific_packages
            
            # Если нет страновых пакетов после фильтрации, возвращаем ошибку
            if not filtered_packages:
                self.logger.error(f"❌ После фильтрации не найдено страновых пакетов для {country_code}")
                return {
                    "success": False,
                    "error": "No country-specific packages found after filtering"
                }
            
            # ВАЖНО: Вместо удаления всех пакетов (что вызывает ошибку внешнего ключа),
            # получаем существующие пакеты и обновляем их или помечаем как архивные
            from sqlalchemy import select
            existing_packages_query = await session.execute(
                select(Package).where(Package.country_id == country.id)
            )
            existing_packages = {pkg.package_code: pkg for pkg in existing_packages_query.scalars().all()}
            
            # Обрабатываем список пакетов
            packages_count = 0
            
            for package in filtered_packages:
                package_code = package.get("packageCode", "") or package.get("slug", "")
                package_name = package.get("name", "")
                
                # Проверяем наличие необходимых данных
                if not package_code or not package_name:
                    self.logger.warning(f"Пропуск пакета без кода или имени: {package}")
                    continue
                
                # Добавляем префикс страны к коду пакета, чтобы он был уникальным
                # (Одинаковые коды могут использоваться для разных стран)
                unique_package_code = f"{country_code}_{package_code}"
                
                # Получаем информацию о пакете
                data_volume = package.get("volume", 0)
                duration = package.get("duration", 0)
                price = package.get("price", 0)
                retail_price = package.get("retailPrice", 0)  # Получаем рекомендуемую розничную цену
                
                # Конвертируем объем данных в ГБ
                data_volume_gb = self._convert_to_gb(data_volume)
                
                # Конвертируем цены в USD
                price_usd = self._convert_price(price, package_code, package)
                retail_price_usd = self._convert_price(retail_price, package_code, package)  # Конвертируем розничную цену
                
                # Проверяем, существует ли такой пакет уже
                if unique_package_code in existing_packages:
                    # Обновляем существующий пакет
                    existing_pkg = existing_packages[unique_package_code]
                    existing_pkg.name = package_name
                    existing_pkg.data_amount = data_volume_gb
                    existing_pkg.duration = duration
                    existing_pkg.price = price_usd
                    existing_pkg.retail_price = retail_price_usd  # Обновляем розничную цену
                    existing_pkg.last_synced_at = datetime.now()  # Обновляем время синхронизации
                    # Проверяем, есть ли поле is_archived в модели
                    if hasattr(existing_pkg, 'is_archived'):
                        existing_pkg.is_archived = False  # Помечаем как актуальный
                    
                    # Если есть описание, обновляем его
                    if "description" in package:
                        existing_pkg.description = package["description"]
                
                    self.logger.info(f"Обновлен пакет: {unique_package_code} - {package_name}")
                    
                    # Удаляем из словаря, чтобы потом пометить оставшиеся как архивные
                    del existing_packages[unique_package_code]
                else:
                    # Создаем новый пакет
                    new_package = Package(
                        package_code=unique_package_code,
                        name=package_name,
                        country_id=country.id,
                        data_amount=data_volume_gb,
                        duration=duration,
                        price=price_usd,
                        retail_price=retail_price_usd,  # Устанавливаем розничную цену
                        last_synced_at=datetime.now()  # Устанавливаем время синхронизации
                    )
                    
                    # Если в модели есть поле is_archived, устанавливаем его в False
                    if hasattr(Package, 'is_archived'):
                        new_package.is_archived = False
                    
                    # Добавляем дополнительные поля, если они есть в ответе API
                    if "description" in package:
                        new_package.description = package["description"]
                        
                    session.add(new_package)
                    self.logger.info(f"Добавлен новый пакет: {unique_package_code} - {package_name}")
                
                packages_count += 1
            
            # Помечаем оставшиеся пакеты как архивные, если поле is_archived существует
            for code, old_package in existing_packages.items():
                if hasattr(old_package, 'is_archived'):
                    old_package.is_archived = True
                    self.logger.info(f"Пакет {code} помечен как архивный")
            
            # НЕ делаем commit здесь, он выполняется в вызывающем коде после обработки каждой страны
            # await session.commit() - УДАЛЯЕМ ЭТУ СТРОКУ!
            
            self.logger.info(f"✅ Успешно синхронизировано {packages_count} пакетов для страны {country_code}")
            return {
                "success": True,
                "message": f"Successfully synced {packages_count} packages for country {country_code}",
                "packages_count": packages_count
            }
                
        except Exception as e:
            self.logger.exception(f"❌ Ошибка при синхронизации пакетов: {str(e)}")
            try:
                await session.rollback()
            except:
                pass
            return {
                "success": False,
                "error": f"Error syncing packages: {str(e)}"
            }
    
    async def get_available_package_codes(self, country_code: str) -> Dict[str, Any]:
        """
        Получает список доступных пакетов для указанной страны из API.
        
        Args:
            country_code: Код страны (например, 'SI' для Словении)
            
        Returns:
            Словарь с кодами пакетов и их данными
        """
        self.logger.info(f"Получение доступных пакетов для страны {country_code} из API")
        
        try:
            # Формируем запрос согласно документации API
            request_data = {
                "locationCode": country_code,
                "type": "",  # Запрашиваем все типы пакетов
                "packageCode": "",
                "iccid": ""
            }
            
            # Выполняем запрос к API
            response = await self._make_request("POST", "open/package/list", json_data=request_data)
            
            # Обрабатываем ошибку API
            error_response = await self._handle_api_error(response, "get available packages")
            if error_response:
                return {}
            
            # Извлекаем данные пакетов из ответа
            packages_data = response.get("obj", [])
            
            if not packages_data:
                self.logger.warning(f"⚠️ API вернул пустой список пакетов для страны {country_code}")
                return {}
            
            # Преобразуем данные в словарь, где ключ - код пакета
            packages = {}
            for package in packages_data:
                if isinstance(package, dict):
                    # Проверяем наличие packageCode или slug
                    package_code = package.get("packageCode") or package.get("slug")
                    if package_code:
                        packages[package_code] = package
            
            self.logger.info(f"✅ Получено {len(packages)} пакетов для страны {country_code}")
            return packages
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка при получении пакетов для страны {country_code}: {str(e)}")
            return {}
    
    async def get_all_available_packages(self) -> Dict[str, Any]:
        """
        Получает список всех доступных пакетов из API.
        
        Returns:
            Словарь с кодами пакетов и их данными
        """
        self.logger.info("Получение всех доступных пакетов из API")
        
        try:
            # Получаем все типы пакетов
            packages = {}
            
            # 1. Получаем глобальные пакеты
            # global_packages = await self._get_packages_by_location("!GL")
            # if global_packages:
            #     packages.update(global_packages)
            #     self.logger.info(f"✅ Получено {len(global_packages)} глобальных пакетов")
            
            # 2. Получаем региональные пакеты
            # regional_packages = await self._get_packages_by_location("!RG")
            # if regional_packages:
            #     packages.update(regional_packages)
            #     self.logger.info(f"✅ Получено {len(regional_packages)} региональных пакетов")
            
            # 3. Получаем пакеты для конкретных стран
            common_countries = ["SI", "HR", "IT", "FR", "DE", "ES", "GB", "US", "JP"]
            for country in common_countries:
                country_packages = await self.get_available_package_codes(country)
                if country_packages:
                    packages.update(country_packages)
                    self.logger.info(f"✅ Получено {len(country_packages)} пакетов для страны {country}")
            
            if packages:
                self.logger.info(f"✅ Всего получено {len(packages)} пакетов")
                return packages
            
            self.logger.warning("⚠️ Не удалось получить список пакетов")
            return {}
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка при получении всех пакетов: {str(e)}")
            return {}
    
    async def _get_packages_by_location(self, location_code: str) -> Dict[str, Any]:
        """
        Вспомогательный метод для получения пакетов по коду локации.
        
        Args:
            location_code: Код локации (страны или региона)
            
        Returns:
            Словарь с кодами пакетов и их данными
        """
        try:
            # Формируем запрос согласно документации API
            request_data = {
                "locationCode": location_code,
                "type": "",  # Запрашиваем все типы пакетов
                "packageCode": "",
                "iccid": ""
            }
            
            # Выполняем запрос к API
            response = await self._make_request("POST", "open/package/list", json_data=request_data)
            
            # Обрабатываем ошибку API
            error_response = await self._handle_api_error(response, "get packages by location")
            if error_response:
                return {}
            
            # Извлекаем данные пакетов из ответа
            packages_data = response.get("obj", [])
            
            if not packages_data:
                return {}
            
            # Преобразуем данные в словарь, где ключ - код пакета
            packages = {}
            for package in packages_data:
                if isinstance(package, dict):
                    # Проверяем наличие packageCode или slug
                    package_code = package.get("packageCode") or package.get("slug")
                    if package_code:
                        packages[package_code] = package
            
            return packages
            
        except Exception:
            return {}
    
    async def sync_packages_with_api(self, session: AsyncSession, country_code: Optional[str] = None) -> Dict:
        """
        Синхронизирует пакеты с API для всех стран или для указанной страны
        
        Args:
            session: Сессия базы данных
            country_code: Код страны (опционально)
            
        Returns:
            Dict: Результат синхронизации
        """
        self.logger.info(f"Синхронизация пакетов с API {f'для страны {country_code}' if country_code else 'для всех стран'}")
        
        try:
            if country_code:
                # Синхронизируем пакеты только для указанной страны
                result = await self.sync_packages(session, country_code)
                return result
            else:
                # Получаем список всех стран из базы данных
                countries = await get_all_countries(session)
                
                # Синхронизируем пакеты для каждой страны
                total_packages = 0
                success_count = 0
                failed_count = 0
                
                for country in countries:
                    try:
                        result = await self.sync_packages(session, country.code)
                        
                        if result.get("success"):
                            total_packages += result.get("packages_count", 0)
                            success_count += 1
                        else:
                            failed_count += 1
                    except Exception as e:
                        self.logger.exception(f"❌ Ошибка при синхронизации пакетов для страны {country.code}: {e}")
                        failed_count += 1
                
                self.logger.info(f"✅ Синхронизация пакетов завершена. Успешно: {success_count}, Ошибок: {failed_count}, Всего пакетов: {total_packages}")
                
                return {
                    "success": True,
                    "total_packages": total_packages,
                    "success_count": success_count,
                    "failed_count": failed_count
                }
        except Exception as e:
            self.logger.exception(f"❌ Ошибка при синхронизации пакетов с API: {e}")
            return {
                "success": False,
                "error": str(e)
            }
            
    async def sync_countries_and_packages(self, session: AsyncSession, sync_packages: bool = True) -> bool:
        """
        Синхронизирует список стран и пакетов с API
        
        Args:
            session: Сессия базы данных
            sync_packages: Флаг, указывающий, нужно ли синхронизировать пакеты
            
        Returns:
            bool: Результат синхронизации
        """
        self.logger.info(f"Синхронизация стран и пакетов с API (sync_packages={sync_packages})")
        
        try:
            # Синхронизируем список стран
            countries_result = await self.sync_countries(session)
            
            if not countries_result.get("success"):
                self.logger.error(f"❌ Ошибка при синхронизации стран: {countries_result.get('error')}")
                return False
                
            # Если нужно, синхронизируем пакеты для всех стран
            if sync_packages:
                packages_result = await self.sync_packages_with_api(session)
                
                if not packages_result.get("success"):
                    self.logger.error(f"❌ Ошибка при синхронизации пакетов: {packages_result.get('error')}")
                    return False
            
            self.logger.info(f"✅ Синхронизация стран и пакетов успешно завершена")
            
            return True
        except Exception as e:
            self.logger.exception(f"❌ Ошибка при синхронизации стран и пакетов: {e}")
            return False
            
    async def sync_packages_for_country(self, session: AsyncSession, country: Any) -> bool:
        """
        Синхронизирует пакеты для указанной страны
        
        Args:
            session: Сессия базы данных
            country: Объект страны
            
        Returns:
            bool: Результат синхронизации
        """
        self.logger.info(f"Синхронизация пакетов для страны {country.code} - {country.name}")
        
        try:
            # Синхронизируем пакеты для страны
            result = await self.sync_packages(session, country.code)
            
            if not result.get("success"):
                self.logger.error(f"❌ Ошибка при синхронизации пакетов для страны {country.code}: {result.get('error')}")
                return False
                
            self.logger.info(f"✅ Синхронизация пакетов для страны {country.code} успешно завершена. Обработано {result.get('packages_count')} пакетов.")
            
            return True
        except Exception as e:
            self.logger.exception(f"❌ Ошибка при синхронизации пакетов для страны {country.code}: {e}")
            return False

    async def topup_esim(self, iccid: str, package_code: str, transaction_id: str = "") -> Dict:
        """
        Пополняет трафик для существующей eSIM через API провайдера
        
        Args:
            iccid: ICCID eSIM
            package_code: Код пакета (например, SI-0.3GB-1D)
            transaction_id: ID транзакции (опционально)
            
        Returns:
            Dict: Результат пополнения трафика
        """
        self.logger.info(f"Пополнение трафика для eSIM с ICCID: {iccid}, код пакета: {package_code}")
        
        # Проверяем баланс аккаунта перед операцией
        if not await self.check_balance_before_operation("topup eSIM"):
            self.logger.error(f"❌ Недостаточный баланс для пополнения трафика eSIM с ICCID: {iccid}")
            return {
                "success": False,
                "error": "Недостаточный баланс аккаунта для пополнения трафика"
            }
        
        # Получаем только суффикс кода пакета (последнюю часть)
        # Например, из "SI-0.3GB-1D-P82Y6VYRL" получаем "P82Y6VYRL"
        modified_package_code = package_code
        if "-" in package_code:
            package_code_parts = package_code.split("-")
            if len(package_code_parts) > 1:
                modified_package_code = package_code_parts[-1]
                self.logger.info(f"Используем модифицированный код пакета: {modified_package_code}")
        
        # Если transaction_id не указан, генерируем его
        if not transaction_id:
            transaction_id = f"topup-{uuid.uuid4().hex}"
        
        # Формируем данные для запроса
        data = {
            "transactionId": transaction_id,
            "iccid": iccid,
            "packageCode": modified_package_code
        }
        
        self.logger.info(f"Отправляем запрос на пополнение трафика с данными: {json.dumps(data, indent=2)}")
        
        try:
            # Отправляем запрос на пополнение трафика
            # Используем эндпоинт для пополнения трафика
            response = await self._make_request("POST", "open/esim/topup", json_data=data)
            self.logger.info(f"Получен ответ от API при пополнении трафика: {json.dumps(response, indent=2)}")
            
            # Обрабатываем ошибку API
            error_response = await self._handle_api_error(response, "topup eSIM")
            if error_response:
                return error_response
            
            # Проверяем успешность запроса
            if "code" in response and response["code"] == "0":
                self.logger.info(f"Успешно инициировано пополнение трафика для eSIM с ICCID: {iccid}")
                return response.get("data", {})
            else:
                error_msg = response.get("message", "Неизвестная ошибка")
                self.logger.error(f"Ошибка при пополнении трафика: {error_msg}")
                raise Exception(f"Ошибка при пополнении трафика: {error_msg}")
                
        except Exception as e:
            self.logger.error(f"Исключение при пополнении трафика: {str(e)}")
            raise

    async def cancel_esim(self, iccid: str, transaction_id: str = "") -> Dict:
        """
        Отменяет профиль eSIM
        
        Args:
            iccid: ICCID eSIM
            transaction_id: ID транзакции (опционально)
            
        Returns:
            Dict: Результат отмены профиля
        """
        self.logger.info(f"Отмена профиля eSIM с ICCID: {iccid}")
        
        # Если transaction_id не указан, генерируем его
        if not transaction_id:
            transaction_id = f"cancel-{uuid.uuid4().hex}"
        
        # Формируем данные для запроса
        data = {
            "transactionId": transaction_id,
            "iccid": iccid
        }
        
        self.logger.info(f"Отправляем запрос на отмену профиля с данными: {json.dumps(data, indent=2)}")
        
        try:
            # Проверяем баланс перед отменой профиля
            if not await self.check_balance_before_operation("cancel eSIM"):
                self.logger.error(f"❌ Недостаточный баланс для отмены профиля eSIM с ICCID: {iccid}")
                return {
                    "success": False,
                    "error": "Insufficient balance"
                }
            
            # Отправляем запрос на отмену профиля
            response = await self._make_request("POST", "open/esim/cancel", json_data=data)
            self.logger.info(f"Получен ответ от API при отмене профиля: {json.dumps(response, indent=2)}")
            
            # Обрабатываем ошибку API
            error_response = await self._handle_api_error(response, "cancel eSIM")
            if error_response:
                return error_response
            
            # Формируем результат
            return {
                "success": True,
                "iccid": iccid,
                "api_response": response
            }
                
        except Exception as e:
            self.logger.error(f"Исключение при отмене профиля: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def suspend_esim(self, iccid: str, transaction_id: str = "") -> Dict:
        """
        Приостанавливает профиль eSIM
        
        Args:
            iccid: ICCID eSIM
            transaction_id: ID транзакции (опционально)
            
        Returns:
            Dict: Результат приостановки профиля
        """
        self.logger.info(f"Приостановка профиля eSIM с ICCID: {iccid}")
        
        # Если transaction_id не указан, генерируем его
        if not transaction_id:
            transaction_id = f"suspend-{uuid.uuid4().hex}"
        
        # Формируем данные для запроса
        data = {
            "transactionId": transaction_id,
            "iccid": iccid
        }
        
        self.logger.info(f"Отправляем запрос на приостановку профиля с данными: {json.dumps(data, indent=2)}")
        
        try:
            # Проверяем баланс перед приостановкой профиля
            if not await self.check_balance_before_operation("suspend eSIM"):
                self.logger.error(f"❌ Недостаточный баланс для приостановки профиля eSIM с ICCID: {iccid}")
                return {
                    "success": False,
                    "error": "Insufficient balance"
                }
            
            # Отправляем запрос на приостановку профиля
            response = await self._make_request("POST", "open/esim/suspend", json_data=data)
            self.logger.info(f"Получен ответ от API при приостановке профиля: {json.dumps(response, indent=2)}")
            
            # Обрабатываем ошибку API
            error_response = await self._handle_api_error(response, "suspend eSIM")
            if error_response:
                return error_response
            
            # Формируем результат
            return {
                "success": True,
                "iccid": iccid,
                "api_response": response
            }
                
        except Exception as e:
            self.logger.error(f"Исключение при приостановке профиля: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def unsuspend_esim(self, iccid: str, transaction_id: str = "") -> Dict:
        """
        Возобновляет профиль eSIM
        
        Args:
            iccid: ICCID eSIM
            transaction_id: ID транзакции (опционально)
            
        Returns:
            Dict: Результат возобновления профиля
        """
        self.logger.info(f"Возобновление профиля eSIM с ICCID: {iccid}")
        
        # Если transaction_id не указан, генерируем его
        if not transaction_id:
            transaction_id = f"unsuspend-{uuid.uuid4().hex}"
        
        # Формируем данные для запроса
        data = {
            "transactionId": transaction_id,
            "iccid": iccid
        }
        
        self.logger.info(f"Отправляем запрос на возобновление профиля с данными: {json.dumps(data, indent=2)}")
        
        try:
            # Проверяем баланс перед возобновлением профиля
            if not await self.check_balance_before_operation("unsuspend eSIM"):
                self.logger.error(f"❌ Недостаточный баланс для возобновления профиля eSIM с ICCID: {iccid}")
                return {
                    "success": False,
                    "error": "Insufficient balance"
                }
            
            # Отправляем запрос на возобновление профиля
            response = await self._make_request("POST", "open/esim/unsuspend", json_data=data)
            self.logger.info(f"Получен ответ от API при возобновлении профиля: {json.dumps(response, indent=2)}")
            
            # Обрабатываем ошибку API
            error_response = await self._handle_api_error(response, "unsuspend eSIM")
            if error_response:
                return error_response
            
            # Формируем результат
            return {
                "success": True,
                "iccid": iccid,
                "api_response": response
            }
                
        except Exception as e:
            self.logger.error(f"Исключение при возобновлении профиля: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def send_sms(self, iccid: str, message: str, transaction_id: str = "") -> Dict:
        """
        Отправляет SMS на eSIM
        
        Args:
            iccid: ICCID eSIM
            message: Текст сообщения
            transaction_id: ID транзакции (опционально)
            
        Returns:
            Dict: Результат отправки SMS
        """
        self.logger.info(f"Отправка SMS на eSIM с ICCID: {iccid}")
        
        # Если transaction_id не указан, генерируем его
        if not transaction_id:
            transaction_id = f"sms-{uuid.uuid4().hex}"
        
        # Формируем данные для запроса
        data = {
            "transactionId": transaction_id,
            "iccid": iccid,
            "content": message
        }
        
        self.logger.info(f"Отправляем запрос на отправку SMS с данными: {json.dumps(data, indent=2)}")
        
        try:
            # Проверяем баланс перед отправкой SMS
            if not await self.check_balance_before_operation("send SMS"):
                self.logger.error(f"❌ Недостаточный баланс для отправки SMS на eSIM с ICCID: {iccid}")
                return {
                    "success": False,
                    "error": "Insufficient balance"
                }
            
            # Отправляем запрос на отправку SMS
            response = await self._make_request("POST", "open/esim/sendSms", json_data=data)
            self.logger.info(f"Получен ответ от API при отправке SMS: {json.dumps(response, indent=2)}")
            
            # Обрабатываем ошибку API
            error_response = await self._handle_api_error(response, "send SMS")
            if error_response:
                return error_response
            
            # Формируем результат
            return {
                "success": True,
                "iccid": iccid,
                "api_response": response
            }
                
        except Exception as e:
            self.logger.error(f"Исключение при отправке SMS: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def save_webhook(self, webhook_url: str, events: List[str] = None, transaction_id: str = "") -> Dict:
        """
        Сохраняет URL для webhook-уведомлений
        
        Args:
            webhook_url: URL для отправки webhook-уведомлений
            events: Список событий для уведомления (опционально)
            transaction_id: ID транзакции (опционально)
            
        Returns:
            Dict: Результат сохранения webhook
        """
        self.logger.info(f"Сохранение webhook URL: {webhook_url}")
        
        # Проверяем баланс аккаунта перед операцией
        if not await self.check_balance_before_operation("save webhook"):
            self.logger.error(f"❌ Недостаточный баланс для сохранения webhook URL: {webhook_url}")
            return {
                "success": False,
                "error": "Недостаточный баланс аккаунта для сохранения webhook"
            }
        
        # Если transaction_id не указан, генерируем его
        if not transaction_id:
            transaction_id = f"webhook-{uuid.uuid4().hex}"
        
        # Если список событий не указан, используем все доступные события
        if not events:
            events = ["ORDER_STATUS_CHANGE", "ESIM_STATUS_CHANGE", "PACKAGE_STATUS_CHANGE"]
        
        # Формируем данные для запроса
        data = {
            "transactionId": transaction_id,
            "url": webhook_url,
            "events": events
        }
        
        self.logger.info(f"Отправляем запрос на сохранение webhook с данными: {json.dumps(data, indent=2)}")
        
        try:
            # Отправляем запрос на сохранение webhook
            response = await self._make_request("POST", "open/webhook/save", json_data=data)
            self.logger.info(f"Получен ответ от API при сохранении webhook: {json.dumps(response, indent=2)}")
            
            # Обрабатываем ошибку API
            error_response = await self._handle_api_error(response, "save webhook")
            if error_response:
                return error_response
            
            # Формируем результат
            return {
                "success": True,
                "webhook_url": webhook_url,
                "events": events,
                "api_response": response
            }
                
        except Exception as e:
            self.logger.error(f"Исключение при сохранении webhook: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def query_balance(self, transaction_id: str = "") -> Dict:
        """
        Запрашивает текущий баланс аккаунта
        
        Args:
            transaction_id: ID транзакции (опционально)
            
        Returns:
            Dict: Информация о балансе
        """
        self.logger.info(f"Запрос баланса аккаунта")
        
        # Если transaction_id не указан, генерируем его
        if not transaction_id:
            transaction_id = f"balance-{uuid.uuid4().hex}"
        
        # Формируем данные для запроса
        data = {
            "transactionId": transaction_id
        }
        
        self.logger.info(f"Отправляем запрос на получение баланса с данными: {json.dumps(data, indent=2)}")
        
        try:
            # Отправляем запрос на получение баланса
            response = await self._make_request("POST", "open/balance/query", json_data=data)
            self.logger.info(f"Получен ответ от API при запросе баланса: {json.dumps(response, indent=2)}")
            
            # Обрабатываем ошибку API
            error_response = await self._handle_api_error(response, "query balance")
            if error_response:
                return error_response
            
            # Извлекаем данные о балансе из структуры obj
            obj_data = response.get("obj", {})
            balance = obj_data.get("balance", 0)
            # Если баланс в особом формате провайдера, преобразуем его в доллары
            if balance > 100:  # предполагаем, что большие значения требуют конвертации
                balance = balance / 10000  # делим на 10000, чтобы получить значение в долларах
                
            # Формируем результат
            return {
                "success": True,
                "balance": balance,
                "currency": "USD",  # Предполагаем, что валюта всегда USD
                "api_response": response
            }
                
        except Exception as e:
            self.logger.error(f"Исключение при запросе баланса: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def check_balance_before_operation(self, operation_name: str = "") -> bool:
        """
        Проверяет баланс аккаунта перед выполнением операции и отправляет уведомление администратору,
        если баланс ниже порогового значения.
        
        Args:
            operation_name: Название операции для логирования
            
        Returns:
            bool: True, если баланс достаточный, False в противном случае
        """
        self.logger.info(f"⚖️ Проверка баланса аккаунта перед операцией: {operation_name}")
        
        # Пороговое значение баланса (в долларах) и интервал между уведомлениями (в часах)
        threshold = float(os.getenv("LOW_BALANCE_THRESHOLD", 50))
        min_operational_balance = 5.0  # Минимальный баланс для операций (5$)
        notification_interval = int(os.getenv("BALANCE_NOTIFICATION_INTERVAL", 12)) * 3600  # часы -> секунды
        
        # Ключ для хранения времени последнего уведомления
        last_notification_key = "last_balance_notification_time"
        
        try:
            # Запрашиваем текущий баланс
            balance_result = await self.query_balance()
            
            if not balance_result.get("success"):
                error = balance_result.get("error", "Неизвестная ошибка")
                self.logger.error(f"❌ Не удалось проверить баланс аккаунта: {error}")
                return True  # Продолжаем операцию, если не удалось проверить баланс
            
            # Получаем текущий баланс и валюту
            balance = balance_result.get("balance", 0)
            currency = balance_result.get("currency", "USD")
            
            self.logger.info(f"💰 Текущий баланс аккаунта: {balance} {currency}")
            
            # Проверяем, достаточен ли баланс для операции
            if balance <= 0:
                self.logger.error(f"❌ Недостаточный баланс для операции '{operation_name}': {balance} {currency}")
                return False
                
            # Проверка минимального операционного баланса
            if balance < min_operational_balance:
                self.logger.error(f"❌ Баланс ниже минимального значения для операции '{operation_name}': {balance} {currency} (минимум: {min_operational_balance} {currency})")
                return False
            
            # Если баланс ниже порогового значения, отправляем уведомление администратору
            if balance < threshold:
                # Проверяем, не отправляли ли мы уже уведомление недавно
                current_time = time.time()
                last_notification_time = getattr(self, last_notification_key, 0)
                
                # Отправляем уведомление, только если прошло достаточно времени с момента последнего уведомления
                if current_time - last_notification_time >= notification_interval:
                    admin_chat_id = os.getenv("ADMIN_CHAT_ID")
                    if admin_chat_id:
                        try:
                            # Импортируем Bot из aiogram только если нужно отправить сообщение
                            from aiogram import Bot
                            
                            # Получаем токен бота
                            bot_token = os.getenv("BOT_TOKEN")
                            if not bot_token:
                                self.logger.error("❌ Не удалось получить токен бота для отправки уведомления администратору")
                                return True  # Продолжаем операцию, если не удалось отправить уведомление
                            
                            # Создаем экземпляр бота
                            bot = Bot(token=bot_token)
                            
                            # Формируем сообщение
                            message = f"⚠️ ВНИМАНИЕ! Низкий баланс аккаунта eSIM: {balance} {currency}.\n"
                            message += f"Баланс ниже порогового значения в {threshold} {currency}.\n"
                            if operation_name:
                                message += f"Уведомление вызвано операцией: {operation_name}.\n"
                            message += "Пожалуйста, пополните баланс аккаунта как можно скорее!"
                            
                            # Отправляем сообщение администратору
                            await bot.send_message(admin_chat_id, message)
                            
                            # Обновляем время последнего уведомления
                            setattr(self, last_notification_key, current_time)
                            
                            self.logger.info(f"📨 Уведомление о низком балансе отправлено администратору (chat_id: {admin_chat_id})")
                        except Exception as e:
                            self.logger.error(f"❌ Ошибка при отправке уведомления администратору: {str(e)}")
                    else:
                        self.logger.warning("⚠️ ADMIN_CHAT_ID не установлен. Невозможно отправить уведомление о низком балансе.")
                else:
                    time_since_last = (current_time - last_notification_time) / 3600  # в часах
                    self.logger.info(f"ℹ️ Уведомление о низком балансе не отправлено: последнее уведомление было отправлено {time_since_last:.1f} часов назад")
            
            self.logger.info(f"✅ Баланс достаточен для операции '{operation_name}': {balance} {currency}")
            return True
        except Exception as e:
            self.logger.exception(f"❌ Ошибка при проверке баланса: {e}")
            return True  # Продолжаем операцию, если произошла ошибка при проверке баланса

    def _get_country_name(self, country_code: str) -> str:
        """
        Получает название страны по её коду
        
        Args:
            country_code: Двухбуквенный код страны
            
        Returns:
            str: Название страны или пустая строка
        """
        try:
            country = pycountry.countries.get(alpha_2=country_code)
            if country:
                return country.name
            return country_code
        except Exception:
            return country_code
            
    def _get_country_flag(self, country_code: str) -> str:
        """
        Получает эмодзи флага страны по её коду
        
        Args:
            country_code: Двухбуквенный код страны
            
        Returns:
            str: Эмодзи флага страны или пустая строка
        """
        try:
            # Преобразуем каждую букву в эмодзи региональный индикатор
            # A-Z (Английские) имеют коды 65-90, региональные индикаторы начинаются с 0x1F1E6 (A)
            country_code = country_code.upper()
            if len(country_code) == 2:
                char1 = ord(country_code[0]) - 65 + 0x1F1E6
                char2 = ord(country_code[1]) - 65 + 0x1F1E6
                return chr(char1) + chr(char2)
            return ""
        except Exception:
            return ""
            
    def _create_flag_emoji(self, country_code: str) -> str:
        """
        Создает эмодзи флага страны по её коду
        
        Args:
            country_code: Двухбуквенный код страны
            
        Returns:
            str: Эмодзи флага страны или пустая строка
        """
        return self._get_country_flag(country_code)

    def _convert_to_gb(self, bytes_value: int) -> float:
        """
        Преобразует размер в байтах в гигабайты
        
        Args:
            bytes_value: Размер в байтах
            
        Returns:
            float: Размер в гигабайтах
        """
        try:
            # Проверяем, есть ли значение
            if not bytes_value:
                return 0.0
                
            # Преобразуем байты в ГБ (1 ГБ = 1024^3 байт)
            gb_value = float(bytes_value) / (1024 * 1024 * 1024)
            
            # Округляем до 2 знаков после запятой для читаемости
            return round(gb_value, 2)
        except Exception as e:
            self.logger.error(f"Ошибка при конвертации размера пакета в ГБ: {e}")
            return 0.0

    def _convert_price(self, price, package_code, package_data):
        """
        Конвертирует цену пакета в USD
        
        Args:
            price: Цена пакета в формате API (71000 = $7.10)
            package_code: Код пакета (для логирования)
            package_data: Данные о пакете
            
        Returns:
            float: Цена в USD
        """
        try:
            if not price:
                return 0.0
                
            # Преобразуем строку в число
            usd_price = float(price)
            
            # API возвращает цены в формате 71000 = $7.10, делим на 10000
            usd_price = usd_price / 10000.0
            
            # Округляем до 2 знаков после запятой
            return round(usd_price, 2)
        except Exception as e:
            self.logger.error(f"Ошибка при конвертации цены пакета {package_code}: {e}")
            return 0.0

# Создаем экземпляр сервиса для использования в других модулях
esim_service = ESIMService()
