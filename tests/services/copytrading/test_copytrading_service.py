import pytest
from services.copytrading.copytrading_service import CopyTradingService
from core.database.database import Database
from core.database.models import User, CopyTrader, CopyTraderFollower, SpotOrder, Wallet
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.database.models import Base
from services.notifications.notification_service import NotificationService, NotificationType
from services.fees.fee_service import FeeService

pytest_plugins = ('pytest_asyncio',)

#  in-memory SQLite
@pytest.fixture(scope="session")
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Database()
    db.SessionLocal = SessionLocal #  
    yield db
    Base.metadata.drop_all(engine)

@pytest.fixture
def copytrading_service(in_memory_db):
    notification_service_mock = AsyncMock(spec=NotificationService)
    fee_service_mock = AsyncMock(spec=FeeService)
    return CopyTradingService(db=in_memory_db, notification_service=notification_service_mock)

@pytest.fixture
async def create_test_user(in_memory_db):
    session = in_memory_db.SessionLocal()
    user = User(telegram_id=12345, username="testuser", balance=500) #  баланс
    #  кошельки
    wallet1 = Wallet(user_id=user.id, network="SOL", balance=300)
    wallet2 = Wallet(user_id=user.id, network="TON", balance=200)
    #  ордера
    order1 = SpotOrder(user_id=user.id, base_currency="SOL", quote_currency="USDT", side="BUY", price=10, quantity=20) # 200
    order2 = SpotOrder(user_id=user.id, base_currency="TON", quote_currency="USDT", side="SELL", price=5, quantity=60) # 300
    session.add_all([user, wallet1, wallet2, order1, order2])
    session.commit()
    session.refresh(user)
    yield user
    session.delete(user)
    session.delete(wallet1)
    session.delete(wallet2)
    session.delete(order1)
    session.delete(order2)
    session.commit()
    session.close()

@pytest.mark.asyncio
async def test_register_as_trader_success(copytrading_service, create_test_user, in_memory_db):
    """Тест register_as_trader: успех."""
    user = create_test_user
    result = await copytrading_service.register_as_trader(user.telegram_id)
    assert result['success'] is True

    session = in_memory_db.SessionLocal()
    trader = session.query(CopyTrader).filter_by(user_id=user.id).first()
    assert trader is not None
    assert trader.is_active is True
    assert trader.total_trades == 0
    assert trader.successful_trades == 0
    session.close()

@pytest.mark.asyncio
async def test_register_as_trader_insufficient_balance(copytrading_service, create_test_user):
    """Тест register_as_trader: недостаточный баланс."""
    user = create_test_user
    user.balance = 200  #  баланс
    session = copytrading_service.db.SessionLocal()
    session.add(user)
    session.commit()
    result = await copytrading_service.register_as_trader(user.telegram_id)
    assert result['success'] is False
    assert result['error'] == 'Недостаточный баланс для регистрации копитрейдером'
    session.close()

@pytest.mark.asyncio
async def test_register_as_trader_insufficient_volume(copytrading_service, create_test_user, in_memory_db):
    """Тест register_as_trader: недостаточный объем торгов."""
    user = create_test_user
    #  ордера,   
    session = in_memory_db.SessionLocal()
    for order in user.spot_orders:
        session.delete(order)
    session.commit()

    result = await copytrading_service.register_as_trader(user.telegram_id)
    assert result['success'] is False
    assert result['error'] == 'Недостаточный объем торгов для регистрации копитрейдером'
    session.close()

@pytest.mark.asyncio
async def test_register_as_trader_user_not_found(copytrading_service):
    """Тест register_as_trader: пользователь не найден."""
    result = await copytrading_service.register_as_trader(99999)  #  ID
    assert result['success'] is False
    assert result['error'] == 'Пользователь не найден'

@pytest.mark.asyncio
async def test_register_as_trader_exception(copytrading_service, create_test_user, monkeypatch):
    """Тест register_as_trader: исключение."""
    user = create_test_user
    #  ,   
    async def mock_add(*args, **kwargs):
        raise Exception("Some error")

    monkeypatch.setattr(copytrading_service.db.SessionLocal, 'add', mock_add)

    result = await copytrading_service.register_as_trader(user.telegram_id)
    assert result['success'] is False
    assert "Some error" in result['error']

