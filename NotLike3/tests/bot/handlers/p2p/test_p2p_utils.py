import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from aiogram.types import Message
from bot.handlers.p2p_handler import is_premium
from core.database.models import User
from datetime import datetime, timedelta

class TestP2PUtils(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.message_mock = MagicMock(spec=Message)
        self.message_mock.from_user.id = 123

    async def test_is_premium_true(self):
        """Тест is_premium (премиум)."""
        user = User(telegram_id=123, is_premium=True, premium_expires_at=datetime.utcnow() + timedelta(days=1))
        with patch('bot.handlers.p2p_handler.Database') as mock_db:
            mock_db.return_value.get_session.return_value.query.return_value.filter.return_value.first.return_value = user
            result = await is_premium(self.message_mock)
        self.assertTrue(result)

    async def test_is_premium_false(self):
        """Тест is_premium (не премиум)."""
        user = User(telegram_id=123, is_premium=False, premium_expires_at=None)
        with patch('bot.handlers.p2p_handler.Database') as mock_db:
            mock_db.return_value.get_session.return_value.query.return_value.filter.return_value.first.return_value = user
            result = await is_premium(self.message_mock)
        self.assertFalse(result)

    async def test_is_premium_expired(self):
        """Тест is_premium (премиум истек)."""
        user = User(telegram_id=123, is_premium=True, premium_expires_at=datetime.utcnow() - timedelta(days=1))
        with patch('bot.handlers.p2p_handler.Database') as mock_db:
            mock_db.return_value.get_session.return_value.query.return_value.filter.return_value.first.return_value = user
            result = await is_premium(self.message_mock)
        self.assertFalse(result) 