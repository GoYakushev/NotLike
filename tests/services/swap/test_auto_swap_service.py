import pytest
from services.swap.auto_swap_service import AutoSwapService
from core.database.database import Database
from core.database.models import User, AutoSwap
from services.swap.simpleswap_service import SimpleSwapService
from services.wallet.wallet_service import WalletService
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.database.models import Base
import asyncio
from services.notifications.notification_service import NotificationService, NotificationType

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
def auto_swap_service(in_memory_db):
    simpleswap_mock = AsyncMock(spec=SimpleSwapService)
    wallet_service_mock = AsyncMock(spec=WalletService)
    notification_service_mock = AsyncMock(spec=NotificationService)
    #  api_key
    return AutoSwapService(simpleswap_api_key="test_api_key", db=in_memory_db, simpleswap=simpleswap_mock, wallet_service=wallet_service_mock, notification_service=notification_service_mock)

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
async def test_handle_incoming_transfer_success(auto_swap_service, create_test_user, in_memory_db):
    """Тест handle_incoming_transfer: успех."""
    user = create_test_user
    #  WalletService  SimpleSwapService
    auto_swap_service.wallet_service.get_wallet.return_value = MagicMock(address="target_address")
    auto_swap_service.simpleswap.get_estimated_amount.return_value = 0.9  #  сумма
    auto_swap_service.simpleswap.create_exchange.return_value = {"id": "exchange_id"}

    await auto_swap_service.handle_incoming_transfer(user.telegram_id, "SOL", 1.0)

    #  ,   AutoSwap
    session = in_memory_db.SessionLocal()
    auto_swap = session.query(AutoSwap).filter_by(user_id=user.id).first()
    assert auto_swap is not None
    assert auto_swap.from_network == "SOL"
    assert auto_swap.to_network == "TON"
    assert auto_swap.amount == 1.0
    assert auto_swap.exchange_id == "exchange_id"
    assert auto_swap.status == "CREATED"
    session.close()

    auto_swap_service.wallet_service.get_wallet.assert_awaited_once_with(user.telegram_id, "TON")
    auto_swap_service.simpleswap.get_estimated_amount.assert_awaited_once_with("USDT_SOL", "USDT_TON", 1.0)
    auto_swap_service.simpleswap.create_exchange.assert_awaited_once_with(
        "USDT_SOL", "USDT_TON", 1.0, "target_address"
    )

@pytest.mark.asyncio
async def test_handle_incoming_transfer_user_not_found(auto_swap_service):
    """Тест handle_incoming_transfer: пользователь не найден."""
    await auto_swap_service.handle_incoming_transfer(99999, "SOL", 1.0)  #  ID
    auto_swap_service.wallet_service.get_wallet.assert_not_called()
    auto_swap_service.simpleswap.get_estimated_amount.assert_not_called()
    auto_swap_service.simpleswap.create_exchange.assert_not_called()

@pytest.mark.asyncio
async def test_handle_incoming_transfer_no_target_wallet(auto_swap_service, create_test_user):
    """Тест handle_incoming_transfer: нет целевого кошелька."""
    user = create_test_user
    auto_swap_service.wallet_service.get_wallet.return_value = None  #  кошелька
    await auto_swap_service.handle_incoming_transfer(user.telegram_id, "SOL", 1.0)
    auto_swap_service.simpleswap.get_estimated_amount.assert_not_called()
    auto_swap_service.simpleswap.create_exchange.assert_not_called()

@pytest.mark.asyncio
async def test_handle_incoming_transfer_no_estimated_amount(auto_swap_service, create_test_user):
    """Тест handle_incoming_transfer: нет estimated_amount."""
    user = create_test_user
    auto_swap_service.wallet_service.get_wallet.return_value = MagicMock(address="target_address")
    auto_swap_service.simpleswap.get_estimated_amount.return_value = None  #  суммы
    await auto_swap_service.handle_incoming_transfer(user.telegram_id, "SOL", 1.0)
    auto_swap_service.simpleswap.create_exchange.assert_not_called()

