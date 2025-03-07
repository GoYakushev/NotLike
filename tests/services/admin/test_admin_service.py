import pytest
from services.admin.admin_service import AdminService
from core.database.database import Database
from core.database.models import User, Admin, AdminLog
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
def admin_service(in_memory_db):
    return AdminService(db=in_memory_db)

@pytest.fixture
async def create_test_users(in_memory_db):
    session = in_memory_db.SessionLocal()
    user1 = User(telegram_id=12345, username="user1")
    user2 = User(telegram_id=67890, username="admin", is_admin=True)  #  админ
    admin = Admin(user_id=user2.id) #  
    session.add_all([user1, user2, admin])
    session.commit()
    session.refresh(user1)
    session.refresh(user2)
    yield user1, user2
    session.delete(user1)
    session.delete(user2)
    session.delete(admin)
    session.commit()
    session.close()

@pytest.mark.asyncio
async def test_is_admin_true(admin_service, create_test_users):
    """Тест is_admin: True."""
    _, admin_user = create_test_users
    is_admin = await admin_service.is_admin(admin_user.telegram_id)
    assert is_admin is True

@pytest.mark.asyncio
async def test_is_admin_false(admin_service, create_test_users):
    """Тест is_admin: False."""
    user, _ = create_test_users
    is_admin = await admin_service.is_admin(user.telegram_id)
    assert is_admin is False

@pytest.mark.asyncio
async def test_is_admin_user_not_found(admin_service):
    """Тест is_admin: пользователь не найден."""
    is_admin = await admin_service.is_admin(99999)  #  ID
    assert is_admin is False

@pytest.mark.asyncio
async def test_add_admin_log(admin_service, create_test_users, in_memory_db):
    """Тест add_admin_log."""
    _, admin_user = create_test_users
    await admin_service.add_admin_log(admin_user.telegram_id, "Test action", "Test details")

    session = in_memory_db.SessionLocal()
    log = session.query(AdminLog).filter_by(admin_id=admin_user.id).first()
    assert log is not None
    assert log.action == "Test action"
    assert log.details == "Test details"
    session.close()

@pytest.mark.asyncio
async def test_add_admin_log_admin_not_found(admin_service, create_test_users):
    """Тест add_admin_log: админ не найден."""
    user, _ = create_test_users
    #   ,    
    await admin_service.add_admin_log(user.telegram_id, "Test action", "Test details")

@pytest.mark.asyncio
async def test_add_admin_log_exception(admin_service, create_test_users, monkeypatch):
    """Тест add_admin_log: исключение."""
    _, admin_user = create_test_users
    #  ,   
    async def mock_add(*args, **kwargs):
        raise Exception("Some error")

    monkeypatch.setattr(admin_service.db.SessionLocal, 'add', mock_add)

    await admin_service.add_admin_log(admin_user.telegram_id, "Test action", "Test details")
    #   ,    

@pytest.mark.asyncio
async def test_get_all_users(admin_service, create_test_users, in_memory_db):
    """Тест get_all_users."""
    users = await admin_service.get_all_users()
    assert len(users) == 2  #   

@pytest.mark.asyncio
async def test_get_user_by_id(admin_service, create_test_users, in_memory_db):
    """Тест get_user_by_id."""
    user, _ = create_test_users
    retrieved_user = await admin_service.get_user_by_id(user.telegram_id)
    assert retrieved_user is not None
    assert retrieved_user.username == "user1"

@pytest.mark.asyncio
async def test_get_user_by_id_not_found(admin_service):
    """Тест get_user_by_id: пользователь не найден."""
    user = await admin_service.get_user_by_id(99999)  #  ID
    assert user is None

@pytest.mark.asyncio
async def test_block_user_success(admin_service, create_test_users, in_memory_db):
    """Тест block_user: успех."""
    user, _ = create_test_users
    result = await admin_service.block_user(user.telegram_id)
    assert result is True

    session = in_memory_db.SessionLocal()
    updated_user = session.query(User).filter_by(telegram_id=user.telegram_id).first()
    assert updated_user.is_blocked is True
    session.close()

@pytest.mark.asyncio
async def test_block_user_not_found(admin_service):
    """Тест block_user: пользователь не найден."""
    result = await admin_service.block_user(99999)  #  ID
    assert result is False

@pytest.mark.asyncio
async def test_block_user_exception(admin_service, create_test_users, in_memory_db, monkeypatch):
    """Тест block_user: исключение."""
    user, _ = create_test_users
    #  ,   
    async def mock_commit(*args, **kwargs):
        raise Exception("Some error")

    monkeypatch.setattr(admin_service.db.SessionLocal, 'commit', mock_commit)

    result = await admin_service.block_user(user.telegram_id)
    assert result is False

@pytest.mark.asyncio
async def test_unblock_user_success(admin_service, create_test_users, in_memory_db):
    """Тест unblock_user: успех."""
    user, _ = create_test_users
    user.is_blocked = True  #  
    session = in_memory_db.SessionLocal()
    session.add(user)
    session.commit()

    result = await admin_service.unblock_user(user.telegram_id)
    assert result is True

    updated_user = session.query(User).filter_by(telegram_id=user.telegram_id).first()
    assert updated_user.is_blocked is False
    session.close()

@pytest.mark.asyncio
async def test_unblock_user_not_found(admin_service):
    """Тест unblock_user: пользователь не найден."""
    result = await admin_service.unblock_user(99999)  #  ID
    assert result is False

@pytest.mark.asyncio
async def test_unblock_user_exception(admin_service, create_test_users, in_memory_db, monkeypatch):
    """Тест unblock_user: исключение."""
    user, _ = create_test_users
    user.is_blocked = True
    session = in_memory_db.SessionLocal()
    session.add(user)
    session.commit()

    #  ,   
    async def mock_commit(*args, **kwargs):
        raise Exception("Some error")

    monkeypatch.setattr(admin_service.db.SessionLocal, 'commit', mock_commit)

    result = await admin_service.unblock_user(user.telegram_id)
    assert result is False 