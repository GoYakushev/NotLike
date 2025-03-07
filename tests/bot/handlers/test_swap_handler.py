import pytest
from aiogram import types
from aiogram.dispatcher import FSMContext
from unittest.mock import AsyncMock, patch, MagicMock
from bot.handlers.swap_handler import (
    show_swap_menu, start_swap, process_swap_amount,
    SwapStates
)
from services.swap.swap_service import SwapService

pytest_plugins = ('pytest_asyncio',)

@pytest.fixture
def swap_service_mock():
    return AsyncMock(spec=SwapService)

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
async def test_show_swap_menu(message_mock):
    """Тест show_swap_menu."""
    await show_swap_menu(message_mock)
    message_mock.answer.assert_called_once()
    args, kwargs = message_mock.answer.call_args
    assert "🔄 Свопы" in args[0]
    assert isinstance(kwargs['reply_markup'], types.InlineKeyboardMarkup)

@pytest.mark.asyncio
async def test_start_swap(callback_query_mock, state_mock):
    """Тест start_swap."""
    callback_query_mock.data = "swap_sol_ton"
    await start_swap(callback_query_mock, state_mock)
    callback_query_mock.message.answer.assert_called_with("Введите количество SOL для обмена:")
    state_mock.set_state.assert_called_with(SwapStates.entering_amount)
    state_mock.update_data.assert_called_with(from_currency="SOL", to_currency="TON")
    callback_query_mock.answer.assert_called_once()

@pytest.mark.asyncio
async def test_start_swap_ton_sol(callback_query_mock, state_mock):
    """Тест start_swap (TON -> SOL)."""
    callback_query_mock.data = "swap_ton_sol"  #  
    await start_swap(callback_query_mock, state_mock)
    callback_query_mock.message.answer.assert_called_with("Введите количество TON для обмена:")  #  
    state_mock.set_state.assert_called_with(SwapStates.entering_amount)
    state_mock.update_data.assert_called_with(from_currency="TON", to_currency="SOL")  #  
    callback_query_mock.answer.assert_called_once()

@pytest.mark.asyncio
async def test_process_swap_amount_success(message_mock, state_mock, swap_service_mock):
    """Тест process_swap_amount: успех."""
    message_mock.text = "10.5"
    state_mock.get_data.return_value = {"from_currency": "SOL", "to_currency": "TON"}
    swap_service_mock.get_swap_price.return_value = {
        'success': True,
        'rate': 2.0,
        'estimated': 21.0
    }

    await process_swap_amount(message_mock, state_mock, swap_service_mock)

    swap_service_mock.get_swap_price.assert_awaited_once_with("SOL", "TON", 10.5)
    message_mock.answer.assert_called_once()
    args, kwargs = message_mock.answer.call_args
    assert "📊 Детали обмена" in args[0]
    assert "От: 10.5 SOL" in args[0]
    assert "К: 21.0 TON" in args[0]
    assert "Курс: 1 SOL = 2.0 TON" in args[0]
    assert isinstance(kwargs['reply_markup'], types.InlineKeyboardMarkup)  #  
    state_mock.finish.assert_not_called() #  ,   

@pytest.mark.asyncio
async def test_process_swap_amount_invalid_input(message_mock, state_mock):
    """Тест process_swap_amount: неверный ввод."""
    message_mock.text = "abc"  #  
    await process_swap_amount(message_mock, state_mock)
    message_mock.answer.assert_called_with("❌ Пожалуйста, введите корректное число")
    state_mock.finish.assert_not_called()

@pytest.mark.asyncio
async def test_process_swap_amount_price_error(message_mock, state_mock, swap_service_mock):
    """Тест process_swap_amount: ошибка при получении цены."""
    message_mock.text = "10.5"
    state_mock.get_data.return_value = {"from_currency": "SOL", "to_currency": "TON"}
    swap_service_mock.get_swap_price.return_value = {'success': False}  #  
    await process_swap_amount(message_mock, state_mock, swap_service_mock)
    message_mock.answer.assert_called_with("❌ Не удалось получить курс обмена")
    state_mock.finish.assert_not_called() 