@pytest.mark.asyncio
async def test_handle_incoming_transfer_exception(auto_swap_service, create_test_user, monkeypatch):
    """Тест handle_incoming_transfer: исключение."""
    user = create_test_user
    #  ,   
    async def mock_get_wallet(*args, **kwargs):
        raise Exception("Some error")

    monkeypatch.setattr(auto_swap_service.wallet_service, 'get_wallet', mock_get_wallet)

    await auto_swap_service.handle_incoming_transfer(user.telegram_id, "SOL", 1.0)
    #   ,    
    auto_swap_service.simpleswap.get_estimated_amount.assert_not_called()
    auto_swap_service.simpleswap.create_exchange.assert_not_called()

@pytest.mark.asyncio
async def test_monitor_swap_status_completed(auto_swap_service, create_test_user, in_memory_db, monkeypatch):
    """Тест monitor_swap_status: статус COMPLETED."""
    user = create_test_user
    session = in_memory_db.SessionLocal()
    auto_swap = AutoSwap(user_id=user.id, from_network="SOL", to_network="TON", amount=1.0, exchange_id="exchange_id", status="CREATED")
    session.add(auto_swap)
    session.commit()
    session.refresh(auto_swap)

    #  get_exchange_status  notify_swap_completed
    auto_swap_service.simpleswap.get_exchange_status.return_value = {"status": "COMPLETED"}
    # mock_notify_completed = AsyncMock() #  
    # monkeypatch.setattr(auto_swap_service, 'notify_swap_completed', mock_notify_completed) #  

    #  ,     
    with patch('asyncio.sleep', new_callable=AsyncMock):
        await auto_swap_service.monitor_swap_status("exchange_id")

    auto_swap_service.simpleswap.get_exchange_status.assert_awaited_once_with("exchange_id")
    # mock_notify_completed.assert_awaited_once_with(user.telegram_id, 1.0, "SOL", "TON") #  

    #  ,   
    updated_auto_swap = session.query(AutoSwap).filter_by(id=auto_swap.id).first()
    assert updated_auto_swap.status == "COMPLETED"
    session.close()
    auto_swap_service.notification_service.notify.assert_awaited_once_with(
        user_id=user.telegram_id,
        notification_type=NotificationType.SWAP_STATUS,
        message=ANY,  #  ANY,    
        data={'exchange_id': 'exchange_id'}
    )

@pytest.mark.asyncio
async def test_monitor_swap_status_failed(auto_swap_service, create_test_user, in_memory_db, monkeypatch):
    """Тест monitor_swap_status: статус FAILED."""
    user = create_test_user
    session = in_memory_db.SessionLocal()
    auto_swap = AutoSwap(user_id=user.id, from_network="SOL", to_network="TON", amount=1.0, exchange_id="exchange_id", status="CREATED")
    session.add(auto_swap)
    session.commit()
    session.refresh(auto_swap)

    auto_swap_service.simpleswap.get_exchange_status.return_value = {"status": "FAILED"}
    # mock_notify_failed = AsyncMock() #  
    # monkeypatch.setattr(auto_swap_service, 'notify_swap_failed', mock_notify_failed) #  

    with patch('asyncio.sleep', new_callable=AsyncMock):
        await auto_swap_service.monitor_swap_status("exchange_id")

    auto_swap_service.simpleswap.get_exchange_status.assert_awaited_once_with("exchange_id")
    # mock_notify_failed.assert_awaited_once_with(user.telegram_id, 1.0, "SOL", "TON", "FAILED") #  
    updated_auto_swap = session.query(AutoSwap).filter_by(id=auto_swap.id).first()
    assert updated_auto_swap.status == "FAILED"
    session.close()
    auto_swap_service.notification_service.notify.assert_awaited_once_with(
        user_id=user.telegram_id,
        notification_type=NotificationType.SWAP_STATUS,
        message=ANY,
        data={'exchange_id': 'exchange_id'}
    )

