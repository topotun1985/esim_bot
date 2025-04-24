from enum import Enum, auto
from aiogram.fsm.state import State, StatesGroup

class MainMenu(StatesGroup):
    """Основное меню бота"""
    menu = State()

class BuyESim(StatesGroup):
    """Состояния для процесса покупки eSIM"""
    select_country = State()  # Выбор страны
    select_duration = State()  # Выбор длительности пакета
    select_package = State()  # Выбор тарифного плана
    confirm_purchase = State()  # Подтверждение покупки
    select_payment = State()  # Выбор метода оплаты
    awaiting_payment = State()  # Ожидание оплаты
    payment_complete = State()  # Оплата завершена

class AccountMenu(StatesGroup):
    """Состояния для раздела личного кабинета"""
    menu = State()  # Главное меню личного кабинета
    orders = State()  # Список заказов
    order_details = State()  # Детали конкретного заказа
    language = State()  # Выбор языка

class SupportMenu(StatesGroup):
    """Состояния для раздела поддержки"""
    menu = State()  # Главное меню поддержки
    faq = State()  # Просмотр FAQ
    faq_details = State()  # Подробная информация по конкретному FAQ
    new_ticket = State()  # Создание нового тикета
    enter_subject = State()  # Ввод темы тикета
    enter_message = State()  # Ввод сообщения тикета
    ticket_list = State()  # Список тикетов пользователя
    ticket_chat = State()  # Чат с поддержкой по конкретному тикету

class AdminMenu(StatesGroup):
    """Состояния для раздела администратора"""
    menu = State()  # Главное меню администратора
    stats = State()  # Статистика продаж
    orders = State()  # Управление заказами
    order_details = State()  # Детали заказа
    packages = State()  # Управление тарифными планами
    edit_package = State()  # Редактирование тарифного плана
    countries = State()  # Управление странами
    edit_country = State()  # Редактирование информации о стране
    support = State()  # Раздел поддержки
    tickets = State()  # Список тикетов
    ticket_chat = State()  # Чат с пользователем

class Form(Enum):
    """Enum для форм ввода данных"""
    SUBJECT = auto()  # Тема обращения
    MESSAGE = auto()  # Сообщение
    
class CallbackData(Enum):
    """Enum для данных в callback_data"""
    COUNTRY = 'country'  # Идентификатор страны
    PACKAGE = 'package'  # Идентификатор пакета
    DURATION = 'duration'  # Длительность пакета в днях
    ORDER = 'order'  # Идентификатор заказа
    PAYMENT = 'payment'  # Метод оплаты
    FAQ = 'faq'  # Идентификатор FAQ
    TICKET = 'ticket'  # Идентификатор тикета
    BACK = 'back'  # Кнопка "назад"
    CANCEL = 'cancel'  # Кнопка "отмена"
    CONFIRM = 'confirm'  # Кнопка "подтвердить"
    LANGUAGE = 'language'  # Выбор языка
    PAGE = 'page'  # Номер страницы для пагинации


class PaymentState(StatesGroup):
    """Состояния для процесса оплаты"""
    select_method = State()  # Выбор способа оплаты
    ton_payment = State()    # Оплата через TON (CryptoBot)
    crypto_payment = State()  # Оплата через Cryptomus
    awaiting_payment = State()  # Ожидание подтверждения оплаты

class TopUpESim(StatesGroup):
    """Состояния для пополнения трафика eSIM"""
    select_duration = State()  # Выбор длительности пакета
    select_package = State()  # Выбор пакета для пополнения
    confirm_payment = State()  # Подтверждение оплаты
    select_payment = State()  # Выбор способа оплаты

class SMSMenu(StatesGroup):
    """Состояния для меню отправки SMS"""
    select_esim = State()      # Выбор eSIM для отправки
    enter_message = State()    # Ввод текста сообщения
    confirm_send = State()     # Подтверждение отправки