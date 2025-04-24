import os
import uuid
import requests
import json
from dotenv import load_dotenv

load_dotenv()

# Константы и API ключи
CRYPTOBOT_API_TOKEN = os.getenv("CRYPTOBOT_API_TOKEN", "")
CRYPTOBOT_API_URL = "https://pay.crypt.bot/api"

CRYPTOMUS_API_KEY = os.getenv("CRYPTOMUS_API_KEY", "")
CRYPTOMUS_API_SECRET = os.getenv("CRYPTOMUS_API_SECRET", "")
CRYPTOMUS_API_URL = "https://api.cryptomus.com/v1"

# ------------------ Generic CryptoBot invoice creator ------------------
async def create_crypto_invoice(order_id: int, amount_usd: float, asset: str = "TON"):
    """
    Создаёт инвойс в CryptoBot в указанной валюте.

    Args:
        order_id: идентификатор заказа
        amount_usd: сумма к оплате в долларах
        asset: тикер криптовалюты (TON, USDT, BTC, ...)
    """
    import aiohttp, logging

    logger = logging.getLogger(__name__)

    # --- Рассчитываем эквивалент суммы в выбранной валюте ---
    if asset.upper() == "USDT":  # стейбл переводится 1‑к‑1 к USD
        amount = round(amount_usd, 2)
    else:
        cg_ids = {
            "TON": "the-open-network",
            "BTC": "bitcoin",
            "ETH": "ethereum",
        }
        cg_id = cg_ids.get(asset.upper())
        amount = amount_usd  # fallback, если курс не найден
        if cg_id:
            async with aiohttp.ClientSession() as session:
                resp = await session.get(
                    "https://api.coingecko.com/api/v3/simple/price",
                    params={"ids": cg_id, "vs_currencies": "usd"},
                    timeout=10,
                )
                if resp.status == 200:
                    rate = (await resp.json())[cg_id]["usd"]
                    if rate:
                        amount = round(amount_usd / rate, 8)
    logger.info(
        f"Creating CryptoBot invoice for order {order_id}: {amount_usd}$ -> {amount} {asset.upper()}"
    )

    params = {
        "asset": asset.upper(),
        "amount": str(amount),
        "description": f"eSIM order #{order_id}",
        "payload": f"order_{order_id}",
        "allow_comments": False,
    }

    headers = {
        "Crypto-Pay-API-Token": CRYPTOBOT_API_TOKEN,
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        resp = await session.post(f"{CRYPTOBOT_API_URL}/createInvoice", json=params, headers=headers)
        data = await resp.json()
        if resp.status == 200 and data.get("ok"):
            res = data["result"]
            invoice = {
                "invoice_id": res["invoice_id"],
                "payment_url": res["pay_url"],
                "amount": amount,
                "asset": asset.upper(),
            }
            logger.info(f"Invoice created: {invoice}")
            return invoice

    logger.error(f"CryptoBot error response: {data}")
    return None


# ----------------------------------------------------------------------
# Back‑compat wrapper (keeps the old name alive)
async def create_ton_invoice(order_id: int, amount_usd: float):
    """Совместимая обёртка: создаёт инвойс в TON"""
    return await create_crypto_invoice(order_id, amount_usd, "TON")


# ----------------------------------------------------------------------
async def create_any_crypto_invoice(order_id, amount_usd):
    """
    Создает инвойс в CryptoBot c параметром asset="ANY_CRYPTO".
    Пользователь выбирает конкретную монету в интерфейсе CryptoBot.

    Args:
        order_id: ID заказа в нашей системе
        amount_usd: Сумма в USD

    Returns:
        dict: Информация об инвойсе (payment_url, invoice_id, amount)
    """
    import aiohttp
    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"Creating ANY_CRYPTO invoice for order {order_id} with amount ${amount_usd}")

    # Запрос курса TON к USD через Coingecko API
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "the-open-network", "vs_currencies": "usd"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    ton_usd_rate = data.get("the-open-network", {}).get("usd", 0)
                    if ton_usd_rate > 0:
                        # USD к TON (например, если 1 TON = 5 USD, то 1 USD = 0.2 TON)
                        ton_rate = 1 / ton_usd_rate
                    else:
                        ton_rate = 0.3  # Запасной вариант, если API недоступен
                else:
                    ton_rate = 0.3  # Запасной вариант, если API вернул ошибку
    except Exception as e:
        logger.error(f"Ошибка при получении курса TON: {e}")
        ton_rate = 0.3  # Запасной вариант, если API недоступен

    # Преобразуем USD к эквиваленту TON для предварительной суммы (CryptoBot пересчитает при выборе монеты)
    amount_ton = round(amount_usd * ton_rate, 2)
    logger.info(
        f"Converted ${amount_usd} ~ {amount_ton} TON (rate: {ton_rate}) for ANY_CRYPTO invoice")

    # Создаем уникальный ID для платежа
    app_invoice_id = f"order_{order_id}_{uuid.uuid4().hex[:8]}"

    # Параметры для запроса - обязательно используем формат API v1
    params = {
        "asset": "ANY_CRYPTO",
        "amount": str(amount_ton),  # API требует строковые значения
        "description": f"eSIM order #{order_id}",
        "hidden_message": f"Thank you for your purchase! Order ID: {order_id}",
        "paid_btn_name": "callback",
        "paid_btn_url": "https://t.me/your_bot",  # Замените на вашего бота
        "payload": app_invoice_id,
        "allow_comments": False,
        "allow_anonymous": False,
        "expires_in": 86400  # 24 часа в секундах
    }

    # Выводим параметры для отладки
    logger.info(f"CryptoBot API request parameters: {params}")

    # Выполняем запрос к API CryptoBot
    try:
        headers = {
            "Crypto-Pay-API-Token": CRYPTOBOT_API_TOKEN,
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            url = f"{CRYPTOBOT_API_URL}/createInvoice"
            logger.info(f"Sending request to {url}")

            async with session.post(
                url,
                json=params,
                headers=headers
            ) as resp:
                response_text = await resp.text()
                logger.info(f"CryptoBot API response status: {resp.status}")
                logger.info(f"CryptoBot API response: {response_text}")

                if resp.status == 200:
                    data = await resp.json()
                    if data.get("ok"):
                        result = data.get("result", {})
                        response = {
                            "invoice_id": result.get("invoice_id"),
                            "payment_url": result.get("pay_url"),
                            "amount": amount_ton,
                            "asset": "ANY_CRYPTO"
                        }
                        logger.info(f"Successfully created invoice: {response}")
                        return response
                    else:
                        error_msg = f"Ошибка CryptoBot API: {data.get('error')}"
                        logger.error(error_msg)
                else:
                    error_msg = f"Ошибка HTTP: {resp.status}, Текст: {response_text}"
                    logger.error(error_msg)
    except Exception as e:
        logger.exception(f"Ошибка при создании инвойса в CryptoBot: {e}")

    # Если произошла ошибка, возвращаем прямую ссылку на CryptoBot
    response = {
        "invoice_id": f"fallback_{uuid.uuid4().hex[:8]}",
        "payment_url": f"https://t.me/CryptoBot?start=pay_{CRYPTOBOT_API_TOKEN.split(':')[0]}_{amount_ton}_TON",
        "amount": amount_ton,
        "asset": "TON"
    }
    logger.info(f"Using fallback payment URL: {response['payment_url']}")

    return response

# Функция для создания инвойса в Cryptomus
async def create_cryptomus_invoice(order_id, amount_usd, currency="USDT"):
    """
    Создает инвойс в Cryptomus для оплаты в различных криптовалютах

    Args:
        order_id: ID заказа в нашей системе
        amount_usd: Сумма в USD
        currency: Криптовалюта для оплаты (по умолчанию USDT)

    Returns:
        dict: Информация об инвойсе (payment_url, invoice_id)
    """
    import aiohttp
    import hashlib
    import time
    import logging

    logger = logging.getLogger(__name__)

    # Создаем уникальный ID для платежа
    order_id_str = f"esim_{order_id}_{uuid.uuid4().hex[:8]}"

    # Параметры для запроса
    payload = {
        "amount": str(amount_usd),
        "currency": "USD",
        "order_id": order_id_str,
        "payment_method": currency,
        "to_currency": currency,
        "url_callback": "",  # Можно добавить URL для вебхуков
        "url_return": "",  # URL для возврата после оплаты
        "is_payment_multiple": False,  # Одноразовый платеж
        "lifetime": "24",  # Время жизни инвойса в часах
        "description": f"eSIM order #{order_id}"
    }

    # Пытаемся выполнить запрос к API Cryptomus
    try:
        # Создаем подпись для запроса
        json_payload = json.dumps(payload)
        sign = hashlib.md5(json_payload.encode() + CRYPTOMUS_API_SECRET.encode()).hexdigest()

        headers = {
            "merchant": CRYPTOMUS_API_KEY,
            "sign": sign,
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{CRYPTOMUS_API_URL}/payment",
                json=payload,
                headers=headers
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("state") == 0:  # Успешный ответ
                        result = data.get("result", {})
                        return {
                            "invoice_id": result.get("uuid"),
                            "payment_url": result.get("url"),
                            "amount": amount_usd,
                            "currency": currency
                        }
                    else:
                        logger.error(f"Cryptomus API error: {data.get('message')}")
                        return None
                else:
                    logger.error(f"HTTP error {resp.status}: {await resp.text()}")
                    return None
    except Exception as e:
        logger.exception(f"Error creating Cryptomus invoice: {e}")
        return None

# Функция для проверки статуса платежа в CryptoBot
async def check_ton_payment(invoice_id):
    """
    Проверяет статус платежа в CryptoBot

    Args:
        invoice_id: ID инвойса в CryptoBot

    Returns:
        dict: Информация о платеже (status, paid, amount, fee) или None в случае ошибки
    """
    import aiohttp
    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"Checking payment status for invoice_id: {invoice_id}")

    # Если это фоллбэк инвойс, вернуть заглушку
    if str(invoice_id).startswith(("demo_", "fallback_")):
        logger.info(f"This is a fallback invoice, returning not paid status")
        return {"paid": False, "status": "pending", "amount": 0, "fee": 0}

    try:
        headers = {
            "Crypto-Pay-API-Token": CRYPTOBOT_API_TOKEN,
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            # Используем правильный метод API: getInvoices вместо invoices
            url = f"{CRYPTOBOT_API_URL}/getInvoices"
            logger.info(f"Sending request to {url} for invoice_id: {invoice_id}")

            # Параметры запроса согласно обновленной документации API
            params = {"invoice_ids": invoice_id}

            async with session.get(
                url,
                params=params,
                headers=headers
            ) as resp:
                response_text = await resp.text()
                logger.info(f"CryptoBot API response status: {resp.status}")
                logger.info(f"CryptoBot API response: {response_text}")

                if resp.status == 200:
                    data = await resp.json()
                    if data.get("ok"):
                        # Ищем нужный инвойс в списке результатов
                        items = data.get("result", {}).get("items", [])
                        if items and len(items) > 0:
                            for invoice in items:
                                if str(invoice.get("invoice_id")) == str(invoice_id):
                                    status = invoice.get("status")
                                    is_paid = status == "paid"

                                    payment_info = {
                                        "paid": is_paid,
                                        "status": status,
                                        "amount": invoice.get("amount"),
                                        "fee": invoice.get("fee", 0),
                                        "payload": invoice.get("payload"),
                                        "asset": invoice.get("asset")
                                    }

                                    logger.info(f"Payment status for invoice {invoice_id}: {payment_info}")
                                    return payment_info

                            logger.warning(f"Invoice {invoice_id} not found in response items")
                        else:
                            logger.warning(f"No invoices found in response")
                    else:
                        error_msg = f"Ошибка CryptoBot API: {data.get('error')}"
                        logger.error(error_msg)
                else:
                    error_msg = f"Ошибка HTTP: {resp.status}, Текст: {response_text}"
                    logger.error(error_msg)
    except Exception as e:
        print(f"Ошибка при проверке платежа в CryptoBot: {e}")

    return False  # В случае ошибки возвращаем False

# Функция для проверки статуса платежа в Cryptomus
async def check_cryptomus_payment(invoice_id):
    """
    Проверяет статус платежа в Cryptomus

    Args:
        invoice_id: ID инвойса в Cryptomus

    Returns:
        bool: True если оплачен, False если не оплачен
    """
    import aiohttp
    import hashlib

    # Если это тестовый инвойс, вернуть False
    if str(invoice_id).startswith("demo_cm_"):
        return False

    try:
        # Формируем параметры запроса
        payload = {
            "uuid": invoice_id
        }

        # Создаем подпись
        json_payload = json.dumps(payload)
        sign = hashlib.md5(json_payload.encode() + CRYPTOMUS_API_SECRET.encode()).hexdigest()

        headers = {
            "merchant": CRYPTOMUS_API_KEY,
            "sign": sign,
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{CRYPTOMUS_API_URL}/payment/info",
                json=payload,
                headers=headers
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("state") == 0:  # Успешный ответ
                        result = data.get("result", {})
                        # Статус 'paid' означает, что инвойс оплачен
                        status = result.get("status")
                        return status == "paid"
                    else:
                        print(f"Ошибка Cryptomus API: {data.get('message')}")
                else:
                    print(f"Ошибка HTTP: {resp.status}")
    except Exception as e:
        print(f"Ошибка при проверке платежа в Cryptomus: {e}")

    return False  # В случае ошибки возвращаем False