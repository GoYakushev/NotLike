import pytest
from aiogram import types
from aiogram.dispatcher import FSMContext
from unittest.mock import AsyncMock, patch, MagicMock
from bot.handlers.demo_handler import (
    show_demo_menu, toggle_demo_mode, show_demo_balance,
    show_demo_orders, start_demo_trade, process_demo_token,
    process_demo_side, process_demo_amount, process_demo_price,
    confirm_demo_order, DemoStates
)
from services.demo.demo_service import DemoService

pytest_plugins = ('pytest_asyncio',)

@pytest.fixture
def demo_service_mock():
    return AsyncMock(spec=DemoService)

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
async def test_show_demo_menu(message_mock):
    """Тест show_demo_menu."""
    await show_demo_menu(message_mock)
    message_mock.answer.assert_called_once()
    args, kwargs = message_mock.answer.call_args
    assert "🎮 Демо-торговля" in args[0]
    assert isinstance(kwargs['reply_markup'], types.InlineKeyboardMarkup)

@pytest.mark.asyncio
async def test_toggle_demo_mode_success(callback_query_mock, demo_service_mock):
    """Тест toggle_demo_mode: успех."""
    demo_service_mock.toggle_demo_mode.return_value = {'success': True, 'demo_mode': True, 'balance': 1000.0}
    await toggle_demo_mode(callback_query_mock, demo_service_mock)
    demo_service_mock.toggle_demo_mode.assert_awaited_once_with(123)
    callback_query_mock.message.answer.assert_called_with("🔄 Демо-режим включен ✅\n💰 Баланс: $1,000.00")

@pytest.mark.asyncio
async def test_toggle_demo_mode_failure(callback_query_mock, demo_service_mock):
    """Тест toggle_demo_mode: ошибка."""
    demo_service_mock.toggle_demo_mode.return_value = {'success': False, 'error': 'Some error'}
    await toggle_demo_mode(callback_query_mock, demo_service_mock)
    demo_service_mock.toggle_demo_mode.assert_awaited_once_with(123)
    callback_query_mock.message.answer.assert_called_with("❌ Ошибка: Some error")

@pytest.mark.asyncio
async def test_show_demo_balance(message_mock, demo_service_mock):
    """Тест show_demo_balance."""
    demo_service_mock.get_demo_balance.return_value = 1234.56
    await show_demo_balance(message_mock, demo_service_mock)
    demo_service_mock.get_demo_balance.assert_awaited_once_with(123)
    message_mock.answer.assert_called_with("💰 Ваш демо-баланс: $1,234.56")

@pytest.mark.asyncio
async def test_show_demo_orders(message_mock, demo_service_mock):
    """Тест show_demo_orders."""
    #  
    order1 = MagicMock()
    order1.token = "SOL"
    order1.side = "BUY"
    order1.amount = 10.0
    order1.price = 50.0
    order1.status = "OPEN"
    order2 = MagicMock()
    order2.token = "TON"
    order2.side = "SELL"
    order2.amount = 5.0
    order2.price = 2.0
    order2.status = "CLOSED"
    demo_service_mock.get_demo_orders.return_value = [order1, order2]

    await show_demo_orders(message_mock, demo_service_mock)

    demo_service_mock.get_demo_orders.assert_awaited_once_with(123)
    message_mock.answer.assert_called_once()
    args, _ = message_mock.answer.call_args
    assert "📊 Ваши демо-ордера" in args[0]
    assert "Токен: SOL" in args[0]
    assert "Сторона: BUY" in args[0]
    assert "Количество: 10.0" in args[0]
    assert "Цена: 50.0" in args[0]
    assert "Статус: OPEN" in args[0]
    assert "Токен: TON" in args[0]
    assert "Сторона: SELL" in args[0]
    assert "Количество: 5.0" in args[0]
    assert "Цена: 2.0" in args[0]
    assert "Статус: CLOSED" in args[0]

@pytest.mark.asyncio
async def test_show_demo_orders_no_orders(message_mock, demo_service_mock):
    """Тест show_demo_orders: нет ордеров."""
    demo_service_mock.get_demo_orders.return_value = []  #  ордеров
    await show_demo_orders(message_mock, demo_service_mock)
    demo_service_mock.get_demo_orders.assert_awaited_once_with(123)
    message_mock.answer.assert_called_with("У вас нет демо-ордеров.")

@pytest.mark.asyncio
async def test_start_demo_trade(message_mock, state_mock):
    """Тест start_demo_trade."""
    await start_demo_trade(message_mock, state_mock)
    message_mock.answer.assert_called_with("Введите токен (например, SOL):")
    state_mock.set_state.assert_called_with(DemoStates.choosing_token)

@pytest.mark.asyncio
async def test_process_demo_token(message_mock, state_mock):
    """Тест process_demo_token."""
    message_mock.text = "SOL"
    await process_demo_token(message_mock, state_mock)
    message_mock.answer.assert_called_with("Вы хотите купить (BUY) или продать (SELL)?")
    state_mock.set_state.assert_called_with(DemoStates.choosing_side)
    state_mock.update_data.assert_called_with(token="SOL")

