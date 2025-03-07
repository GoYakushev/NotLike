import pytest
from services.referral.referral_service import ReferralService
from core.database.database import Database
from core.database.models import User, ReferralProgram, ReferralEarning
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.database.models import Base
from datetime import datetime

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
def referral_service(in_memory_db):
    notification_service_mock = AsyncMock()  #  
    return ReferralService(notification_manager=notification_service_mock, db=in_memory_db)

@pytest.fixture
async def create_test_users(in_memory_db):
    session = in_memory_db.SessionLocal()
    user1 = User(telegram_id=12345, username="referrer")
    user2 = User(telegram_id=67890, username="referred")
    session.add_all([user1, user2])
    session.commit()
    session.refresh(user1)
    session.refresh(user2)
    yield user1, user2
    session.delete(user1)
    session.delete(user2)
    session.commit()
    session.close()

@pytest.mark.asyncio
async def test_create_referral_link(referral_service, create_test_users):
    """Тест create_referral_link."""
    referrer, _ = create_test_users
    link = await referral_service.create_referral_link(referrer.telegram_id)
    assert link is not None
    assert f"ref_{referrer.telegram_id}_" in link  #  ID

@pytest.mark.asyncio
async def test_create_referral_link_user_not_found(referral_service):
    """Тест create_referral_link: пользователь не найден."""
    link = await referral_service.create_referral_link(99999)  #  ID
    assert link is None

@pytest.mark.asyncio
async def test_apply_referral_link_success(referral_service, create_test_users, in_memory_db):
    """Тест apply_referral_link: успех."""
    referrer, referred = create_test_users
    link = await referral_service.create_referral_link(referrer.telegram_id)

    await referral_service.apply_referral_link(link, referred.telegram_id)

    session = in_memory_db.SessionLocal()
    updated_referred = session.query(User).filter_by(telegram_id=referred.telegram_id).first()
    assert updated_referred.referral_id == referrer.id
    session.close()

@pytest.mark.asyncio
async def test_apply_referral_link_invalid_link(referral_service, create_test_users):
    """Тест apply_referral_link: неверная ссылка."""
    _, referred = create_test_users
    await referral_service.apply_referral_link("invalid_link", referred.telegram_id)
    #   ,    
    assert referred.referral_id is None

@pytest.mark.asyncio
async def test_apply_referral_link_referrer_not_found(referral_service, create_test_users):
    """Тест apply_referral_link: referrer не найден."""
    _, referred = create_test_users
    link = "ref_99999_abc"  #  ID
    await referral_service.apply_referral_link(link, referred.telegram_id)
    assert referred.referral_id is None

@pytest.mark.asyncio
async def test_apply_referral_link_referred_not_found(referral_service, create_test_users):
    """Тест apply_referral_link: referred не найден."""
    referrer, _ = create_test_users
    link = await referral_service.create_referral_link(referrer.telegram_id)
    await referral_service.apply_referral_link(link, 99999)  #  ID

@pytest.mark.asyncio
async def test_apply_referral_link_already_referred(referral_service, create_test_users, in_memory_db):
    """Тест apply_referral_link: уже есть реферер."""
    referrer, referred = create_test_users
    link = await referral_service.create_referral_link(referrer.telegram_id)
    #  
    session = in_memory_db.SessionLocal()
    referred.referral_id = referrer.id
    session.add(referred)
    session.commit()

    await referral_service.apply_referral_link(link, referred.telegram_id)

    #   ,    
    updated_referred = session.query(User).filter_by(telegram_id=referred.telegram_id).first()
    assert updated_referred.referral_id == referrer.id  #  меняется
    session.close()

@pytest.mark.asyncio
async def test_get_referral_stats(referral_service, create_test_users, in_memory_db):
    """Тест get_referral_stats."""
    referrer, referred = create_test_users
    #  
    session = in_memory_db.SessionLocal()
    referred.referral_id = referrer.id
    referred.is_premium = True  #  
    session.add(referred)
    session.commit()

    stats = await referral_service.get_referral_stats(referrer.telegram_id)
    assert stats['total_referrals'] == 1
    assert stats['active_referrals'] == 1  #  
    assert stats['total_earned'] == 0.0  #   

@pytest.mark.asyncio
async def test_get_referral_stats_no_referrals(referral_service, create_test_users):
    """Тест get_referral_stats: нет рефералов."""
    referrer, _ = create_test_users
    stats = await referral_service.get_referral_stats(referrer.telegram_id)
    assert stats['total_referrals'] == 0
    assert stats['active_referrals'] == 0
    assert stats['total_earned'] == 0.0

@pytest.mark.asyncio
async def test_get_referral_stats_user_not_found(referral_service):
    """Тест get_referral_stats: пользователь не найден."""
    stats = await referral_service.get_referral_stats(99999)  #  ID
    assert stats is None

@pytest.mark.asyncio
async def test_add_referral_earnings(referral_service, create_test_users, in_memory_db):
    """Тест add_referral_earnings."""
    referrer, referred = create_test_users
    await referral_service.add_referral_earnings(referrer.telegram_id, referred.telegram_id, 10.0, "p2p")

    session = in_memory_db.SessionLocal()
    earnings = session.query(ReferralEarning).filter_by(referrer_id=referrer.id).all()
    assert len(earnings) == 1
    assert earnings[0].referred_id == referred.id
    assert earnings[0].amount == 10.0
    assert earnings[0].earning_type == "p2p"
    session.close()

@pytest.mark.asyncio
async def test_add_referral_earnings_referrer_not_found(referral_service, create_test_users):
    """Тест add_referral_earnings: referrer не найден."""
    _, referred = create_test_users
    #  ,   
    await referral_service.add_referral_earnings(99999, referred.telegram_id, 10.0, "p2p")

@pytest.mark.asyncio
async def test_add_referral_earnings_referred_not_found(referral_service, create_test_users):
    """Тест add_referral_earnings: referred не найден."""
    referrer, _ = create_test_users
    #  ,   
    await referral_service.add_referral_earnings(referrer.telegram_id, 99999, 10.0, "p2p")

@pytest.mark.asyncio
async def test_add_referral_earnings_exception(referral_service, create_test_users, monkeypatch):
    """Тест add_referral_earnings: исключение."""
    referrer, referred = create_test_users
    #  ,   
    async def mock_add(*args, **kwargs):
        raise Exception("Some error")

    monkeypatch.setattr(referral_service.db.SessionLocal, 'add', mock_add)

    await referral_service.add_referral_earnings(referrer.telegram_id, referred.telegram_id, 10.0, "p2p")
    #   ,    
``` 