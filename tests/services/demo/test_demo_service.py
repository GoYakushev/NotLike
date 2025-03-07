import pytest
from services.demo.demo_service import DemoService
from core.database.database import Database
from core.database.models import User, DemoOrder
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.database.models import Base

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
def demo_service(in_memory_db):
    return DemoService(db=in_memory_db)

@pytest.fixture
def create_test_user(in_memory_db):
    session = in_memory_db.SessionLocal()
    user = User(telegram_id=12345, username="testuser", demo_balance=1000.0)
    session.add(user)
    session.commit()
    session.refresh(user)
    yield user
    session.delete(user)
    session.commit()
    session.close()

@pytest.mark.asyncio
async def test_toggle_demo_mode_on(demo_service, create_test_user, in_memory_db):
    """Тест toggle_demo_mode: включение."""
    user = create_test_user
    result = await demo_service.toggle_demo_mode(user.telegram_id)
    assert result['success'] is True
    assert result['demo_mode'] is True
    assert result['balance'] == 1000.0

    session = in_memory_db.SessionLocal()
    updated_user = session.query(User).filter_by(telegram_id=user.telegram_id).first()
    assert updated_user.is_demo_mode is True
    session.close()

@pytest.mark.asyncio
async def test_toggle_demo_mode_off(demo_service, create_test_user, in_memory_db):
    """Тест toggle_demo_mode: выключение."""
    user = create_test_user
    user.is_demo_mode = True  #  включен
    session = in_memory_db.SessionLocal()
    session.add(user)
    session.commit()

    result = await demo_service.toggle_demo_mode(user.telegram_id)
    assert result['success'] is True
    assert result['demo_mode'] is False
    assert result['balance'] == 1000.0

    updated_user = session.query(User).filter_by(telegram_id=user.telegram_id).first()
    assert updated_user.is_demo_mode is False
    session.close()

@pytest.mark.asyncio
async def test_toggle_demo_mode_user_not_found(demo_service):
    """Тест toggle_demo_mode: пользователь не найден."""
    result = await demo_service.toggle_demo_mode(99999)  #  ID
    assert result['success'] is False
    assert result['error'] == 'Пользователь не найден'

@pytest.mark.asyncio
async def test_get_demo_balance(demo_service, create_test_user):
    """Тест get_demo_balance."""
    user = create_test_user
    balance = await demo_service.get_demo_balance(user.telegram_id)
    assert balance == 1000.0

@pytest.mark.asyncio
async def test_get_demo_balance_user_not_found(demo_service):
    """Тест get_demo_balance: пользователь не найден."""
    balance = await demo_service.get_demo_balance(99999)  #  ID
    assert balance is None

@pytest.mark.asyncio
async def test_create_demo_order_success(demo_service, create_test_user, in_memory_db):
    """Тест create_demo_order: успех."""
    user = create_test_user
    result = await demo_service.create_demo_order(user.telegram_id, "SOL", "BUY", 10.0, 50.0)
    assert result['success'] is True
    assert 'order_id' in result

    session = in_memory_db.SessionLocal()
    order = session.query(DemoOrder).filter_by(user_id=user.id).first()
    assert order is not None
    assert order.token == "SOL"
    assert order.side == "BUY"
    assert order.amount == 10.0
    assert order.price == 50.0
    assert order.status == "OPEN"

    #  баланс
    updated_user = session.query(User).filter_by(telegram_id=user.telegram_id).first()
    assert updated_user.demo_balance == 500.0  # 1000 - (10 * 50)
    session.close()

@pytest.mark.asyncio
async def test_create_demo_order_user_not_found(demo_service):
    """Тест create_demo_order: пользователь не найден."""
    result = await demo_service.create_demo_order(99999, "SOL", "BUY", 10.0, 50.0)  #  ID
    assert result['success'] is False
    assert result['error'] == 'Пользователь не найден'

@pytest.mark.asyncio
async def test_create_demo_order_insufficient_funds(demo_service, create_test_user):
    """Тест create_demo_order: недостаточно средств."""
    user = create_test_user
    result = await demo_service.create_demo_order(user.telegram_id, "SOL", "BUY", 100.0, 50.0)  #  5000
    assert result['success'] is False
    assert result['error'] == 'Недостаточно средств на демо-балансе'

@pytest.mark.asyncio
async def test_create_demo_order_exception(demo_service, create_test_user, monkeypatch):
    """Тест create_demo_order: исключение."""
    user = create_test_user
    #  ,   
    async def mock_add(*args, **kwargs):
        raise Exception("Some error")

    monkeypatch.setattr(demo_service.db.SessionLocal, 'add', mock_add)

    result = await demo_service.create_demo_order(user.telegram_id, "SOL", "BUY", 10.0, 50.0)
    assert result['success'] is False
    assert "Some error" in result['error']

@pytest.mark.asyncio
async def test_get_demo_orders(demo_service, create_test_user, in_memory_db):
    """Тест get_demo_orders."""
    user = create_test_user
    session = in_memory_db.SessionLocal()
    order1 = DemoOrder(user_id=user.id, token="SOL", side="BUY", amount=10.0, price=50.0, status="OPEN")
    order2 = DemoOrder(user_id=user.id, token="TON", side="SELL", amount=5.0, price=2.0, status="CLOSED")
    session.add_all([order1, order2])
    session.commit()

    orders = await demo_service.get_demo_orders(user.telegram_id)
    assert len(orders) == 2
    assert orders[0].token == "SOL"
    assert orders[0].side == "BUY"
    assert orders[1].token == "TON"
    assert orders[1].side == "SELL"
    session.close()

@pytest.mark.asyncio
async def test_get_demo_orders_no_orders(demo_service, create_test_user):
    """Тест get_demo_orders: нет ордеров."""
    user = create_test_user
    orders = await demo_service.get_demo_orders(user.telegram_id)
    assert len(orders) == 0 