@pytest.mark.asyncio
async def test_process_demo_side_buy(message_mock, state_mock):
    """Тест process_demo_side (BUY)."""
    message_mock.text = "BUY"
    await process_demo_side(message_mock, state_mock)
    message_mock.answer.assert_called_with("Введите количество:")
    state_mock.set_state.assert_called_with(DemoStates.entering_amount)
    state_mock.update_data.assert_called_with(side="BUY")

@pytest.mark.asyncio
async def test_process_demo_side_sell(message_mock, state_mock):
    """Тест process_demo_side (SELL)."""
    message_mock.text = "SELL"
    await process_demo_side(message_mock, state_mock)
    message_mock.answer.assert_called_with("Введите количество:")
    state_mock.set_state.assert_called_with(DemoStates.entering_amount)
    state_mock.update_data.assert_called_with(side="SELL")

@pytest.mark.asyncio
async def test_process_demo_side_invalid(message_mock, state_mock):
    """Тест process_demo_side: неверный ввод."""
    message_mock.text = "INVALID"
    await process_demo_side(message_mock, state_mock)
    message_mock.answer.assert_called_with("Пожалуйста, введите BUY или SELL.")
    state_mock.set_state.assert_not_called()  #  не меняется
    state_mock.update_data.assert_not_called()

@pytest.mark.asyncio
async def test_process_demo_amount(message_mock, state_mock):
    """Тест process_demo_amount."""
    message_mock.text = "10.5"
    await process_demo_amount(message_mock, state_mock)
    message_mock.answer.assert_called_with("Введите цену (или оставьте пустым для рыночной цены):")
    state_mock.set_state.assert_called_with(DemoStates.entering_price)
    state_mock.update_data.assert_called_with(amount=10.5)

@pytest.mark.asyncio
async def test_process_demo_amount_invalid(message_mock, state_mock):
    """Тест process_demo_amount: неверный ввод."""
    message_mock.text = "abc"  #  
    await process_demo_amount(message_mock, state_mock)
    message_mock.answer.assert_called_with("Пожалуйста, введите число.")
    state_mock.set_state.assert_not_called()
    state_mock.update_data.assert_not_called()

@pytest.mark.asyncio
async def test_process_demo_price(message_mock, state_mock):
    """Тест process_demo_price (с ценой)."""
    message_mock.text = "55.5"
    await process_demo_price(message_mock, state_mock)
    message_mock.answer.assert_called_with(f"Подтвердите ордер:\nТокен: {ANY}\nСторона: {ANY}\nКоличество: {ANY}\nЦена: 55.5", reply_markup=ANY)
    state_mock.set_state.assert_called_with(DemoStates.confirming_order)
    state_mock.update_data.assert_called_with(price=55.5)

@pytest.mark.asyncio
async def test_process_demo_price_empty(message_mock, state_mock):
    """Тест process_demo_price (без цены, рыночная)."""
    message_mock.text = ""  #  
    await process_demo_price(message_mock, state_mock)
    message_mock.answer.assert_called_with(f"Подтвердите ордер:\nТокен: {ANY}\nСторона: {ANY}\nКоличество: {ANY}\nЦена: ", reply_markup=ANY)
    state_mock.set_state.assert_called_with(DemoStates.confirming_order)
    state_mock.update_data.assert_called_with(price=None)  #  

@pytest.mark.asyncio
async def test_process_demo_price_invalid(message_mock, state_mock):
    """Тест process_demo_price: неверный ввод."""
    message_mock.text = "abc"  #  
    await process_demo_price(message_mock, state_mock)
    message_mock.answer.assert_called_with("Пожалуйста, введите число или оставьте поле пустым.")
    state_mock.set_state.assert_not_called()
    state_mock.update_data.assert_not_called()

@pytest.mark.asyncio
async def test_confirm_demo_order_success(message_mock, state_mock, demo_service_mock):
    """Тест confirm_demo_order: успех."""
    state_mock.get_data.return_value = {"token": "SOL", "side": "BUY", "amount": 10.0, "price": 50.0}
    demo_service_mock.create_demo_order.return_value = {'success': True, 'order_id': 123}
    await confirm_demo_order(message_mock, state_mock, demo_service_mock)
    demo_service_mock.create_demo_order.assert_awaited_once_with(123, "SOL", "BUY", 10.0, 50.0)
    message_mock.answer.assert_called_with("✅ Демо-ордер создан. ID: 123")
    state_mock.finish.assert_called_once()

@pytest.mark.asyncio
async def test_confirm_demo_order_failure(message_mock, state_mock, demo_service_mock):
    """Тест confirm_demo_order: ошибка."""
    state_mock.get_data.return_value = {"token": "SOL", "side": "BUY", "amount": 10.0, "price": 50.0}
    demo_service_mock.create_demo_order.return_value = {'success': False, 'error': 'Some error'}
    await confirm_demo_order(message_mock, state_mock, demo_service_mock)
    demo_service_mock.create_demo_order.assert_awaited_once_with(123, "SOL", "BUY", 10.0, 50.0)
    message_mock.answer.assert_called_with("❌ Ошибка при создании демо-ордера: Some error")
    state_mock.finish.assert_called_once() 