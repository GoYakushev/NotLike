from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Enum, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, backref
from datetime import datetime
import json
from typing import List
import enum

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    full_name = Column(String)
    language_code = Column(String)
    referral_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    registration_date = Column(DateTime)
    last_login_date = Column(DateTime)
    is_admin = Column(Boolean, default=False)
    is_banned = Column(Boolean, default=False)
    balance = Column(Float, default=0.0)
    referrals = relationship("User", backref=backref("referrer", remote_side=[id]))
    wallets = relationship("Wallet", back_populates="user")
    transactions = relationship("Transaction", back_populates="user")
    p2p_orders = relationship("P2POrder", back_populates="user", foreign_keys=[P2POrder.user_id])
    taken_p2p_orders = relationship("P2POrder", back_populates="taker", foreign_keys=[P2POrder.taker_id])
    is_premium = Column(Boolean, default=False)
    premium_expires_at = Column(DateTime, nullable=True)
    hide_p2p_orders = Column(Boolean, default=False)

    def __repr__(self):
        return f"<User(telegram_id={self.telegram_id}, username={self.username})>"

class Wallet(Base):
    __tablename__ = 'wallets'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    network = Column(String)  # 'SOL' или 'TON'
    address = Column(String)  # Адрес кошелька пользователя в сети
    private_key = Column(String)
    balance = Column(Float, default=0.0)
    locked_balance = Column(Float, default=0.0)
    token_address = Column(String, nullable=True)  # Адрес контракта токена
    
    user = relationship("User", back_populates="wallets")

    def __repr__(self):
        return f"<Wallet(user_id={self.user_id}, network={self.network}, address={self.address})>"

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    wallet_id = Column(Integer, ForeignKey("wallets.id"))
    transaction_hash = Column(String, unique=True)
    amount = Column(Float)
    timestamp = Column(DateTime)
    status = Column(String)
    transaction_type = Column(String)
    token_address = Column(String, nullable=True)

    user = relationship("User", back_populates="transactions")

    def __repr__(self):
        return f"<Transaction(user_id={self.user_id}, transaction_hash={self.transaction_hash}, amount={self.amount})>"

class Review(Base):
    __tablename__ = 'reviews'
    
    id = Column(Integer, primary_key=True)
    reviewer_id = Column(Integer, ForeignKey('users.id'))
    reviewee_id = Column(Integer, ForeignKey('users.id'))
    order_id = Column(Integer, ForeignKey('p2p_orders.id'), nullable=True)  #  P2P
    rating = Column(Integer)
    comment = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    reviewer = relationship("User", foreign_keys=[reviewer_id], backref="reviews_given")
    reviewee = relationship("User", foreign_keys=[reviewee_id], backref="reviews_received")
    order = relationship("P2POrder", back_populates="reviews")

class SpotOrder(Base):
    __tablename__ = 'spot_orders'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    base_currency = Column(String, nullable=False)
    quote_currency = Column(String, nullable=False)
    order_type = Column(Enum("MARKET", "LIMIT"), nullable=False)
    side = Column(Enum("BUY", "SELL"), nullable=False)
    price = Column(Float, nullable=True)  # Может быть Null для MARKET ордеров
    quantity = Column(Float, nullable=False)
    status = Column(Enum("OPEN", "FILLED", "PARTIALLY_FILLED", "CANCELLED"), default="OPEN")
    created_at = Column(DateTime, default=datetime.utcnow)
    filled_amount = Column(Float, default=0.0)
    take_profit = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    
    user = relationship("User", backref="spot_orders")

    def __repr__(self):
        return (
            f"<SpotOrder(user_id={self.user_id}, base_currency={self.base_currency}, "
            f"quote_currency={self.quote_currency}, order_type={self.order_type}, side={self.side}, "
            f"price={self.price}, quantity={self.quantity}, status={self.status})>"
        )

class Token(Base):
    __tablename__ = 'tokens'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    symbol = Column(String, unique=True, index=True)
    address = Column(String, unique=True, index=True)
    decimals = Column(Integer)
    network = Column(String)  # SOL или TON
    total_supply = Column(Float)
    circulating_supply = Column(Float)
    market_cap = Column(Float)
    volume_24h = Column(Float)
    ath = Column(Float)
    atl = Column(Float)
    
    def __repr__(self):
        return f"<Token(name={self.name}, symbol={self.symbol}, address={self.address})>"

