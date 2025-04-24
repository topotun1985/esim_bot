from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Text, BigInteger, JSON, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()

class User(Base):
    """User model to store Telegram user information"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    language_code = Column(String(10), default='ru')
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    orders = relationship("Order", back_populates="user")
    support_tickets = relationship("SupportTicket", back_populates="user")
    
    def __repr__(self):
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, username={self.username})>"


class Country(Base):
    """Country model to store available countries for eSIM"""
    __tablename__ = 'countries'
    
    id = Column(Integer, primary_key=True)
    code = Column(String(10), unique=True, nullable=False)  # Country code (e.g., US, GB)
    name = Column(String(255), nullable=False)  # Country name
    name_ru = Column(String(255), nullable=True)  # Country name in Russian
    flag_emoji = Column(String(10), nullable=True)  # Flag emoji (e.g., 🇺🇸)
    is_available = Column(Boolean, default=True)
    
    # Relationships
    packages = relationship("Package", back_populates="country")
    
    def __repr__(self):
        return f"<Country(id={self.id}, code={self.code}, name={self.name})>"


class Package(Base):
    """Package model to store eSIM packages with their details"""
    __tablename__ = 'packages'
    
    id = Column(Integer, primary_key=True)
    country_id = Column(Integer, ForeignKey('countries.id'), nullable=False)
    package_code = Column(String(255), unique=True, nullable=False)  # Code from provider
    slug = Column(String(255), unique=True, nullable=True)  # Slug from provider
    name = Column(String(255), nullable=False)  # Package name
    data_amount = Column(Float, nullable=False)  # Amount of data in GB
    duration = Column(Integer, nullable=False)  # Duration in days
    price = Column(Float, nullable=False)  # Price in USD (wholesale price from provider)
    retail_price = Column(Float, nullable=True)  # Our retail price in USD
    description = Column(Text, nullable=True)  # Package description
    is_available = Column(Boolean, default=True)
    last_synced_at = Column(DateTime, nullable=True)  # Timestamp of last sync
    
    # Relationships
    country = relationship("Country", back_populates="packages")
    orders = relationship("Order", back_populates="package")
    
    def __repr__(self):
        return f"<Package(id={self.id}, name={self.name}, data_amount={self.data_amount}GB, duration={self.duration} days, price=${self.price})>"


class OrderStatus(enum.Enum):
    """Enum for order statuses"""
    CREATED = "created"  # Заказ создан
    AWAITING_PAYMENT = "awaiting_payment"  # Ожидается оплата
    PAID = "paid"  # Оплачено, но eSIM еще не заказана
    PROCESSING = "processing"  # Заказ обрабатывается у поставщика
    COMPLETED = "completed"  # Заказ выполнен, eSIM предоставлена
    FAILED = "failed"  # Произошла ошибка при обработке заказа
    CANCELED = "canceled"  # Заказ отменен


class OrderType(enum.Enum):
    """Enum for order types"""
    NEW = "new"  # Заказ на новую eSIM
    TOPUP = "topup"  # Заказ на пополнение трафика существующей eSIM


class PaymentMethod(enum.Enum):
    """Enum for payment methods"""
    CARD = "card"  # Оплата картой через Telegram Pay
    CRYPTO_TON = "crypto_ton"  # Оплата в TON через CryptoBot
    CRYPTO_BTC = "crypto_btc"  # Оплата в Bitcoin через Cryptomus
    CRYPTO_ETH = "crypto_eth"  # Оплата в Ethereum через Cryptomus
    CRYPTO_USDT = "crypto_usdt"  # Оплата в USDT через Cryptomus


class Order(Base):
    """Order model to store eSIM orders"""
    __tablename__ = 'orders'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    package_id = Column(Integer, ForeignKey('packages.id'), nullable=False)
    transaction_id = Column(String(255), unique=True, nullable=False)  # Уникальный ID для API-провайдера
    order_no = Column(String(255), unique=True, nullable=True)  # Номер заказа от провайдера
    status = Column(String(50), default=OrderStatus.CREATED.value)
    order_type = Column(String(50), default=OrderType.NEW.value)
    payment_method = Column(String(50), nullable=True)  # Метод оплаты
    payment_id = Column(String(255), nullable=True)  # ID платежа от платежной системы
    invoice_id = Column(String(255), nullable=True)  # ID инвойса от CryptoBot/Cryptomus
    payment_details = Column(Text, nullable=True)  # Детали платежа в JSON формате
    paid_at = Column(DateTime, nullable=True)  # Дата и время оплаты
    amount = Column(Float, nullable=False)  # Сумма в USD
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="orders")
    package = relationship("Package", back_populates="orders")
    esim = relationship("ESim", uselist=False, back_populates="order")
    
    def __repr__(self):
        return f"<Order(id={self.id}, transaction_id={self.transaction_id}, status={self.status})>"


class ESim(Base):
    """ESim model to store eSIM details after successful order"""
    __tablename__ = 'esims'
    
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=False, unique=True)
    esim_tran_no = Column(String(255), nullable=True)  # Номер транзакции от провайдера
    iccid = Column(String(255), nullable=True)  # Идентификатор SIM-карты
    imsi = Column(String(255), nullable=True)  # Международный идентификатор мобильного абонента
    msisdn = Column(String(255), nullable=True)  # Номер телефона
    activation_code = Column(String(1024), nullable=True)  # Код активации eSIM
    qr_code_url = Column(String(1024), nullable=True)  # URL QR-кода
    short_url = Column(String(512), nullable=True)  # Короткий URL для QR-кода
    smdp_status = Column(String(50), nullable=True)  # Статус SM-DP+
    esim_status = Column(String(50), nullable=True)  # Статус eSIM
    active_type = Column(Integer, nullable=True)  # Тип активации
    expired_time = Column(DateTime, nullable=True)  # Время истечения срока действия
    total_volume = Column(BigInteger, nullable=True)  # Общий объем данных в байтах
    total_duration = Column(Integer, nullable=True)  # Общая продолжительность в днях
    duration_unit = Column(String(20), nullable=True)  # Единица измерения продолжительности
    order_usage = Column(BigInteger, nullable=True)  # Использованный объем данных в байтах
    pin = Column(String(50), nullable=True)  # PIN-код, если предоставляется
    puk = Column(String(50), nullable=True)  # PUK-код, если предоставляется
    apn = Column(String(255), nullable=True)  # Имя точки доступа
    raw_data = Column(JSON, nullable=True)  # Необработанные данные от API
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    order = relationship("Order", back_populates="esim")
    
    def __repr__(self):
        return f"<ESim(id={self.id}, iccid={self.iccid}, esim_status={self.esim_status})>"


class FAQ(Base):
    """FAQ model to store frequently asked questions"""
    __tablename__ = 'faqs'
    
    id = Column(Integer, primary_key=True)
    question_en = Column(Text, nullable=False)  # Вопрос на английском
    answer_en = Column(Text, nullable=False)  # Ответ на английском
    question_ru = Column(Text, nullable=True)  # Вопрос на русском
    answer_ru = Column(Text, nullable=True)  # Ответ на русском
    order = Column(Integer, default=0)  # Порядок отображения
    is_active = Column(Boolean, default=True)  # Активность FAQ
    
    def __repr__(self):
        return f"<FAQ(id={self.id}, question_en={self.question_en[:30]}...)>"


class SupportTicket(Base):
    """Support ticket model for user support requests"""
    __tablename__ = 'support_tickets'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    subject = Column(String(255), nullable=False)  # Тема запроса
    message = Column(Text, nullable=False)  # Сообщение
    status = Column(String(50), default='open')  # open, closed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="support_tickets")
    messages = relationship("SupportMessage", back_populates="ticket")
    
    def __repr__(self):
        return f"<SupportTicket(id={self.id}, user_id={self.user_id}, status={self.status})>"


class SupportMessage(Base):
    """Model for messages in support chat"""
    __tablename__ = 'support_messages'
    
    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey('support_tickets.id'), nullable=False)
    sender_type = Column(String(20), nullable=False)  # user, admin
    text = Column(Text, nullable=False)  # Текст сообщения
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    ticket = relationship("SupportTicket", back_populates="messages")
    
    def __repr__(self):
        return f"<SupportMessage(id={self.id}, ticket_id={self.ticket_id}, sender_type={self.sender_type})>"