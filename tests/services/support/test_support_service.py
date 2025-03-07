import pytest
from services.support.support_service import SupportService
from core.database.database import Database
from core.database.models import User, SupportTicket, SupportMessage
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
def support_service(in_memory_db):
    notification_service_mock = AsyncMock()  #  
    return SupportService(notification_manager=notification_service_mock, db=in_memory_db)

@pytest.fixture
async def create_test_users(in_memory_db):
    session = in_memory_db.SessionLocal()
    user1 = User(telegram_id=12345, username="user1")
    user2 = User(telegram_id=67890, username="support_agent")  #  
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
async def test_create_ticket_success(support_service, create_test_users, in_memory_db):
    """Тест create_ticket: успех."""
    user, _ = create_test_users
    result = await support_service.create_ticket(user.telegram_id, "Test subject", "Test message")
    assert result['success'] is True
    assert 'ticket_id' in result

    session = in_memory_db.SessionLocal()
    ticket = session.query(SupportTicket).filter_by(user_id=user.id).first()
    assert ticket is not None
    assert ticket.subject == "Test subject"
    assert ticket.status == "OPEN"
    assert len(ticket.messages) == 1
    assert ticket.messages[0].message == "Test message"
    assert ticket.messages[0].sender_id == user.id
    session.close()

@pytest.mark.asyncio
async def test_create_ticket_user_not_found(support_service):
    """Тест create_ticket: пользователь не найден."""
    result = await support_service.create_ticket(99999, "Test subject", "Test message")  #  ID
    assert result['success'] is False
    assert result['error'] == 'Пользователь не найден'

@pytest.mark.asyncio
async def test_create_ticket_exception(support_service, create_test_users, monkeypatch):
    """Тест create_ticket: исключение."""
    user, _ = create_test_users
    #  ,   
    async def mock_add(*args, **kwargs):
        raise Exception("Some error")

    monkeypatch.setattr(support_service.db.SessionLocal, 'add', mock_add)

    result = await support_service.create_ticket(user.telegram_id, "Test subject", "Test message")
    assert result['success'] is False
    assert "Some error" in result['error']

@pytest.mark.asyncio
async def test_get_tickets(support_service, create_test_users, in_memory_db):
    """Тест get_tickets."""
    user, _ = create_test_users
    session = in_memory_db.SessionLocal()
    ticket1 = SupportTicket(user_id=user.id, subject="Subject 1", status="OPEN")
    ticket2 = SupportTicket(user_id=user.id, subject="Subject 2", status="CLOSED")
    session.add_all([ticket1, ticket2])
    session.commit()

    tickets = await support_service.get_tickets()
    assert len(tickets) == 2
    assert tickets[0].subject == "Subject 1"
    assert tickets[1].subject == "Subject 2"
    session.close()

@pytest.mark.asyncio
async def test_get_ticket(support_service, create_test_users, in_memory_db):
    """Тест get_ticket."""
    user, _ = create_test_users
    session = in_memory_db.SessionLocal()
    ticket = SupportTicket(user_id=user.id, subject="Test subject", status="OPEN")
    message = SupportMessage(ticket_id=ticket.id, sender_id=user.id, message="Test message")
    ticket.messages.append(message)
    session.add(ticket)
    session.commit()
    session.refresh(ticket)

    retrieved_ticket = await support_service.get_ticket(ticket.id)
    assert retrieved_ticket is not None
    assert retrieved_ticket.subject == "Test subject"
    assert len(retrieved_ticket.messages) == 1
    assert retrieved_ticket.messages[0].message == "Test message"
    session.close()

@pytest.mark.asyncio
async def test_get_ticket_not_found(support_service):
    """Тест get_ticket: тикет не найден."""
    ticket = await support_service.get_ticket(99999)  #  ID
    assert ticket is None