@pytest.mark.asyncio
async def test_follow_trader_success(copytrading_service, create_test_user, in_memory_db):
    """Тест follow_trader: успех."""
    user1 = create_test_user
    #  
    session = in_memory_db.SessionLocal()
    user2 = User(telegram_id=67890, username="testtrader")
    trader = CopyTrader(user_id=user2.id)
    session.add_all([user2, trader])
    session.commit()
    session.refresh(user2)
    session.refresh(trader)

    result = await copytrading_service.follow_trader(user1.telegram_id, user2.telegram_id, 100)
    assert result['success'] is True

    follower = session.query(CopyTraderFollower).filter_by(follower_id=user1.id, trader_id=trader.id).first()
    assert follower is not None
    assert follower.active is True
    assert follower.copy_amount == 100
    session.close()

@pytest.mark.asyncio
async def test_follow_trader_follower_not_found(copytrading_service, create_test_user, in_memory_db):
    """Тест follow_trader: follower не найден."""
    #  
    session = in_memory_db.SessionLocal()
    user2 = User(telegram_id=67890, username="testtrader")
    trader = CopyTrader(user_id=user2.id)
    session.add_all([user2, trader])
    session.commit()
    session.refresh(user2)
    session.refresh(trader)

    result = await copytrading_service.follow_trader(99999, user2.telegram_id, 100)  #  follower
    assert result['success'] is False
    assert result['error'] == 'Пользователь не найден'
    session.close()

@pytest.mark.asyncio
async def test_follow_trader_trader_not_found(copytrading_service, create_test_user):
    """Тест follow_trader: трейдер не найден."""
    user1 = create_test_user
    result = await copytrading_service.follow_trader(user1.telegram_id, 99999, 100)  #  trader
    assert result['success'] is False
    assert result['error'] == 'Трейдер не найден'

@pytest.mark.asyncio
async def test_follow_trader_already_following(copytrading_service, create_test_user, in_memory_db):
    """Тест follow_trader: уже подписан."""
    user1 = create_test_user
    #  
    session = in_memory_db.SessionLocal()
    user2 = User(telegram_id=67890, username="testtrader")
    trader = CopyTrader(user_id=user2.id)
    follower = CopyTraderFollower(follower_id=user1.id, trader_id=trader.id, active=True, copy_amount=50)
    session.add_all([user2, trader, follower])
    session.commit()
    session.refresh(user2)
    session.refresh(trader)

    result = await copytrading_service.follow_trader(user1.telegram_id, user2.telegram_id, 100)
    assert result['success'] is False
    assert result['error'] == 'Вы уже подписаны на этого трейдера'
    session.close()

@pytest.mark.asyncio
async def test_follow_trader_exception(copytrading_service, create_test_user, in_memory_db, monkeypatch):
    """Тест follow_trader: исключение."""
    user1 = create_test_user
    #  
    session = in_memory_db.SessionLocal()
    user2 = User(telegram_id=67890, username="testtrader")
    trader = CopyTrader(user_id=user2.id)
    session.add_all([user2, trader])
    session.commit()
    session.refresh(user2)
    session.refresh(trader)

    #  ,   
    async def mock_add(*args, **kwargs):
        raise Exception("Some error")

    monkeypatch.setattr(copytrading_service.db.SessionLocal, 'add', mock_add)

    result = await copytrading_service.follow_trader(user1.telegram_id, user2.telegram_id, 100)
    assert result['success'] is False
    assert "Some error" in result['error']
    session.close()

