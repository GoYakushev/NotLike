import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from services.wallet.wallet_service import WalletService
from core.database.models import Wallet, User
from core.database.database import Database


class TestWalletService(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.db_mock = AsyncMock(spec=Database)
        self.session_mock = AsyncMock()
        self.db_mock.get_session.return_value = self.session_mock
        self.wallet_service = WalletService(self.db_mock)
        self.user = User(id=1, telegram_id=123, username="testuser")

    async def test_get_wallet_exists(self):
        """Тест get_wallet: кошелек существует."""
        wallet = Wallet(user_id=1, network="TON", token_address="EQ...", address="EQ...")
        self.session_mock.query.return_value.filter_by.return_value.first.return_value = wallet
        result = await self.wallet_service.get_wallet(1, "TON", "EQ...")
        self.assertEqual(result, wallet)
        self.session_mock.query.assert_called_once_with(Wallet)
        self.session_mock.query.return_value.filter_by.assert_called_once_with(user_id=1, network="TON", token_address="EQ...")
        self.session_mock.close.assert_called_once()

    async def test_get_wallet_not_exists(self):
        """Тест get_wallet: кошелек не существует."""
        self.session_mock.query.return_value.filter_by.return_value.first.return_value = None
        result = await self.wallet_service.get_wallet(1, "TON", "EQ...")
        self.assertIsNone(result)

    async def test_get_balance_exists(self):
        """Тест get_balance: кошелек существует."""
        wallet = Wallet(user_id=1, network="TON", token_address=None, balance=10.5)
        with patch('services.wallet.wallet_service.WalletService.get_wallet', return_value=wallet):
            result = await self.wallet_service.get_balance(1, "TON")
        self.assertEqual(result, 10.5)

    async def test_get_balance_not_exists(self):
        """Тест get_balance: кошелек не существует."""
        with patch('services.wallet.wallet_service.WalletService.get_wallet', return_value=None):
            result = await self.wallet_service.get_balance(1, "TON")
        self.assertEqual(result, 0.0)

    async def test_update_balance_success(self):
        """Тест update_balance: успех."""
        wallet = Wallet(user_id=1, network="TON", token_address=None, balance=10.0)
        self.session_mock.query.return_value.filter_by.return_value.first.return_value = wallet
        result = await self.wallet_service.update_balance(1, "TON", 5.5)
        self.assertTrue(result)
        self.assertEqual(wallet.balance, 15.5)
        self.session_mock.commit.assert_called_once()

    async def test_update_balance_wallet_not_found(self):
        """Тест update_balance: кошелек не найден."""
        self.session_mock.query.return_value.filter_by.return_value.first.return_value = None
        result = await self.wallet_service.update_balance(1, "TON", 5.5)
        self.assertFalse(result)
        self.session_mock.commit.assert_not_called()

    async def test_update_balance_exception(self):
        """Тест update_balance: исключение."""
        self.session_mock.query.return_value.filter_by.return_value.first.side_effect = Exception("Some error")
        result = await self.wallet_service.update_balance(1, "TON", 5.5)
        self.assertFalse(result)
        self.session_mock.rollback.assert_called_once()

    async def test_lock_funds_success(self):
        """Тест lock_funds: успех."""
        wallet = Wallet(user_id=1, network="TON", token_address=None, balance=10.0, locked_balance=0.0)
        self.session_mock.query.return_value.filter_by.return_value.first.return_value = wallet
        result = await self.wallet_service.lock_funds(1, "TON", 5.5)
        self.assertTrue(result)
        self.assertEqual(wallet.balance, 4.5)
        self.assertEqual(wallet.locked_balance, 5.5)
        self.session_mock.commit.assert_called_once()

    async def test_lock_funds_wallet_not_found(self):
        """Тест lock_funds: кошелек не найден."""
        self.session_mock.query.return_value.filter_by.return_value.first.return_value = None
        result = await self.wallet_service.lock_funds(1, "TON", 5.5)
        self.assertFalse(result)
        self.session_mock.commit.assert_not_called()

    async def test_lock_funds_insufficient_funds(self):
        """Тест lock_funds: недостаточно средств."""
        wallet = Wallet(user_id=1, network="TON", token_address=None, balance=1.0, locked_balance=0.0)
        self.session_mock.query.return_value.filter_by.return_value.first.return_value = wallet
        result = await self.wallet_service.lock_funds(1, "TON", 5.5)
        self.assertFalse(result)
        self.session_mock.commit.assert_not_called()

    async def test_lock_funds_exception(self):
        """Тест lock_funds: исключение."""
        self.session_mock.query.return_value.filter_by.return_value.first.side_effect = Exception("Some error")
        result = await self.wallet_service.lock_funds(1, "TON", 5.5)
        self.assertFalse(result)
        self.session_mock.rollback.assert_called_once()

    async def test_unlock_funds_success(self):
        """Тест unlock_funds: успех."""
        wallet = Wallet(user_id=1, network="TON", token_address=None, balance=4.5, locked_balance=5.5)
        self.session_mock.query.return_value.filter_by.return_value.first.return_value = wallet
        result = await self.wallet_service.unlock_funds(1, "TON", 5.5)
        self.assertTrue(result)
        self.assertEqual(wallet.balance, 10.0)
        self.assertEqual(wallet.locked_balance, 0.0)
        self.session_mock.commit.assert_called_once()

    async def test_unlock_funds_wallet_not_found(self):
        """Тест unlock_funds: кошелек не найден."""
        self.session_mock.query.return_value.filter_by.return_value.first.return_value = None
        result = await self.wallet_service.unlock_funds(1, "TON", 5.5)
        self.assertFalse(result)
        self.session_mock.commit.assert_not_called()

    async def test_unlock_funds_insufficient_locked_funds(self):
        """Тест unlock_funds: недостаточно заблокированных средств."""
        wallet = Wallet(user_id=1, network="TON", token_address=None, balance=4.5, locked_balance=1.0)
        self.session_mock.query.return_value.filter_by.return_value.first.return_value = wallet
        result = await self.wallet_service.unlock_funds(1, "TON", 5.5)
        self.assertFalse(result)
        self.session_mock.commit.assert_not_called()

    async def test_unlock_funds_exception(self):
        """Тест unlock_funds: исключение."""
        self.session_mock.query.return_value.filter_by.return_value.first.side_effect = Exception("Some error")
        result = await self.wallet_service.unlock_funds(1, "TON", 5.5)
        self.assertFalse(result)
        self.session_mock.rollback.assert_called_once()

    async def test_transfer_funds_success(self):
        """Тест transfer_funds: успех."""
        wallet1 = Wallet(user_id=1, network="TON", token_address=None, balance=10.0)
        wallet2 = Wallet(user_id=2, network="TON", token_address=None, balance=5.0)
        self.session_mock.query.return_value.filter_by.side_effect = [wallet1, wallet2]  #  side_effect
        result = await self.wallet_service.transfer_funds(1, 2, "TON", 4.0)
        self.assertTrue(result)
        self.assertEqual(wallet1.balance, 6.0)
        self.assertEqual(wallet2.balance, 9.0)
        self.session_mock.commit.assert_called_once()

    async def test_transfer_funds_from_wallet_not_found(self):
        """Тест transfer_funds: кошелек отправителя не найден."""
        self.session_mock.query.return_value.filter_by.side_effect = [None, MagicMock()]  #  side_effect
        result = await self.wallet_service.transfer_funds(1, 2, "TON", 4.0)
        self.assertFalse(result)
        self.session_mock.commit.assert_not_called()

    async def test_transfer_funds_to_wallet_not_found(self):
        """Тест transfer_funds: кошелек получателя не найден."""
        self.session_mock.query.return_value.filter_by.side_effect = [MagicMock(), None]  #  side_effect
        result = await self.wallet_service.transfer_funds(1, 2, "TON", 4.0)
        self.assertFalse(result)
        self.session_mock.commit.assert_not_called()

    async def test_transfer_funds_insufficient_funds(self):
        """Тест transfer_funds: недостаточно средств."""
        wallet1 = Wallet(user_id=1, network="TON", token_address=None, balance=1.0)
        wallet2 = Wallet(user_id=2, network="TON", token_address=None, balance=5.0)
        self.session_mock.query.return_value.filter_by.side_effect = [wallet1, wallet2]
        result = await self.wallet_service.transfer_funds(1, 2, "TON", 4.0)
        self.assertFalse(result)
        self.session_mock.commit.assert_not_called()

    async def test_transfer_funds_exception(self):
        """Тест transfer_funds: исключение."""
        self.session_mock.query.return_value.filter_by.side_effect = Exception("Some error")
        result = await self.wallet_service.transfer_funds(1, 2, "TON", 4.0)
        self.assertFalse(result)
        self.session_mock.rollback.assert_called_once() 