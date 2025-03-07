import pytest
from aiogram import types
from aiogram.dispatcher import FSMContext
from unittest.mock import AsyncMock, patch, MagicMock
from bot.handlers.support_handler import (
    show_support_menu, create_support_ticket,
    process_ticket_subject, process_ticket_message,
    reply_to_ticket, process_ticket_reply,
    close_ticket_handler, SupportStates
)
from services.support.support_service import SupportService

pytest_plugins = ('pytest_asyncio',)

@pytest.fixture
def support_service_mock():
    return AsyncMock(spec=SupportService)

@pytest.fixture
def message_mock():
    mock = AsyncMock(spec=types.Message)
    mock.from_user.id = 123
    mock.from_user.username = "testuser"
    return mock

@pytest.fixture
def callback_query_mock(message_mock):
    mock = AsyncMock(spec=types.CallbackQuery)
    mock.from_user.id = 123
    mock.message = message_mock
    return mock

@pytest.fixture
def state_mock():
    return AsyncMock(spec=FSMContext)

@pytest.mark.asyncio
async def test_show_support_menu(message_mock):
    """Тест show_support_menu."""
    await show_support_menu(message_mock)
    message_mock.answer.assert_called_once()
    args, kwargs = message_mock.answer.call_args
    assert "💬 Поддержка" in args[0]
    assert isinstance(kwargs['reply_markup'], types.InlineKeyboardMarkup)

@pytest.mark.asyncio
async def test_create_support_ticket(message_mock, state_mock):
    """Тест create_support_ticket."""
    await create_support_ticket(message_mock, state_mock)
    message_mock.answer.assert_called_with("Введите тему обращения:")
    state_mock.set_state.assert_called_with(SupportStates.entering_subject)

@pytest.mark.asyncio
async def test_process_ticket_subject(message_mock, state_mock):
    """Тест process_ticket_subject."""
    message_mock.text = "Test subject"
    await process_ticket_subject(message_mock, state_mock)
    message_mock.answer.assert_called_with("Введите сообщение:")
    state_mock.set_state.assert_called_with(SupportStates.entering_message)
    state_mock.update_data.assert_called_with(subject="Test subject")

@pytest.mark.asyncio
async def test_process_ticket_message_success(message_mock, state_mock, support_service_mock):
    """Тест process_ticket_message: успех."""
    message_mock.text = "Test message"
    state_mock.get_data.return_value = {"subject": "Test subject"}
    support_service_mock.create_ticket.return_value = {'success': True, 'ticket_id': 123}

    await process_ticket_message(message_mock, state_mock, support_service_mock)

    support_service_mock.create_ticket.assert_awaited_once_with(123, "Test subject", "Test message")
    message_mock.answer.assert_called_with("✅ Ваше обращение принято. ID: 123")
    state_mock.finish.assert_called_once()

@pytest.mark.asyncio
async def test_process_ticket_message_failure(message_mock, state_mock, support_service_mock):
    """Тест process_ticket_message: ошибка."""
    message_mock.text = "Test message"
    state_mock.get_data.return_value = {"subject": "Test subject"}
    support_service_mock.create_ticket.return_value = {'success': False, 'error': 'Some error'}

    await process_ticket_message(message_mock, state_mock, support_service_mock)

    support_service_mock.create_ticket.assert_awaited_once_with(123, "Test subject", "Test message")
    message_mock.answer.assert_called_with("❌ Ошибка при создании обращения: Some error")
    state_mock.finish.assert_called_once()

@pytest.mark.asyncio
async def test_reply_to_ticket(message_mock, state_mock):
    """Тест reply_to_ticket."""
    message_mock.text = "/reply 123"  #  ID
    await reply_to_ticket(message_mock, state_mock)
    message_mock.answer.assert_called_with("Введите ответ:")
    state_mock.set_state.assert_called_with(SupportStates.replying_to_ticket)
    state_mock.update_data.assert_called_with(ticket_id=123)

@pytest.mark.asyncio
async def test_reply_to_ticket_invalid_format(message_mock, state_mock):
    """Тест reply_to_ticket: неверный формат."""
    message_mock.text = "/reply"  #  ID
    await reply_to_ticket(message_mock, state_mock)
    message_mock.answer.assert_called_with("Неверный формат. Используйте /reply ticket_id")
    state_mock.set_state.assert_not_called()
    state_mock.update_data.assert_not_called()

@pytest.mark.asyncio
async def test_process_ticket_reply_success(message_mock, state_mock, support_service_mock):
    """Тест process_ticket_reply: успех."""
    message_mock.text = "Test reply"
    state_mock.get_data.return_value = {"ticket_id": 123}
    support_service_mock.add_message_to_ticket.return_value = {'success': True}

    await process_ticket_reply(message_mock, state_mock, support_service_mock)

    support_service_mock.add_message_to_ticket.assert_awaited_once_with(123, 123, "Test reply")
    message_mock.answer.assert_called_with("✅ Ответ добавлен к тикету.")
    state_mock.finish.assert_called_once()

@pytest.mark.asyncio
async def test_process_ticket_reply_failure(message_mock, state_mock, support_service_mock):
    """Тест process_ticket_reply: ошибка."""
    message_mock.text = "Test reply"
    state_mock.get_data.return_value = {"ticket_id": 123}
    support_service_mock.add_message_to_ticket.return_value = {'success': False, 'error': 'Some error'}

    await process_ticket_reply(message_mock, state_mock, support_service_mock)

    support_service_mock.add_message_to_ticket.assert_awaited_once_with(123, 123, "Test reply")
    message_mock.answer.assert_called_with("❌ Ошибка при добавлении ответа: Some error")
    state_mock.finish.assert_called_once()

@pytest.mark.asyncio
async def test_close_ticket_handler_success(message_mock, support_service_mock):
    """Тест close_ticket_handler: успех."""
    message_mock.text = "/close 123"  #  ID
    support_service_mock.close_ticket.return_value = {'success': True}
    await close_ticket_handler(message_mock, support_service_mock)
    support_service_mock.close_ticket.assert_awaited_once_with(123)
    message_mock.answer.assert_called_with("✅ Тикет закрыт.")

@pytest.mark.asyncio
async def test_close_ticket_handler_failure(message_mock, support_service_mock):
    """Тест close_ticket_handler: ошибка."""
    message_mock.text = "/close 123"
    support_service_mock.close_ticket.return_value = {'success': False, 'error': 'Some error'}
    await close_ticket_handler(message_mock, support_service_mock)
    support_service_mock.close_ticket.assert_awaited_once_with(123)
    message_mock.answer.assert_called_with("❌ Ошибка при закрытии тикета: Some error")

@pytest.mark.asyncio
async def test_close_ticket_handler_invalid_format(message_mock):
    """Тест close_ticket_handler: неверный формат."""
    message_mock.text = "/close"  #  ID
    await close_ticket_handler(message_mock)
    message_mock.answer.assert_called_with("Неверный формат. Используйте /close ticket_id") 