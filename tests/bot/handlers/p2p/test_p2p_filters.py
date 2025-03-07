import pytest
from aiogram.dispatcher import FSMContext
from unittest.mock import AsyncMock, Mock
from aiogram import types
from bot.handlers.p2p_handler import (
    set_p2p_filters, process_p2p_filter_choice,
    process_filter_base_currency, process_filter_quote_currency,
    process_filter_payment_method
)
from bot.keyboards.p2p_keyboards import p2p_filters_keyboard

#  aiogram.types.CallbackQuery  aiogram.types.Message
pytest_plugins = ('pytest_asyncio',)

@pytest.mark.asyncio
async def test_set_p2p_filters():
    callback_query = AsyncMock(spec=types.CallbackQuery)
    state = AsyncMock(spec=FSMContext)

    await set_p2p_filters(callback_query, state)

    callback_query.message.answer.assert_called_once_with("Выберите фильтры:", reply_markup=p2p_filters_keyboard())
    state.set_state.assert_called_once() #  set_state  
    callback_query.answer.assert_called_once()

@pytest.mark.asyncio
async def test_process_p2p_filter_choice_base():
    callback_query = AsyncMock(spec=types.CallbackQuery)
    callback_query.data = "p2p_filter_base"
    state = AsyncMock(spec=FSMContext)

    await process_p2p_filter_choice(callback_query, state)

    state.set_state.assert_called_once() #  set_state  
    callback_query.message.answer.assert_called_once_with("Введите базовую валюту (например, TON):")
    callback_query.answer.assert_called_once()

@pytest.mark.asyncio
async def test_process_p2p_filter_choice_quote():
    callback_query = AsyncMock(spec=types.CallbackQuery)
    callback_query.data = "p2p_filter_quote"
    state = AsyncMock(spec=FSMContext)

    await process_p2p_filter_choice(callback_query, state)

    state.set_state.assert_called_once() #  set_state
    callback_query.message.answer.assert_called_once_with("Введите котируемую валюту (например, USDT):")
    callback_query.answer.assert_called_once()

@pytest.mark.asyncio
async def test_process_p2p_filter_choice_payment(monkeypatch):
    callback_query = AsyncMock(spec=types.CallbackQuery)
    callback_query.data = "p2p_filter_payment"
    state = AsyncMock(spec=FSMContext)

    #  p2p_payment_method_keyboard
    mock_keyboard = Mock()  #  InlineKeyboardMarkup
    monkeypatch.setattr("bot.handlers.p2p_handler.p2p_payment_method_keyboard", AsyncMock(return_value=mock_keyboard))

    await process_p2p_filter_choice(callback_query, state)

    state.set_state.assert_called_once()
    callback_query.message.answer.assert_called_once_with("Выберите способ оплаты:", reply_markup=mock_keyboard)
    callback_query.answer.assert_called_once()

@pytest.mark.asyncio
async def test_process_p2p_filter_choice_reset():
    callback_query = AsyncMock(spec=types.CallbackQuery)
    callback_query.data = "p2p_filter_reset"
    state = AsyncMock(spec=FSMContext)

    await process_p2p_filter_choice(callback_query, state)

    state.update_data.assert_called_once_with(filter_base_currency=None, filter_quote_currency=None, filter_payment_method=None)
    callback_query.message.answer.assert_called_once_with("Фильтры сброшены.")
    state.finish.assert_called_once()
    #  show_menu
    callback_query.answer.assert_called_once()

@pytest.mark.asyncio
async def test_process_p2p_filter_choice_apply():
    callback_query = AsyncMock(spec=types.CallbackQuery)
    callback_query.data = "p2p_filter_apply"
    state = AsyncMock(spec=FSMContext)

    await process_p2p_filter_choice(callback_query, state)
    callback_query.message.answer.assert_called_once_with("Фильтры применены.")
    state.finish.assert_called_once()
    #  show_menu
    callback_query.answer.assert_called_once()

@pytest.mark.asyncio
async def test_process_filter_base_currency():
    message = AsyncMock(spec=types.Message)
    message.text = "TON"
    state = AsyncMock(spec=FSMContext)

    await process_filter_base_currency(message, state)

    state.update_data.assert_called_once_with(filter_base_currency="TON")
    state.set_state.assert_called_once() #  set_state
    message.answer.assert_called_once()

@pytest.mark.asyncio
async def test_process_filter_quote_currency():
    message = AsyncMock(spec=types.Message)
    message.text = "USDT"
    state = AsyncMock(spec=FSMContext)

    await process_filter_quote_currency(message, state)

    state.update_data.assert_called_once_with(filter_quote_currency="USDT")
    state.set_state.assert_called_once() #  set_state
    message.answer.assert_called_once()

@pytest.mark.asyncio
async def test_process_filter_payment_method(monkeypatch):
    callback_query = AsyncMock(spec=types.CallbackQuery)
    callback_query.data = "p2p_paymentmethod_123"
    state = AsyncMock(spec=FSMContext)

    #  p2p_filters_keyboard
    mock_keyboard = Mock()
    monkeypatch.setattr("bot.handlers.p2p_handler.p2p_filters_keyboard", Mock(return_value=mock_keyboard))

    await process_filter_payment_method(callback_query, state)

    state.update_data.assert_called_once_with(filter_payment_method="123")
    state.set_state.assert_called_once()
    callback_query.message.answer.assert_called_once_with(
        "Фильтр способа оплаты установлен. Выберите следующее действие:",
        reply_markup=mock_keyboard
    )
    callback_query.answer.assert_called_once() 