class P2POrderStatus(enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DISPUTE = "dispute"
    CONFIRMED = "confirmed"

class P2PPaymentMethod(enum.Enum):
    #  способов оплаты
    TINKOFF = "TINKOFF"
    SBERBANK = "SBERBANK"
    QIWI = "QIWI"
    YOOMONEY = "YOOMONEY"
    #  способы

class P2POrder(Base):
    __tablename__ = 'p2p_orders'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    taker_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    side = Column(String)  # "BUY" or "SELL"
    crypto_amount = Column(Float)
    fiat_amount = Column(Float)
    fiat_currency = Column(String)
    payment_method = Column(String)
    limit_min = Column(Float, nullable=True)
    limit_max = Column(Float, nullable=True)
    time_limit = Column(Integer, nullable=True)  #  минутах
    status = Column(Enum(P2POrderStatus), default=P2POrderStatus.OPEN)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)  #  
    price = Column(Float) #  цену
    base_currency = Column(String) #  
    quote_currency = Column(String) #

    user = relationship("User", back_populates="p2p_orders", foreign_keys=[user_id])
    taker = relationship("User", back_populates="taken_p2p_orders", foreign_keys=[taker_id])
    reviews = relationship("Review", back_populates="order")

class P2PAdvertisement(Base):
    __tablename__ = 'p2p_advertisements'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    type = Column(String)  # BUY/SELL
    crypto_currency = Column(String)
    fiat_currency = Column(String)
    price = Column(Float)
    min_amount = Column(Float)
    max_amount = Column(Float)
    payment_method_id = Column(Integer, ForeignKey('payment_methods.id'))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User")
    payment_method = relationship("PaymentMethod")

class P2PDispute(Base):
    __tablename__ = 'p2p_disputes'
    
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('p2p_orders.id'))
    opener_id = Column(Integer, ForeignKey('users.id'))
    reason = Column(String)
    status = Column(String)  # OPEN, RESOLVED
    resolution = Column(String, nullable=True)  # REFUND, COMPLETE
    resolved_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    
    order = relationship("P2POrder")
    opener = relationship("User", foreign_keys=[opener_id])
    resolver = relationship("User", foreign_keys=[resolved_by])

class PaymentMethod(Base):
    __tablename__ = 'payment_methods'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    
P2PPaymentMethod = PaymentMethod

class Admin(Base):
    __tablename__ = 'admins'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    role = Column(String)  # SUPERADMIN, SUPPORT, ...
    permissions = Column(String)  # JSON
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User")

class AdminLog(Base):
    __tablename__ = 'admin_logs'
    
    id = Column(Integer, primary_key=True)
    admin_id = Column(Integer, ForeignKey('admins.id'))
    action = Column(String)
    details = Column(String, nullable=True)  # JSON
    created_at = Column(DateTime, default=datetime.utcnow)
    
    admin = relationship("Admin")

class SupportTicket(Base):
    __tablename__ = 'support_tickets'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    subject = Column(String)
    status = Column(String)  # OPEN, CLOSED, IN_PROGRESS
    priority = Column(String)  # LOW, MEDIUM, HIGH
    created_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    
    user = relationship("User")
    messages = relationship("SupportMessage", back_populates="ticket")

class SupportMessage(Base):
    __tablename__ = 'support_messages'
    
    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey('support_tickets.id'))
    sender_id = Column(Integer, ForeignKey('users.id'))
    message = Column(String)
    is_from_support = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    ticket = relationship("SupportTicket", back_populates="messages")
    sender = relationship("User")

class CopyTrader(Base):
    __tablename__ = 'copy_traders'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    monthly_profit = Column(Float, default=0.0)
    successful_trades = Column(Integer, default=0)
    total_trades = Column(Integer, default=0)
    followers_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User")
    followers = relationship("CopyTraderFollower", back_populates="trader")

class CopyTraderFollower(Base):
    __tablename__ = 'copy_trader_followers'
    
    id = Column(Integer, primary_key=True)
    trader_id = Column(Integer, ForeignKey('copy_traders.id'))
    follower_id = Column(Integer, ForeignKey('users.id'))
    copy_amount = Column(Float)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    trader = relationship("CopyTrader", back_populates="followers")
    follower = relationship("User")