@pytest.mark.asyncio
async def test_unfollow_trader_success(copytrading_service, create_test_user, in_memory_db):
    """Тест unfollow_trader: успех."""
    user1 = create_test_user
    #  
    session = in_memory_db.SessionLocal()
    user2 = User(telegram_id=67890, username="testtrader")
    trader = CopyTrader(user_id=user2.id)
    follower = CopyTraderFollower(follower_id=user1.id, trader_id=trader.id, active=True, copy_amount=50)
    session.add_all([user2, trader, follower])
    session.commit()
    session.refresh(user2)
    session.refresh(trader)
    session.refresh(follower)

    result = await copytrading_service.unfollow_trader(user1.telegram_id, user2.telegram_id)
    assert result['success'] is True

    #  ,   
    updated_follower = session.query(CopyTraderFollower).filter_by(follower_id=user1.id, trader_id=trader.id).first()
    assert updated_follower.active is False
    session.close()

@pytest.mark.asyncio
async def test_unfollow_trader_follower_not_found(copytrading_service, create_test_user, in_memory_db):
    """Тест unfollow_trader: follower не найден."""
    #  
    session = in_memory_db.SessionLocal()
    user2 = User(telegram_id=67890, username="testtrader")
    trader = CopyTrader(user_id=user2.id)
    session.add_all([user2, trader])
    session.commit()
    session.refresh(user2)
    session.refresh(trader)

    result = await copytrading_service.unfollow_trader(99999, user2.telegram_id)  #  follower
    assert result['success'] is False
    assert result['error'] == 'Пользователь не найден'
    session.close()

@pytest.mark.asyncio
async def test_unfollow_trader_trader_not_found(copytrading_service, create_test_user):
    """Тест unfollow_trader: трейдер не найден."""
    user1 = create_test_user
    result = await copytrading_service.unfollow_trader(user1.telegram_id, 99999)  #  trader
    assert result['success'] is False
    assert result['error'] == 'Трейдер не найден'

@pytest.mark.asyncio
async def test_unfollow_trader_not_following(copytrading_service, create_test_user, in_memory_db):
    """Тест unfollow_trader: не подписан."""
    user1 = create_test_user
    #  
    session = in_memory_db.SessionLocal()
    user2 = User(telegram_id=67890, username="testtrader")
    trader = CopyTrader(user_id=user2.id)
    session.add_all([user2, trader])
    session.commit()
    session.refresh(user2)
    session.refresh(trader)

    result = await copytrading_service.unfollow_trader(user1.telegram_id, user2.telegram_id)
    assert result['success'] is False
    assert result['error'] == 'Вы не подписаны на этого трейдера'
    session.close()

@pytest.mark.asyncio
async def test_unfollow_trader_exception(copytrading_service, create_test_user, in_memory_db, monkeypatch):
    """Тест unfollow_trader: исключение."""
    user1 = create_test_user
    #  
    session = in_memory_db.SessionLocal()
    user2 = User(telegram_id=67890, username="testtrader")
    trader = CopyTrader(user_id=user2.id)
    follower = CopyTraderFollower(follower_id=user1.id, trader_id=trader.id, active=True, copy_amount=50)
    session.add_all([user2, trader, follower])
    session.commit()
    session.refresh(user2)
    session.refresh(trader)
    session.refresh(follower)

    #  ,   
    async def mock_commit(*args, **kwargs):
        raise Exception("Some error")

    monkeypatch.setattr(copytrading_service.db.SessionLocal, 'commit', mock_commit)

    result = await copytrading_service.unfollow_trader(user1.telegram_id, user2.telegram_id)
    assert result['success'] is False
    assert "Some error" in result['error']
    session.close()

