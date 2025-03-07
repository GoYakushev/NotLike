import pytest
from services.exchange.exchange_service import ExchangeService
from core.database.database import Database
from core.database.models import User, ExchangeAccount
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.database.models import Base
import ccxt.async_support as ccxt  #  ccxt.async_support

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
def exchange_service(in_memory_db):
    #  ccxt
    binance_mock = AsyncMock(spec=ccxt.binance)
    bybit_mock = AsyncMock(spec=ccxt.bybit)
    #  
    exchanges = {
        'binance': binance_mock,
        'bybit': bybit_mock
    }
    return ExchangeService(db=in_memory_db, exchanges=exchanges)

@pytest.fixture
def create_test_user(in_memory_db):
    session = in_memory_db.SessionLocal()
    user = User(telegram_id=12345, username="testuser")
    session.add(user)
    session.commit()
    session.refresh(user)
    yield user
    session.delete(user)
    session.commit()
    session.close()

@pytest.mark.asyncio
async def test_add_exchange_account_success(exchange_service, create_test_user, in_memory_db):
    """Тест add_exchange_account: успех."""
    user = create_test_user
    result = await exchange_service.add_exchange_account(user.telegram_id, "binance", "api_key", "api_secret")
    assert result['success'] is True

    session = in_memory_db.SessionLocal()
    account = session.query(ExchangeAccount).filter_by(user_id=user.id).first()
    assert account is not None
    assert account.exchange == "binance"
    assert account.api_key == "api_key"
    assert account.api_secret == "api_secret"
    session.close()

@pytest.mark.asyncio
async def test_add_exchange_account_user_not_found(exchange_service):
    """Тест add_exchange_account: пользователь не найден."""
    result = await exchange_service.add_exchange_account(99999, "binance", "api_key", "api_secret")  #  ID
    assert result['success'] is False
    assert result['error'] == 'Пользователь не найден'

@pytest.mark.asyncio
async def test_add_exchange_account_invalid_exchange(exchange_service, create_test_user):
    """Тест add_exchange_account: неверная биржа."""
    user = create_test_user
    result = await exchange_service.add_exchange_account(user.telegram_id, "invalid_exchange", "api_key", "api_secret")
    assert result['success'] is False
    assert result['error'] == 'Неподдерживаемая биржа'

@pytest.mark.asyncio
async def test_add_exchange_account_exception(exchange_service, create_test_user, monkeypatch):
    """Тест add_exchange_account: исключение."""
    user = create_test_user
    #  ,   
    async def mock_add(*args, **kwargs):
        raise Exception("Some error")

    monkeypatch.setattr(exchange_service.db.SessionLocal, 'add', mock_add)

    result = await exchange_service.add_exchange_account(user.telegram_id, "binance", "api_key", "api_secret")
    assert result['success'] is False
    assert "Some error" in result['error']

@pytest.mark.asyncio
async def test_get_exchange_balance_success(exchange_service, create_test_user, in_memory_db):
    """Тест get_exchange_balance: успех."""
    user = create_test_user
    session = in_memory_db.SessionLocal()
    account = ExchangeAccount(user_id=user.id, exchange="binance", api_key="api_key", api_secret="api_secret")
    session.add(account)
    session.commit()
    session.refresh(account)

    #  fetch_balance
    exchange_service.exchanges['binance'].fetch_balance.return_value = {'total': {'BTC': 1.0, 'USDT': 100.0}}

    result = await exchange_service.get_exchange_balance(user.telegram_id, "binance")
    assert result['success'] is True
    assert result['balance'] == {'BTC': 1.0, 'USDT': 100.0}
    exchange_service.exchanges['binance'].fetch_balance.assert_awaited_once()

@pytest.mark.asyncio
async def test_get_exchange_balance_user_not_found(exchange_service):
    """Тест get_exchange_balance: пользователь не найден."""
    result = await exchange_service.get_exchange_balance(99999, "binance")  #  ID
    assert result['success'] is False
    assert result['error'] == 'Пользователь не найден'

@pytest.mark.asyncio
async def test_get_exchange_balance_account_not_found(exchange_service, create_test_user):
    """Тест get_exchange_balance: аккаунт не найден."""
    user = create_test_user
    result = await exchange_service.get_exchange_balance(user.telegram_id, "binance")  #  аккаунта
    assert result['success'] is False
    assert result['error'] == 'Аккаунт биржи не найден'

@pytest.mark.asyncio
async def test_get_exchange_balance_invalid_exchange(exchange_service, create_test_user, in_memory_db):
    """Тест get_exchange_balance: неверная биржа."""
    user = create_test_user
    session = in_memory_db.SessionLocal()
    account = ExchangeAccount(user_id=user.id, exchange="binance", api_key="api_key", api_secret="api_secret")
    session.add(account)
    session.commit()
    session.refresh(account)

    result = await exchange_service.get_exchange_balance(user.telegram_id, "invalid_exchange")  #  биржа
    assert result['success'] is False
    assert result['error'] == 'Неподдерживаемая биржа'

@pytest.mark.asyncio
async def test_get_exchange_balance_exception(exchange_service, create_test_user, in_memory_db, monkeypatch):
    """Тест get_exchange_balance: исключение."""
    user = create_test_user
    session = in_memory_db.SessionLocal()
    account = ExchangeAccount(user_id=user.id, exchange="binance", api_key="api_key", api_secret="api_secret")
    session.add(account)
    session.commit()
    session.refresh(account)

    #  fetch_balance
    async def mock_fetch_balance(*args, **kwargs):
        raise Exception("Some error")

    monkeypatch.setattr(exchange_service.exchanges['binance'], 'fetch_balance', mock_fetch_balance)

    result = await exchange_service.get_exchange_balance(user.telegram_id, "binance")
    assert result['success'] is False
    assert "Some error" in result['error'] 