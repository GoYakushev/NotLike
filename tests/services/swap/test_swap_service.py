import pytest
from services.swap.swap_service import SwapService
from core.database.database import Database
from core.database.models import User, SwapOrder
from unittest.mock import AsyncMock, patch, MagicMock
from decimal import Decimal
from services.dex.orca_service import OrcaService
from services.dex.stonfi_service import StonFiService
from services.wallet.wallet_service import WalletService
from services.fees.fee_service import FeeService
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
def swap_service(in_memory_db):
    #  моки для зависимостей
    orca_mock = AsyncMock(spec=OrcaService)
    stonfi_mock = AsyncMock(spec=StonFiService)
    wallet_service_mock = AsyncMock(spec=WalletService)
    fee_service_mock = AsyncMock(spec=FeeService)
    notification_service_mock = AsyncMock()

    return SwapService(in_memory_db, notification_service_mock)

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
async def test_get_swap_price_orca(swap_service):
    """Тест get_swap_price (Orca)."""
    with patch('services.swap.swap_service.OrcaService.get_price', new_callable=AsyncMock) as mock_get_price:
        mock_get_price.return_value = 10.0  #  цена
        result = await swap_service.get_swap_price("SOL_SOL", "USDT_SOL", 1.0)

    assert result['success'] is True
    assert result['price'] == 10.0
    assert result['dex'] == 'ORCA'
    #  комиссии (0.3% DEX + 1% bot)
    assert result['dex_fee'] == 1.0 * 0.003
    assert result['bot_fee'] == 1.0 * 0.01
    assert result['total_fee'] == 1.0 * 0.003 + 1.0 * 0.01
    assert result['estimated_amount'] == (1.0 - 1.0 * 0.003 - 1.0 * 0.01) * 10.0
    mock_get_price.assert_awaited_once_with("SOL_SOL", "USDT_SOL")

@pytest.mark.asyncio
async def test_get_swap_price_stonfi(swap_service):
    """Тест get_swap_price (Ston.fi)."""
    with patch('services.swap.swap_service.StonFiService.get_price', new_callable=AsyncMock) as mock_get_price:
        mock_get_price.return_value = 2.0
        result = await swap_service.get_swap_price("TON_TON", "USDT_TON", 5.0)

    assert result['success'] is True
    assert result['price'] == 2.0
    assert result['dex'] == 'STONFI'
    assert result['dex_fee'] == 5.0 * 0.003
    assert result['bot_fee'] == 5.0 * 0.01
    assert result['total_fee'] == 5.0 * 0.003 + 5.0 * 0.01
    assert result['estimated_amount'] == (5.0 - 5.0 * 0.003 - 5.0 * 0.01) * 2.0
    mock_get_price.assert_awaited_once_with("TON_TON", "USDT_TON")

@pytest.mark.asyncio
async def test_get_swap_price_no_price(swap_service):
    """Тест get_swap_price: цена не получена."""
    with patch('services.swap.swap_service.OrcaService.get_price', new_callable=AsyncMock) as mock_get_price:
        mock_get_price.return_value = None  #  цены
        result = await swap_service.get_swap_price("SOL_SOL", "USDT_SOL", 1.0)

    assert result is None
    mock_get_price.assert_awaited_once_with("SOL_SOL", "USDT_SOL")

@pytest.mark.asyncio
async def test_get_swap_price_exception(swap_service):
    """Тест get_swap_price: исключение."""
    with patch('services.swap.swap_service.OrcaService.get_price', side_effect=Exception("Some error")):
        result = await swap_service.get_swap_price("SOL_SOL", "USDT_SOL", 1.0)

    assert result['success'] is False
    assert "Some error" in result['error']

