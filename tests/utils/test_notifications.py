import pytest
from utils.notifications import (
    notify_new_p2p_order,
    notify_p2p_order_taken,
    notify_p2p_order_completed,
    notify_p2p_order_canceled,
    notify_new_spot_order,
    notify_spot_order_status_changed,
    notify_low_balance,
    notify_user,
    NotificationType
)
from unittest.mock import AsyncMock, patch, ANY

pytest_plugins = ('pytest_asyncio',)

@pytest.fixture
def bot_mock():
    return AsyncMock()

@pytest.mark.asyncio
async def test_notify_new_p2p_order(bot_mock):
    """Тест notify_new_p2p_order."""
    await notify_new_p2p_order(bot_mock, 123, "BUY", "SOL", "USDT", 10.0, 50.0, "binance")
    bot_mock.send_message.assert_awaited_once_with(
        123,
        "🔔 Новый P2P ордер:\nТип: BUY\nВалюта: SOL\nКотируемая валюта: USDT\nКоличество: 10.0\nЦена: 50.0\nПлатежный метод: binance",
        parse_mode="HTML"
    )

@pytest.mark.asyncio
async def test_notify_p2p_order_taken(bot_mock):
    """Тест notify_p2p_order_taken."""
    await notify_p2p_order_taken(bot_mock, 123, 456)
    bot_mock.send_message.assert_awaited_once_with(
        123,
        "🔔 P2P ордер #456 принят.",
        parse_mode="HTML"
    )

@pytest.mark.asyncio
async def test_notify_p2p_order_completed(bot_mock):
    """Тест notify_p2p_order_completed."""
    await notify_p2p_order_completed(bot_mock, 123, 456)
    bot_mock.send_message.assert_awaited_once_with(
        123,
        "✅ P2P ордер #456 выполнен.",
        parse_mode="HTML"
    )

@pytest.mark.asyncio
async def test_notify_p2p_order_canceled(bot_mock):
    """Тест notify_p2p_order_canceled."""
    await notify_p2p_order_canceled(bot_mock, 123, 456)
    bot_mock.send_message.assert_awaited_once_with(
        123,
        "❌ P2P ордер #456 отменен.",
        parse_mode="HTML"
    )

@pytest.mark.asyncio
async def test_notify_new_spot_order(bot_mock):
    """Тест notify_new_spot_order."""
    await notify_new_spot_order(bot_mock, 123, "BUY", "SOL", "USDT", 10.0, 50.0)
    bot_mock.send_message.assert_awaited_once_with(
        123,
        "🔔 Новый спотовый ордер:\nТип: BUY\nВалюта: SOL\nКотируемая валюта: USDT\nКоличество: 10.0\nЦена: 50.0",
        parse_mode="HTML"
    )

@pytest.mark.asyncio
async def test_notify_spot_order_status_changed(bot_mock):
    """Тест notify_spot_order_status_changed."""
    await notify_spot_order_status_changed(bot_mock, 123, 456, "FILLED")
    bot_mock.send_message.assert_awaited_once_with(
        123,
        "🔔 Статус спотового ордера #456 изменен: FILLED",
        parse_mode="HTML"
    )

@pytest.mark.asyncio
async def test_notify_low_balance(bot_mock):
    """Тест notify_low_balance."""
    await notify_low_balance(bot_mock, 123, "SOL", 5.0)
    bot_mock.send_message.assert_awaited_once_with(
        123,
        "⚠️ Низкий баланс SOL: 5.0",
        parse_mode="HTML"
    )

@pytest.mark.asyncio
async def test_notify_user(bot_mock):
    """Тест notify_user."""
    await notify_user(bot_mock, 123, NotificationType.LOW_BALANCE, "Custom message", {'key': 'value'})
    bot_mock.send_message.assert_awaited_once_with(
        123,
        "Custom message",
        parse_mode="HTML",
        reply_markup=ANY  #  ,    
    ) 