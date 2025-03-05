import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from services.wallet.wallet_service import WalletService
from core.database.models import User, Wallet, Token
from core.blockchain.solana_client import SolanaClient
from core.blockchain.ton_client import TONClient
from tonsdk.utils import Address  # Для TON
import aiohttp
from aiohttp import web


class TestWalletService(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.db_mock = AsyncMock()
        self.solana_client_mock = AsyncMock(spec=SolanaClient)
        self.ton_client_mock = AsyncMock(spec=TONClient)

        # Патчим random_string, чтобы он возвращал предсказуемое значение
        self.random_string_patch = patch('services.wallet.wallet_service.random_string', return_value='random_string')
        self.random_string_patch.start()

        self.wallet_service = WalletService()
        self.wallet_service.db = self.db_mock #  db
        self.wallet_service.solana = self.solana_client_mock
        self.wallet_service.ton = self.ton_client_mock

        self.test_user = User(telegram_id=123, username="testuser")

    async def asyncTearDown(self):
        self.random_string_patch.stop()

    async def test_create_wallet_solana_success(self):
        """Тест успешного создания Solana кошелька."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        session_mock.query.return_value.filter_by.return_value.first.return_value = self.test_user

        # Мокаем методы SolanaClient
        self.solana_client_mock.generate_keypair.return_value = ("private_key", "public_key")

        result = await self.wallet_service.create_wallet(self.test_user.telegram_id, "SOL")
        self.assertTrue(result['success'])
        self.assertEqual(result['address'], "public_key")
        session_mock.add.assert_called_once()
        session_mock.commit.assert_called_once()
        # Проверяем, что был создан кошелек с правильными данными
        added_wallet = session_mock.add.call_args[0][0]
        self.assertEqual(added_wallet.user_id, self.test_user.id)
        self.assertEqual(added_wallet.network, "SOL")
        self.assertEqual(added_wallet.address, "public_key")
        self.assertEqual(added_wallet.private_key, "private_key")

    async def test_create_wallet_ton_success(self):
        """Тест успешного создания TON кошелька."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        session_mock.query.return_value.filter_by.return_value.first.return_value = self.test_user

        self.ton_client_mock.generate_keypair.return_value = ("private_key", "public_key")

        result = await self.wallet_service.create_wallet(self.test_user.telegram_id, "TON")
        self.assertTrue(result['success'])
        self.assertEqual(result['address'], "public_key")
        session_mock.add.assert_called_once()
        session_mock.commit.assert_called_once()
        added_wallet = session_mock.add.call_args[0][0]
        self.assertEqual(added_wallet.user_id, self.test_user.id)
        self.assertEqual(added_wallet.network, "TON")
        self.assertEqual(added_wallet.address, "public_key")
        self.assertEqual(added_wallet.private_key, "private_key")

    async def test_create_wallet_user_not_found(self):
        """Тест: пользователь не найден."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        session_mock.query.return_value.filter_by.return_value.first.return_value = None

        result = await self.wallet_service.create_wallet(999, "SOL")
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], "Пользователь не найден")

    async def test_create_wallet_already_exists(self):
        """Тест: кошелек уже существует."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        session_mock.query.return_value.filter_by.return_value.first.return_value = self.test_user
        # Мокаем, что кошелек уже существует
        session_mock.query.return_value.filter_by.return_value.filter_by.return_value.first.return_value = Wallet()

        result = await self.wallet_service.create_wallet(self.test_user.telegram_id, "SOL")
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], "Кошелек SOL уже существует")

    async def test_create_wallet_exception(self):
        """Тест: исключение при создании кошелька."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        session_mock.query.return_value.filter_by.return_value.first.return_value = self.test_user
        session_mock.commit.side_effect = Exception("Database error")

        result = await self.wallet_service.create_wallet(self.test_user.telegram_id, "SOL")
        self.assertFalse(result['success'])
        self.assertIn("Ошибка при создании кошелька", result['error'])

    async def test_get_wallet_address_success(self):
        """Тест успешного получения адреса кошелька."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        # Мокаем, что кошелек существует
        wallet = Wallet(address="test_address")
        session_mock.query.return_value.filter_by.return_value.filter_by.return_value.first.return_value = wallet

        result = await self.wallet_service.get_wallet_address(self.test_user.telegram_id, "SOL")
        self.assertEqual(result, "test_address")

    async def test_get_wallet_address_not_found(self):
        """Тест: кошелек не найден."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        session_mock.query.return_value.filter_by.return_value.filter_by.return_value.first.return_value = None

        result = await self.wallet_service.get_wallet_address(self.test_user.telegram_id, "SOL")
        self.assertIsNone(result)

    async def test_get_wallet_balance_success(self):
        """Тест успешного получения баланса."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        wallet = Wallet(address="test_address", network="SOL")
        session_mock.query.return_value.filter_by.return_value.filter_by.return_value.first.return_value = wallet

        self.solana_client_mock.get_balance.return_value = 1.23  # Мокаем баланс

        result = await self.wallet_service.get_wallet_balance(self.test_user.telegram_id, "SOL")
        self.assertEqual(result, 1.23)
        self.solana_client_mock.get_balance.assert_called_once_with("test_address") # Проверяем вызов

    async def test_get_wallet_balance_wallet_not_found(self):
        """Тест: кошелек не найден (для получения баланса)."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        session_mock.query.return_value.filter_by.return_value.filter_by.return_value.first.return_value = None

        result = await self.wallet_service.get_wallet_balance(self.test_user.telegram_id, "SOL")
        self.assertEqual(result, 0)  # Возвращаем 0, если кошелек не найден

    async def test_get_wallet_balance_exception(self):
        """Тест: исключение при получении баланса."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        wallet = Wallet(address="test_address", network="SOL")
        session_mock.query.return_value.filter_by.return_value.filter_by.return_value.first.return_value = wallet

        self.solana_client_mock.get_balance.side_effect = Exception("Network error") # Мокаем ошибку

        result = await self.wallet_service.get_wallet_balance(self.test_user.telegram_id, "SOL")
        self.assertEqual(result, 0)  # Возвращаем 0 при ошибке
        self.solana_client_mock.get_balance.assert_called_once_with("test_address")

    async def test_transfer_funds_solana_success(self):
        """Тест успешного перевода средств (Solana)."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock

        # Мокаем кошельки отправителя и получателя
        sender_wallet = Wallet(address="sender_address", private_key="sender_private_key", network="SOL", balance=2.0)
        receiver_wallet = Wallet(address="receiver_address", private_key="receiver_private_key", network="SOL", balance=1.0)
        session_mock.query.return_value.filter_by.return_value.filter_by.return_value.first.side_effect = [sender_wallet, receiver_wallet]

        # Мокаем transfer SolanaClient'а
        self.solana_client_mock.transfer.return_value = "transaction_signature"

        result = await self.wallet_service.transfer_funds(
            self.test_user.telegram_id, "receiver_address", 1.5, "SOL"
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['transaction_hash'], "transaction_signature")
        self.solana_client_mock.transfer.assert_called_once_with(
            "sender_private_key", "receiver_address", 1.5
        )
        # Проверяем обновление балансов в БД
        self.assertAlmostEqual(sender_wallet.balance, 0.5)  # 2.0 - 1.5 = 0.5
        self.assertAlmostEqual(receiver_wallet.balance, 2.5) # 1.0 + 1.5 = 2.5
        session_mock.commit.assert_called_once()

    async def test_transfer_funds_ton_success(self):
        """Тест успешного перевода средств (TON)."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock

        sender_wallet = Wallet(address="sender_address", private_key="sender_private_key", network="TON", balance=5.0)
        # Для TON используем Address из tonsdk.utils
        receiver_wallet = Wallet(address=Address("receiver_address").to_string(), private_key="receiver_private_key", network="TON", balance=2.0)
        session_mock.query.return_value.filter_by.return_value.filter_by.return_value.first.side_effect = [sender_wallet, receiver_wallet]

        self.ton_client_mock.transfer.return_value = "transaction_hash"

        result = await self.wallet_service.transfer_funds(
            self.test_user.telegram_id, Address("receiver_address").to_string(), 3.0, "TON"
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['transaction_hash'], "transaction_hash")
        self.ton_client_mock.transfer.assert_called_once_with(
            "sender_private_key", Address("receiver_address").to_string(), 3.0
        )
        self.assertAlmostEqual(sender_wallet.balance, 2.0)
        self.assertAlmostEqual(receiver_wallet.balance, 5.0)
        session_mock.commit.assert_called_once()

    async def test_transfer_funds_sender_wallet_not_found(self):
        """Тест: кошелек отправителя не найден."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        session_mock.query.return_value.filter_by.return_value.filter_by.return_value.first.return_value = None  # Нет кошелька

        result = await self.wallet_service.transfer_funds(
            self.test_user.telegram_id, "receiver_address", 1.0, "SOL"
        )
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], "Кошелек отправителя не найден")

    async def test_transfer_funds_receiver_wallet_not_found(self):
        """Тест: кошелек получателя не найден."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        sender_wallet = Wallet(address="sender_address", private_key="sender_private_key", network="SOL")
        session_mock.query.return_value.filter_by.return_value.filter_by.return_value.first.side_effect = [sender_wallet, None] # Мокаем sender, потом None для receiver

        result = await self.wallet_service.transfer_funds(
            self.test_user.telegram_id, "receiver_address", 1.0, "SOL"
        )
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], "Кошелек получателя не найден")

    async def test_transfer_funds_insufficient_balance(self):
        """Тест: недостаточно средств."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        sender_wallet = Wallet(address="sender_address", private_key="sender_private_key", network="SOL", balance=0.5)
        receiver_wallet = Wallet(address="receiver_address", private_key="receiver_private_key", network="SOL")
        session_mock.query.return_value.filter_by.return_value.filter_by.return_value.first.side_effect = [sender_wallet, receiver_wallet]

        result = await self.wallet_service.transfer_funds(
            self.test_user.telegram_id, "receiver_address", 1.0, "SOL"  # Хотим перевести больше, чем есть
        )
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], "Недостаточно средств")

    async def test_transfer_funds_invalid_network(self):
        """Тест: неверная сеть."""
        result = await self.wallet_service.transfer_funds(
            self.test_user.telegram_id, "receiver_address", 1.0, "INVALID"
        )
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], "Неподдерживаемая сеть: INVALID")

    async def test_transfer_funds_exception(self):
        """Тест: исключение при переводе."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        sender_wallet = Wallet(address="sender_address", private_key="sender_private_key", network="SOL", balance=2.0)
        receiver_wallet = Wallet(address="receiver_address", private_key="receiver_private_key", network="SOL")
        session_mock.query.return_value.filter_by.return_value.filter_by.return_value.first.side_effect = [sender_wallet, receiver_wallet]

        self.solana_client_mock.transfer.side_effect = Exception("Network error") # Мокаем ошибку

        result = await self.wallet_service.transfer_funds(
            self.test_user.telegram_id, "receiver_address", 1.0, "SOL"
        )
        self.assertFalse(result['success'])
        self.assertIn("Ошибка при переводе", result['error'])
        # Балансы не должны измениться
        self.assertEqual(sender_wallet.balance, 2.0)
        self.assertEqual(receiver_wallet.balance, 0.0) # default
        session_mock.commit.assert_not_called() # commit не должен вызываться

    async def test_generate_deposit_address_solana(self):
        """Тест генерации адреса депозита (Solana)."""
        result = await self.wallet_service.generate_deposit_address("SOL")
        self.assertEqual(result, "random_string")  # random_string из-за патча

    async def test_generate_deposit_address_ton(self):
        """Тест генерации адреса депозита (TON)."""
        result = await self.wallet_service.generate_deposit_address("TON")
        self.assertEqual(result, "random_string")

    async def test_generate_deposit_address_invalid_network(self):
        """Тест: неверная сеть (для генерации адреса)."""
        with self.assertRaises(ValueError) as context:
            await self.wallet_service.generate_deposit_address("INVALID")
        self.assertEqual(str(context.exception), "Неподдерживаемая сеть: INVALID")

    async def test_get_balances_solana_and_ton(self):
        """Тест get_balances: SOL, TON, USDT и неизвестный токен."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock

        # Мокаем кошельки
        sol_wallet = Wallet(user_id=self.test_user.id, network="SOL", address="sol_address", token_address=None)
        usdt_wallet = Wallet(user_id=self.test_user.id, network="SOL", address="sol_address", token_address="usdt_address")
        unknown_wallet = Wallet(user_id=self.test_user.id, network="SOL", address="sol_address", token_address="unknown_address")
        ton_wallet = Wallet(user_id=self.test_user.id, network="TON", address="ton_address", token_address=None)
        session_mock.query.return_value.filter_by.return_value.all.return_value = [sol_wallet, usdt_wallet, unknown_wallet, ton_wallet]

        # Мокаем балансы
        self.solana_client_mock.get_balance.side_effect = [1.23, 100.0, 0.5]  # SOL, USDT, Unknown
        self.ton_client_mock.get_balance.return_value = 2.5  # TON

        # Мокаем Orca API, чтобы он возвращал инфу о неизвестном токене
        async def mock_orca_get(*args, **kwargs):
            if args[0] == "https://api.orca.so/v1/token/unknown_address":
                return web.json_response({"symbol": "UNK", "name": "Unknown Token", "decimals": 9}, status=200)
            else:
                return web.json_response({"error": "Not found"}, status=404)

        with patch('aiohttp.ClientSession.get', return_value=AsyncMock(json=mock_orca_get, status=200)):
            balances = await self.wallet_service.get_balances(self.test_user.telegram_id)

        self.assertEqual(len(balances), 4)  # SOL, TON, USDT, UNK
        self.assertAlmostEqual(balances['SOL'], 1.23)
        self.assertAlmostEqual(balances['TON'], 2.5)
        self.assertAlmostEqual(balances['USDT'], 100.0)
        self.assertAlmostEqual(balances['UNK'], 0.5)

        # Проверяем, что токен добавился в базу
        session_mock.add.assert_called()
        session_mock.commit.assert_called()

    async def test_get_balances_only_sol_and_ton(self):
        """Тест get_balances: только SOL и TON (нулевые балансы других токенов)."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock

        sol_wallet = Wallet(user_id=self.test_user.id, network="SOL", address="sol_address", token_address=None)
        ton_wallet = Wallet(user_id=self.test_user.id, network="TON", address="ton_address", token_address=None)
        zero_wallet = Wallet(user_id=self.test_user.id, network="SOL", address="sol_address", token_address="zero_address")
        session_mock.query.return_value.filter_by.return_value.all.return_value = [sol_wallet, ton_wallet, zero_wallet]

        self.solana_client_mock.get_balance.side_effect = [1.23, 0.0]  # SOL, Zero
        self.ton_client_mock.get_balance.return_value = 2.5

        balances = await self.wallet_service.get_balances(self.test_user.telegram_id)
        self.assertEqual(len(balances), 2)  # Только SOL и TON
        self.assertAlmostEqual(balances['SOL'], 1.23)
        self.assertAlmostEqual(balances['TON'], 2.5)

    async def test_get_balances_orca_api_error(self):
        """Тест get_balances: ошибка Orca API."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        unknown_wallet = Wallet(user_id=self.test_user.id, network="SOL", address="sol_address", token_address="unknown_address")
        session_mock.query.return_value.filter_by.return_value.all.return_value = [unknown_wallet]
        self.solana_client_mock.get_balance.return_value = 0.5

        # Мокаем Orca API, чтобы он возвращал ошибку
        async def mock_orca_error(*args, **kwargs):
            return web.json_response({"error": "Some Orca error"}, status=500)

        with patch('aiohttp.ClientSession.get', return_value=AsyncMock(json=mock_orca_error, status=500)):
            balances = await self.wallet_service.get_balances(self.test_user.telegram_id)

        self.assertEqual(len(balances), 1)
        self.assertAlmostEqual(balances['Unknown (unknown_...)'], 0.5)  #  Unknown
        session_mock.add.assert_not_called()  #  токен не должен добавляться
        session_mock.commit.assert_not_called()

    async def test_get_balances_exception(self):
        """Тест get_balances: общее исключение."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        unknown_wallet = Wallet(user_id=self.test_user.id, network="SOL", address="sol_address", token_address="unknown_address")
        session_mock.query.return_value.filter_by.return_value.all.return_value = [unknown_wallet]
        self.solana_client_mock.get_balance.return_value = 0.5

        with patch('aiohttp.ClientSession.get', side_effect=Exception("Some error")):
            balances = await self.wallet_service.get_balances(self.test_user.telegram_id)

        self.assertEqual(len(balances), 1)
        self.assertAlmostEqual(balances['Unknown (unknown_...)'], 0.5)
        session_mock.add.assert_not_called()
        session_mock.commit.assert_not_called() 