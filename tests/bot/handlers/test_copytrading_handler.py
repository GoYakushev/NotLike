import pytest
from aiogram import types
from aiogram.dispatcher import FSMContext
from unittest.mock import AsyncMock, patch, MagicMock
from bot.handlers.copytrading_handler import (
    show_copytrading_menu, show_top_traders, become_trader_handler,
    follow_trader_handler, my_subscriptions, unfollow_trader_handler,
    CopyTradingStates
)
from services.copytrading.copytrading_service import CopyTradingService
from core.database.models import CopyTrader, CopyTraderFollower, User

pytest_plugins = ('pytest_asyncio',)

@pytest.fixture
def copytrading_service_mock():
    return AsyncMock(spec=CopyTradingService)

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
async def test_show_copytrading_menu(message_mock):
    """Тест show_copytrading_menu."""
    await show_copytrading_menu(message_mock)
    message_mock.answer.assert_called_once()
    args, kwargs = message_mock.answer.call_args
    assert "📊 Копитрейдинг" in args[0]
    assert isinstance(kwargs['reply_markup'], types.InlineKeyboardMarkup)

@pytest.mark.asyncio
async def test_show_top_traders(callback_query_mock, copytrading_service_mock):
    """Тест show_top_traders."""
    #  
    trader1 = MagicMock(spec=CopyTrader)
    trader1.user.username = "trader1"
    trader1.total_trades = 100
    trader1.successful_trades = 80
    trader2 = MagicMock(spec=CopyTrader)
    trader2.user.username = "trader2"
    trader2.total_trades = 50
    trader2.successful_trades = 45
    copytrading_service_mock.get_top_traders.return_value = [trader1, trader2]

    await show_top_traders(callback_query_mock, copytrading_service_mock)

    callback_query_mock.message.answer.assert_called_once()
    args, _ = callback_query_mock.message.answer.call_args
    assert "📊 Топ трейдеров" in args[0]
    assert "👤 @trader1" in args[0]
    assert "👤 @trader2" in args[0]
    assert "📈 Сделок: 100" in args[0]
    assert "✅ Успешных: 80" in args[0]
    assert "📈 Сделок: 50" in args[0]
    assert "✅ Успешных: 45" in args[0]
    callback_query_mock.answer.assert_called_once()

@pytest.mark.asyncio
async def test_show_top_traders_no_traders(callback_query_mock, copytrading_service_mock):
    """Тест show_top_traders: нет трейдеров."""
    copytrading_service_mock.get_top_traders.return_value = []  #  трейдеров
    await show_top_traders(callback_query_mock, copytrading_service_mock)
    callback_query_mock.message.answer.assert_called_with("Трейдеров пока нет.")
    callback_query_mock.answer.assert_called_once()

@pytest.mark.asyncio
async def test_become_trader_handler_success(message_mock, copytrading_service_mock):
    """Тест become_trader_handler: успех."""
    copytrading_service_mock.register_as_trader.return_value = {'success': True}
    await become_trader_handler(message_mock, copytrading_service_mock)
    message_mock.answer.assert_called_with("✅ Вы успешно зарегистрированы как трейдер.")

@pytest.mark.asyncio
async def test_become_trader_handler_failure(message_mock, copytrading_service_mock):
    """Тест become_trader_handler: ошибка."""
    copytrading_service_mock.register_as_trader.return_value = {'success': False, 'error': 'Some error'}
    await become_trader_handler(message_mock, copytrading_service_mock)
    message_mock.answer.assert_called_with("❌ Ошибка при регистрации: Some error")

@pytest.mark.asyncio
async def test_follow_trader_handler_success(callback_query_mock, state_mock, copytrading_service_mock):
    """Тест follow_trader_handler: успех."""
    callback_query_mock.data = "follow_trader_456"  #  ID трейдера
    copytrading_service_mock.follow_trader.return_value = {'success': True}

    await follow_trader_handler(callback_query_mock, state_mock, copytrading_service_mock)

    copytrading_service_mock.follow_trader.assert_awaited_once_with(123, 456, 100.0)  #  ID, ID, 
    callback_query_mock.message.answer.assert_called_with("✅ Вы успешно подписались на трейдера.")
    callback_query_mock.answer.assert_called_once()
    state_mock.finish.assert_called_once()

@pytest.mark.asyncio
async def test_follow_trader_handler_failure(callback_query_mock, state_mock, copytrading_service_mock):
    """Тест follow_trader_handler: ошибка."""
    callback_query_mock.data = "follow_trader_456"
    copytrading_service_mock.follow_trader.return_value = {'success': False, 'error': 'Some error'}

    await follow_trader_handler(callback_query_mock, state_mock, copytrading_service_mock)

    copytrading_service_mock.follow_trader.assert_awaited_once_with(123, 456, 100.0)
    callback_query_mock.message.answer.assert_called_with("❌ Ошибка: Some error")
    callback_query_mock.answer.assert_called_once()
    state_mock.finish.assert_called_once()

@pytest.mark.asyncio
async def test_my_subscriptions_no_subscriptions(callback_query_mock, copytrading_service_mock):
    """Тест my_subscriptions: нет подписок."""
    copytrading_service_mock.db.get_session.return_value.query.return_value.filter_by.return_value.all.return_value = []  #  подписок
    await my_subscriptions(callback_query_mock)
    callback_query_mock.message.answer.assert_called_with("У вас нет активных подписок.")

@pytest.mark.asyncio
async def test_my_subscriptions_with_subscriptions(callback_query_mock, copytrading_service_mock):
    """Тест my_subscriptions: есть подписки."""
    #  
    sub1 = MagicMock(spec=CopyTraderFollower)
    sub1.trader.user.username = "trader1"
    sub1.copy_amount = 100.0
    sub2 = MagicMock(spec=CopyTraderFollower)
    sub2.trader.user.username = "trader2"
    sub2.copy_amount = 50.0
    copytrading_service_mock.db.get_session.return_value.query.return_value.filter_by.return_value.all.return_value = [sub1, sub2]

    await my_subscriptions(callback_query_mock)

    callback_query_mock.message.answer.assert_called_once()
    args, _ = callback_query_mock.message.answer.call_args
    assert "📊 Ваши подписки" in args[0]
    assert "👤 Трейдер: @trader1" in args[0]
    assert "💰 Сумма копирования: 100.00" in args[0]
    assert "👤 Трейдер: @trader2" in args[0]
    assert "💰 Сумма копирования: 50.00" in args[0]

@pytest.mark.asyncio
async def test_unfollow_trader_handler_success(callback_query_mock, copytrading_service_mock):
    """Тест unfollow_trader_handler: успех."""
    callback_query_mock.data = "unfollow_trader_456"
    copytrading_service_mock.unfollow_trader.return_value = {'success': True}
    await unfollow_trader_handler(callback_query_mock, copytrading_service_mock)
    copytrading_service_mock.unfollow_trader.assert_awaited_once_with(123, 456)
    callback_query_mock.message.answer.assert_called_with("✅ Вы успешно отписались от трейдера.")

@pytest.mark.asyncio
async def test_unfollow_trader_handler_failure(callback_query_mock, copytrading_service_mock):
    """Тест unfollow_trader_handler: ошибка."""
    callback_query_mock.data = "unfollow_trader_456"
    copytrading_service_mock.unfollow_trader.return_value = {'success': False, 'error': 'Some error'}
    await unfollow_trader_handler(callback_query_mock, copytrading_service_mock)
    copytrading_service_mock.unfollow_trader.assert_awaited_once_with(123, 456)
    callback_query_mock.message.answer.assert_called_with("❌ Ошибка: Some error") 