@pytest.mark.asyncio
async def test_copy_trades_success(copytrading_service, create_test_user, in_memory_db):
    """Тест copy_trades: успех."""
    user1 = create_test_user  #  трейдер
    #  
    session = in_memory_db.SessionLocal()
    user2 = User(telegram_id=67890, username="testfollower")
    trader = CopyTrader(user_id=user1.id)
    follower_rel = CopyTraderFollower(follower_id=user2.id, trader_id=trader.id, active=True, copy_amount=50)
    #  ордер трейдера
    order = SpotOrder(user_id=user1.id, base_currency="SOL", quote_currency="USDT", side="BUY", price=10, quantity=100, status="OPEN")
    session.add_all([user2, trader, follower_rel, order])
    session.commit()
    session.refresh(user1)
    session.refresh(user2)
    session.refresh(trader)
    session.refresh(follower_rel)
    session.refresh(order)

    await copytrading_service.copy_trades(order)

    #  ,    
    copied_order = session.query(SpotOrder).filter_by(user_id=user2.id).first()
    assert copied_order is not None
    assert copied_order.base_currency == "SOL"
    assert copied_order.quote_currency == "USDT"
    assert copied_order.side == "BUY"
    assert copied_order.price == 10
    assert copied_order.quantity == 50  #  ,   50
    assert copied_order.status == "OPEN"
    session.close()
    copytrading_service.notification_service.notify.assert_awaited_once_with(
        user_id=user2.telegram_id,
        notification_type=NotificationType.ORDER_UPDATE,
        message=ANY,  #  ANY,    
        data={'order_id': copied_order.id}
    )

@pytest.mark.asyncio
async def test_copy_trades_no_followers(copytrading_service, create_test_user, in_memory_db):
    """Тест copy_trades: нет подписчиков."""
    user1 = create_test_user
    session = in_memory_db.SessionLocal()
    trader = CopyTrader(user_id=user1.id)
    order = SpotOrder(user_id=user1.id, base_currency="SOL", quote_currency="USDT", side="BUY", price=10, quantity=100, status="OPEN")
    session.add_all([trader, order])
    session.commit()
    session.refresh(user1)
    session.refresh(trader)
    session.refresh(order)

    await copytrading_service.copy_trades(order)

    #  ,    
    copied_orders = session.query(SpotOrder).filter(SpotOrder.user_id != user1.id).all()
    assert len(copied_orders) == 0  #   
    session.close()

@pytest.mark.asyncio
async def test_copy_trades_inactive_follower(copytrading_service, create_test_user, in_memory_db):
    """Тест copy_trades: неактивный подписчик."""
    user1 = create_test_user
    session = in_memory_db.SessionLocal()
    user2 = User(telegram_id=67890, username="testfollower")
    trader = CopyTrader(user_id=user1.id)
    follower_rel = CopyTraderFollower(follower_id=user2.id, trader_id=trader.id, active=False, copy_amount=50)  #  
    order = SpotOrder(user_id=user1.id, base_currency="SOL", quote_currency="USDT", side="BUY", price=10, quantity=100, status="OPEN")
    session.add_all([user2, trader, follower_rel, order])
    session.commit()
    session.refresh(user1)
    session.refresh(user2)
    session.refresh(trader)
    session.refresh(follower_rel)
    session.refresh(order)

    await copytrading_service.copy_trades(order)

    copied_orders = session.query(SpotOrder).filter(SpotOrder.user_id != user1.id).all()
    assert len(copied_orders) == 0
    session.close()

@pytest.mark.asyncio
async def test_copy_trades_fee_error(copytrading_service, create_test_user, in_memory_db, monkeypatch):
    """Тест copy_trades: ошибка при применении комиссии."""
    user1 = create_test_user
    session = in_memory_db.SessionLocal()
    user2 = User(telegram_id=67890, username="testfollower")
    trader = CopyTrader(user_id=user1.id)
    follower_rel = CopyTraderFollower(follower_id=user2.id, trader_id=trader.id, active=True, copy_amount=50)
    order = SpotOrder(user_id=user1.id, base_currency="SOL", quote_currency="USDT", side="BUY", price=10, quantity=100, status="OPEN")
    session.add_all([user2, trader, follower_rel, order])
    session.commit()
    session.refresh(user1)
    session.refresh(user2)
    session.refresh(trader)
    session.refresh(follower_rel)
    session.refresh(order)

    #  apply_fee
    copytrading_service.fee_service.apply_fee.return_value = {'success': False, 'error': 'Fee error'}

    await copytrading_service.copy_trades(order)

    #  ,    
    copied_orders = session.query(SpotOrder).filter(SpotOrder.user_id != user1.id).all()
    assert len(copied_orders) == 0  #   
    session.close() 