@pytest.mark.asyncio
async def test_create_swap_success(swap_service, create_test_user, in_memory_db):
    """Тест create_swap: успех."""
    user = create_test_user
    #  get_swap_price, apply_fee  create_swap_transaction
    with patch('services.swap.swap_service.SwapService.get_swap_price', new_callable=AsyncMock) as mock_get_price, \
         patch('services.swap.swap_service.FeeService.apply_fee', new_callable=AsyncMock) as mock_apply_fee, \
         patch('services.swap.swap_service.OrcaService.create_swap_transaction', new_callable=AsyncMock) as mock_create_tx, \
         patch('services.swap.swap_service.WalletService.get_wallet', new_callable=AsyncMock) as mock_get_wallet:

        mock_get_price.return_value = {'success': True, 'price': 10.0, 'dex': 'ORCA'}
        mock_apply_fee.return_value = {'success': True}
        mock_create_tx.return_value = "transaction_data"
        mock_get_wallet.return_value = MagicMock() #  Wallet

        result = await swap_service.create_swap(user.telegram_id, "SOL_SOL", "USDT_SOL", 1.0)

    assert result['success'] is True
    assert 'order_id' in result
    assert result['transaction'] == "transaction_data"

    #  ,   SwapOrder
    session = in_memory_db.SessionLocal()
    order = session.query(SwapOrder).filter_by(user_id=user.id).first()
    assert order is not None
    assert order.from_token == "SOL_SOL"
    assert order.to_token == "USDT_SOL"
    assert order.amount == 1.0
    assert order.price == 10.0
    assert order.status == 'PENDING'
    session.close()

    mock_get_price.assert_awaited_once_with("SOL_SOL", "USDT_SOL", 1.0)
    mock_apply_fee.assert_awaited_once_with(user.telegram_id, 'swap', 1.0)
    mock_create_tx.assert_awaited_once_with("SOL_SOL", "USDT_SOL", 1.0, ANY) #  Wallet
    mock_get_wallet.assert_awaited_once_with(user.telegram_id, 'SOL')

@pytest.mark.asyncio
async def test_create_swap_user_not_found(swap_service):
    """Тест create_swap: пользователь не найден."""
    result = await swap_service.create_swap(99999, "SOL_SOL", "USDT_SOL", 1.0)  #  ID
    assert result['success'] is False
    assert result['error'] == 'Пользователь не найден'

@pytest.mark.asyncio
async def test_create_swap_price_error(swap_service, create_test_user):
    """Тест create_swap: ошибка при получении цены."""
    user = create_test_user
    with patch('services.swap.swap_service.SwapService.get_swap_price', new_callable=AsyncMock) as mock_get_price:
        mock_get_price.return_value = {'success': False, 'error': 'Price error'}
        result = await swap_service.create_swap(user.telegram_id, "SOL_SOL", "USDT_SOL", 1.0)

    assert result['success'] is False
    assert result['error'] == 'Price error'

@pytest.mark.asyncio
async def test_create_swap_fee_error(swap_service, create_test_user):
    """Тест create_swap: ошибка при применении комиссии."""
    user = create_test_user
    with patch('services.swap.swap_service.SwapService.get_swap_price', new_callable=AsyncMock) as mock_get_price, \
         patch('services.swap.swap_service.FeeService.apply_fee', new_callable=AsyncMock) as mock_apply_fee:

        mock_get_price.return_value = {'success': True, 'price': 10.0, 'dex': 'ORCA'}
        mock_apply_fee.return_value = {'success': False, 'error': 'Fee error'}  #  ошибка
        result = await swap_service.create_swap(user.telegram_id, "SOL_SOL", "USDT_SOL", 1.0)

    assert result['success'] is False
    assert result['error'] == 'Fee error'

@pytest.mark.asyncio
async def test_create_swap_exception(swap_service, create_test_user, monkeypatch):
    """Тест create_swap: общее исключение."""
    user = create_test_user
    #  ,   
    async def mock_get_swap_price(*args, **kwargs):
        raise Exception("Some error")

    monkeypatch.setattr(swap_service, 'get_swap_price', mock_get_swap_price)

    result = await swap_service.create_swap(user.telegram_id, "SOL_SOL", "USDT_SOL", 1.0)
    assert result['success'] is False
    assert "Some error" in result['error'] 