class SwapOrder(Base):
    __tablename__ = 'swap_orders'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    from_currency = Column(String)
    to_currency = Column(String)
    amount = Column(Float)
    rate = Column(Float)
    status = Column(String)  # PENDING, COMPLETED, FAILED
    simpleswap_id = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User")

class Notification(Base):
    __tablename__ = 'notifications'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    type = Column(String)  # ORDER, P2P, SYSTEM, PRICE_ALERT
    title = Column(String)
    message = Column(String)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User")

class PriceAlert(Base):
    __tablename__ = 'price_alerts'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    token_id = Column(Integer, ForeignKey('tokens.id'))
    condition = Column(String)  # ABOVE, BELOW
    price = Column(Float)
    is_triggered = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User")
    token = relationship("Token")

class MarketAnalysis(Base):
    __tablename__ = 'market_analysis'
    
    id = Column(Integer, primary_key=True)
    token_id = Column(Integer, ForeignKey('tokens.id'))
    analysis_type = Column(String)  # TECHNICAL, SENTIMENT, AI_COMBINED
    prediction = Column(String)  # BULLISH, BEARISH, NEUTRAL
    confidence = Column(Float)  # 0-1
    details = Column(String, nullable=True)  # JSON
    created_at = Column(DateTime, default=datetime.utcnow)
    
    token = relationship("Token")

class ReferralProgram(Base):
    __tablename__ = 'referral_programs'
    
    id = Column(Integer, primary_key=True)
    name = Column(String)
    description = Column(String)
    commission_rate = Column(Float)  #  
    start_date = Column(DateTime)
    end_date = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ReferralEarning(Base):
    __tablename__ = 'referral_earnings'
    
    id = Column(Integer, primary_key=True)
    referrer_id = Column(Integer, ForeignKey('users.id'))
    referred_id = Column(Integer, ForeignKey('users.id'))
    order_id = Column(Integer, ForeignKey('spot_orders.id'), nullable=True)  #  SpotOrder
    amount = Column(Float)
    currency = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    referrer = relationship("User", foreign_keys=[referrer_id])
    referred = relationship("User", foreign_keys=[referred_id])

class ExchangeAccount(Base):
    __tablename__ = 'exchange_accounts'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    exchange = Column(String)  # BINANCE, BYBIT, ...
    api_key = Column(String)
    api_secret = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User")

class DemoOrder(Base):
    __tablename__ = 'demo_orders'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    token_id = Column(Integer, ForeignKey('tokens.id'))
    order_type = Column(String)  # MARKET, LIMIT
    side = Column(String)  # BUY, SELL
    amount = Column(Float)
    price = Column(Float)
    status = Column(String)  # OPEN, CLOSED, CANCELLED
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User")
    token = relationship("Token")

class AutoSwap(Base):
    __tablename__ = 'auto_swaps'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    from_network = Column(String)
    to_network = Column(String)
    amount = Column(Float)
    estimated_amount = Column(Float)
    exchange_id = Column(String)
    status = Column(String)  # PENDING, COMPLETED, FAILED, EXPIRED
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User")

class NotificationSettings(Base):
    __tablename__ = 'notification_settings'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    settings = Column(String)  # JSON с настройками
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    
    user = relationship("User")
    
    def is_enabled(self, notification_type: str) -> bool:
        """Проверяет включен ли тип уведомлений"""
        settings = json.loads(self.settings)
        return settings.get(notification_type, {}).get('enabled', True)
        
    def get_channels(self, notification_type: str) -> List[str]:
        """Возвращает каналы доставки для типа уведомлений"""
        settings = json.loads(self.settings)
        return settings.get(notification_type, {}).get('channels', ['telegram'])
        
    def update_settings(self, notification_type: str, enabled: bool, channels: List[str]):
        """Обновляет настройки уведомлений"""
        settings = json.loads(self.settings)
        settings[notification_type] = {
            'enabled': enabled,
            'channels': channels
        }
        self.settings = json.dumps(settings)

class FeeTransaction(Base):  #  модель
    __tablename__ = 'fee_transactions'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    operation_type = Column(String)  #  операции (P2P, SPOT, SWAP, ...)
    amount = Column(Float)  #  операции
    fee_amount = Column(Float)  #  комиссии
    timestamp = Column(DateTime, default=datetime.utcnow)
    details = Column(String, nullable=True)  # JSON  (order_id, transaction_hash)

    user = relationship("User", backref="fee_transactions") 