@pytest.mark.asyncio
async def test_add_message_to_ticket_success(support_service, create_test_users, in_memory_db):
    """Тест add_message_to_ticket: успех."""
    user, agent = create_test_users
    session = in_memory_db.SessionLocal()
    ticket = SupportTicket(user_id=user.id, subject="Test subject", status="OPEN")
    session.add(ticket)
    session.commit()
    session.refresh(ticket)

    #  от пользователя
    result = await support_service.add_message_to_ticket(ticket.id, user.telegram_id, "User message")
    assert result['success'] is True

    #  от агента
    result = await support_service.add_message_to_ticket(ticket.id, agent.telegram_id, "Agent message")
    assert result['success'] is True

    updated_ticket = session.query(SupportTicket).filter_by(id=ticket.id).first()
    assert len(updated_ticket.messages) == 2
    assert updated_ticket.messages[0].message == "User message"
    assert updated_ticket.messages[0].sender_id == user.id
    assert updated_ticket.messages[1].message == "Agent message"
    assert updated_ticket.messages[1].sender_id == agent.id
    session.close()

@pytest.mark.asyncio
async def test_add_message_to_ticket_ticket_not_found(support_service, create_test_users):
    """Тест add_message_to_ticket: тикет не найден."""
    user, _ = create_test_users
    result = await support_service.add_message_to_ticket(99999, user.telegram_id, "Test message")  #  ID
    assert result['success'] is False
    assert result['error'] == 'Тикет не найден'

@pytest.mark.asyncio
async def test_add_message_to_ticket_user_not_found(support_service, create_test_users, in_memory_db):
    """Тест add_message_to_ticket: пользователь не найден."""
    user, _ = create_test_users
    session = in_memory_db.SessionLocal()
    ticket = SupportTicket(user_id=user.id, subject="Test subject", status="OPEN")
    session.add(ticket)
    session.commit()
    session.refresh(ticket)

    result = await support_service.add_message_to_ticket(ticket.id, 99999, "Test message")  #  ID
    assert result['success'] is False
    assert result['error'] == 'Пользователь не найден'

@pytest.mark.asyncio
async def test_add_message_to_ticket_exception(support_service, create_test_users, in_memory_db, monkeypatch):
    """Тест add_message_to_ticket: исключение."""
    user, _ = create_test_users
    session = in_memory_db.SessionLocal()
    ticket = SupportTicket(user_id=user.id, subject="Test subject", status="OPEN")
    session.add(ticket)
    session.commit()
    session.refresh(ticket)

    #  ,   
    async def mock_add(*args, **kwargs):
        raise Exception("Some error")

    monkeypatch.setattr(support_service.db.SessionLocal, 'add', mock_add)

    result = await support_service.add_message_to_ticket(ticket.id, user.telegram_id, "Test message")
    assert result['success'] is False
    assert "Some error" in result['error']

@pytest.mark.asyncio
async def test_close_ticket_success(support_service, create_test_users, in_memory_db):
    """Тест close_ticket: успех."""
    user, _ = create_test_users
    session = in_memory_db.SessionLocal()
    ticket = SupportTicket(user_id=user.id, subject="Test subject", status="OPEN")
    session.add(ticket)
    session.commit()
    session.refresh(ticket)

    result = await support_service.close_ticket(ticket.id)
    assert result['success'] is True

    updated_ticket = session.query(SupportTicket).filter_by(id=ticket.id).first()
    assert updated_ticket.status == "CLOSED"
    session.close()

@pytest.mark.asyncio
async def test_close_ticket_ticket_not_found(support_service):
    """Тест close_ticket: тикет не найден."""
    result = await support_service.close_ticket(99999)  #  ID
    assert result['success'] is False
    assert result['error'] == 'Тикет не найден'

@pytest.mark.asyncio
async def test_close_ticket_exception(support_service, create_test_users, in_memory_db, monkeypatch):
    """Тест close_ticket: исключение."""
    user, _ = create_test_users
    session = in_memory_db.SessionLocal()
    ticket = SupportTicket(user_id=user.id, subject="Test subject", status="OPEN")
    session.add(ticket)
    session.commit()
    session.refresh(ticket)

    #  ,   
    async def mock_commit(*args, **kwargs):
        raise Exception("Some error")

    monkeypatch.setattr(support_service.db.SessionLocal, 'commit', mock_commit)

    result = await support_service.close_ticket(ticket.id)
    assert result['success'] is False
    assert "Some error" in result['error'] 