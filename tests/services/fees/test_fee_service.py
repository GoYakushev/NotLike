import pytest
from services.fees.fee_service import FeeService
from core.database.database import Database
from core.database.models import User, FeeTransaction
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.database.models import Base

#  aiogram.types.CallbackQuery  aiogram.types.Message
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
def fee_service(in_memory_db):
    return FeeService(in_memory_db)

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

def test_get_current_fees_default(fee_service):
    fees = fee_service.get_current_fees()
    assert fees['p2p'] == 0.015  #  P2P
    assert fees['transfer_address'] == 0.01
    assert fees['transfer_username'] == 0.002
    assert fees['spot'] == 0.01
    assert fees['swap'] == 0.01
    assert fees['copytrading'] == 0.03

@pytest.mark.parametrize("weekday, expected_p2p_fee", [
    (0, 0),  #  (0)
    (4, 0),  #  (4)
    (1, 0.015),  #  (1)
    (2, 0.015),
    (3, 0.015),
    (5, 0.015),
    (6, 0.015),
])
def test_get_current_fees_p2p_special_days(fee_service, weekday, expected_p2p_fee):
    with patch('services.fees.fee_service.datetime') as mock_datetime:
        mock_datetime.utcnow.return_value = datetime(2024, 1, 1) + timedelta(days=weekday)  #  2024  
        fees = fee_service.get_current_fees()
        assert fees['p2p'] == expected_p2p_fee

@pytest.mark.parametrize("weekday, expected_spot_fee", [
    (5, 0.005),  #  (5)
    (6, 0.005),  #  (6)
    (0, 0.01),
    (1, 0.01),
    (2, 0.01),
    (3, 0.01),
    (4, 0.01),
])
def test_get_current_fees_spot_special_days(fee_service, weekday, expected_spot_fee):
    with patch('services.fees.fee_service.datetime') as mock_datetime:
        mock_datetime.utcnow.return_value = datetime(2024, 1, 1) + timedelta(days=weekday)
        fees = fee_service.get_current_fees()
        assert fees['spot'] == expected_spot_fee

@pytest.mark.parametrize("operation_type, amount, expected_fee", [
    ('p2p', 100, 1.5),
    ('transfer_address', 100, 1),
    ('transfer_username', 100, 0.2),
    ('spot', 100, 1),
    ('swap', 100, 1),
    ('copytrading', 100, 3),
    ('unknown', 100, 0),  #  
])
def test_calculate_fee(fee_service, operation_type, amount, expected_fee):
    fee = fee_service.calculate_fee(operation_type, amount)
    assert fee == expected_fee

@pytest.mark.asyncio
async def test_apply_fee_success(fee_service, create_test_user, in_memory_db):
    user = create_test_user
    result = await fee_service.apply_fee(user.telegram_id, 'p2p', 100)
    assert result['success'] is True
    assert result['fee_amount'] == 1.5

    session = in_memory_db.SessionLocal()
    fee_transaction = session.query(FeeTransaction).filter_by(user_id=user.id).first()
    assert fee_transaction is not None
    assert fee_transaction.operation_type == 'p2p'
    assert fee_transaction.amount == 100
    assert fee_transaction.fee_amount == 1.5
    session.close()

@pytest.mark.asyncio
async def test_apply_fee_user_not_found(fee_service):
    result = await fee_service.apply_fee(99999, 'p2p', 100)  #  ID
    assert result['success'] is False
    assert result['error'] == 'Пользователь не найден'

@pytest.mark.asyncio
async def test_apply_fee_exception(fee_service, create_test_user, monkeypatch):
    user = create_test_user
    #  ,   
    async def mock_calculate_fee(*args, **kwargs):
        raise Exception("Some error")

    monkeypatch.setattr(fee_service, 'calculate_fee', mock_calculate_fee)

    result = await fee_service.apply_fee(user.telegram_id, 'p2p', 100)
    assert result['success'] is False
    assert "Some error" in result['error']

@pytest.mark.asyncio
async def test_get_user_fee_stats_success(fee_service, create_test_user, in_memory_db):
    user = create_test_user
    session = in_memory_db.SessionLocal()

    #  FeeTransaction
    fee1 = FeeTransaction(user_id=user.id, operation_type='p2p', amount=100, fee_amount=1.5, timestamp=datetime.utcnow())
    fee2 = FeeTransaction(user_id=user.id, operation_type='spot', amount=200, fee_amount=2.0, timestamp=datetime.utcnow())
    fee3 = FeeTransaction(user_id=user.id, operation_type='swap', amount=50, fee_amount=0.5, timestamp=datetime.utcnow() - timedelta(days=2)) #  2 
    session.add_all([fee1, fee2, fee3])
    session.commit()

    stats = await fee_service.get_user_fee_stats(user.telegram_id, period='day')
    assert stats['success'] is True
    assert stats['total_fees'] == 3.5  # 1.5 + 2.0
    assert stats['p2p_fees'] == 0 #  
    assert stats['spot_fees'] == 0 #  
    assert stats['swap_fees'] == 0 #

    stats_week = await fee_service.get_user_fee_stats(user.telegram_id, period='week')
    assert stats_week['success'] is True
    assert stats_week['total_fees'] == 4.0  # 1.5 + 2.0 + 0.5
    session.close()

@pytest.mark.asyncio
async def test_get_user_fee_stats_user_not_found(fee_service):
    stats = await fee_service.get_user_fee_stats(99999, period='day')
    assert stats['success'] is False
    assert stats['error'] == 'Пользователь не найден'

@pytest.mark.asyncio
async def test_get_user_fee_stats_invalid_period(fee_service, create_test_user):
    user = create_test_user
    stats = await fee_service.get_user_fee_stats(user.telegram_id, period='invalid')
    assert stats['success'] is False
    assert stats['error'] == 'Неверный период'

@pytest.mark.asyncio
async def test_get_fee_message(fee_service):
    with patch('services.fees.fee_service.datetime') as mock_datetime:
        #  (0)
        mock_datetime.utcnow.return_value = datetime(2024, 1, 1)  # 1  2024 - 
        message = fee_service.get_fee_message()
        assert message == "Понедельник день тяжелый... P2P торговля без комиссии! 🎉"

        #  (4)
        mock_datetime.utcnow.return_value = datetime(2024, 1, 5)  # 5  2024 - 
        message = fee_service.get_fee_message()
        assert message == "Трудный день... и на выходные! P2P торговля без комиссии! 🎉"

        #  (5)
        mock_datetime.utcnow.return_value = datetime(2024, 1, 6)  # 6  2024 - 
        message = fee_service.get_fee_message()
        assert message == "Хороших выходных! Комиссия на спотовую торговлю снижена до 0.5%! 🎉"

        #  (2)
        mock_datetime.utcnow.return_value = datetime(2024, 1, 2)  # 2  2024 - 
        message = fee_service.get_fee_message()
        assert message is None 