@pytest.mark.asyncio
async def test_monitor_swap_status_expired(auto_swap_service, create_test_user, in_memory_db, monkeypatch):
    """Тест monitor_swap_status: статус EXPIRED."""
    user = create_test_user
    session = in_memory_db.SessionLocal()
    auto_swap = AutoSwap(user_id=user.id, from_network="SOL", to_network="TON", amount=1.0, exchange_id="exchange_id", status="CREATED")
    session.add(auto_swap)
    session.commit()
    session.refresh(auto_swap)

    auto_swap_service.simpleswap.get_exchange_status.return_value = {"status": "EXPIRED"}
    # mock_notify_failed = AsyncMock() #  
    # monkeypatch.setattr(auto_swap_service, 'notify_swap_failed', mock_notify_failed) #  

    with patch('asyncio.sleep', new_callable=AsyncMock):
        await auto_swap_service.monitor_swap_status("exchange_id")

    auto_swap_service.simpleswap.get_exchange_status.assert_awaited_once_with("exchange_id")
    # mock_notify_failed.assert_awaited_once_with(user.telegram_id, 1.0, "SOL", "TON", "EXPIRED") #  
    updated_auto_swap = session.query(AutoSwap).filter_by(id=auto_swap.id).first()
    assert updated_auto_swap.status == "EXPIRED"
    session.close()
    auto_swap_service.notification_service.notify.assert_awaited_once_with(
        user_id=user.telegram_id,
        notification_type=NotificationType.SWAP_STATUS,
        message=ANY,
        data={'exchange_id': 'exchange_id'}
    )

@pytest.mark.asyncio
async def test_monitor_swap_status_exception(auto_swap_service, create_test_user, in_memory_db, monkeypatch):
    """Тест monitor_swap_status: исключение."""
    user = create_test_user
    session = in_memory_db.SessionLocal()
    auto_swap = AutoSwap(user_id=user.id, from_network="SOL", to_network="TON", amount=1.0, exchange_id="exchange_id", status="CREATED")
    session.add(auto_swap)
    session.commit()
    session.refresh(auto_swap)

    #  ,   
    async def mock_get_exchange_status(*args, **kwargs):
        raise Exception("Some error")

    monkeypatch.setattr(auto_swap_service.simpleswap, 'get_exchange_status', mock_get_exchange_status)

    with patch('asyncio.sleep', new_callable=AsyncMock):
        await auto_swap_service.monitor_swap_status("exchange_id")

    #   ,    
    auto_swap_service.simpleswap.get_exchange_status.assert_awaited_once_with("exchange_id")
    updated_auto_swap = session.query(AutoSwap).filter_by(id=auto_swap.id).first()
    assert updated_auto_swap.status == "CREATED"  #  меняется
    session.close()

@pytest.mark.asyncio
async def test_notify_swap_completed(auto_swap_service, create_test_user):
    """Тест notify_swap_completed."""
    user = create_test_user
    await auto_swap_service.notify_swap_completed(user.telegram_id, 1.0, "SOL", "TON")
    auto_swap_service.notification_service.notify.assert_awaited_once_with(
        user_id=user.telegram_id,
        notification_type=NotificationType.SWAP_STATUS,
        message="✅ Автоматический обмен 1.0 SOL -> TON завершен.",
        data=None
    )

@pytest.mark.asyncio
async def test_notify_swap_failed(auto_swap_service, create_test_user):
    """Тест notify_swap_failed."""
    user = create_test_user
    await auto_swap_service.notify_swap_failed(user.telegram_id, 1.0, "SOL", "TON", "FAILED")
    auto_swap_service.notification_service.notify.assert_awaited_once_with(
        user_id=user.telegram_id,
        notification_type=NotificationType.SWAP_STATUS,
        message="❌ Автоматический обмен 1.0 SOL -> TON не удался. Причина: FAILED",
        data=None
    )

#  notify_swap_completed  notify_swap_failed
#   ,     ,   .
#   ,     . 