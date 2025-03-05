import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from core.blockchain.solana_client import SolanaClient
from solana.rpc.api import Client
from solana.account import Account
from solana.publickey import PublicKey
from solana.transaction import Transaction
from spl.token.client import Token
from spl.token.constants import TOKEN_PROGRAM_ID
import base58

class TestSolanaClient(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.client_mock = AsyncMock(spec=Client)
        self.solana_client = SolanaClient()
        self.solana_client.client = self.client_mock  #  client

    async def test_create_wallet(self):
        """Тест создания кошелька."""
        wallet = self.solana_client.create_wallet()
        self.assertIn('address', wallet)
        self.assertIn('private_key', wallet)
        self.assertTrue(PublicKey.is_on_curve(PublicKey(wallet['address']))) #  валидный адрес
        #  приватный ключ
        try:
            Account(base58.b58decode(wallet['private_key']))
        except ValueError:
            self.fail("Invalid private key")

    async def test_get_balance_sol(self):
        """Тест получения баланса SOL."""
        self.client_mock.get_balance.return_value = {'result': {'value': 1234567890}}  # 1.23456789 SOL
        balance = self.solana_client.get_balance("test_address")
        self.assertAlmostEqual(balance, 1.23456789)
        self.client_mock.get_balance.assert_called_once_with(PublicKey("test_address"))

    async def test_get_balance_spl_token(self):
        """Тест получения баланса SPL токена."""
        token_mock = MagicMock(spec=Token)
        # Мокаем get_accounts_by_owner, чтобы он возвращал  associated token account
        token_mock.get_accounts_by_owner.return_value = {
            'result': {
                'value': [{'pubkey': 'token_account_address'}]
            }
        }
        # Мокаем get_balance, чтобы он возвращал баланс
        token_mock.get_balance.return_value = {'result': {'value': {'uiAmount': 10.5}}}

        with patch('spl.token.client.Token', return_value=token_mock):
            balance = self.solana_client.get_balance("test_address", "token_address")

        self.assertAlmostEqual(balance, 10.5)
        token_mock.get_accounts_by_owner.assert_called_once_with(PublicKey("test_address"), commitment="processed")
        token_mock.get_balance.assert_called_once_with('token_account_address', commitment="processed")

    async def test_get_balance_spl_token_no_account(self):
        """Тест: нет associated token account."""
        token_mock = MagicMock(spec=Token)
        token_mock.get_accounts_by_owner.return_value = {'result': {'value': []}} # Пустой список

        with patch('spl.token.client.Token', return_value=token_mock):
            balance = self.solana_client.get_balance("test_address", "token_address")
        self.assertEqual(balance, 0.0)
        token_mock.get_accounts_by_owner.assert_called_once_with(PublicKey("test_address"), commitment="processed")
        token_mock.get_balance.assert_not_called() # get_balance не должен вызываться

    async def test_get_balance_exception(self):
        """Тест: исключение при получении баланса."""
        self.client_mock.get_balance.side_effect = Exception("Network error")
        balance = self.solana_client.get_balance("test_address")
        self.assertEqual(balance, 0.0)

    async def test_transfer_sol_success(self):
        """Тест успешного перевода SOL."""
        self.client_mock.send_transaction.return_value = {'result': 'transaction_signature'}
        sender_private_key = base58.b58encode(Account().keypair()).decode('utf-8') #  приватный ключ
        result = self.solana_client.transfer(sender_private_key, "recipient_address", 1.0)
        self.assertTrue(result['success'])
        self.assertEqual(result['transaction_id'], 'transaction_signature')
        self.client_mock.send_transaction.assert_called_once()
        #  аргументы (проверяем, что транзакция создана правильно)
        args, kwargs = self.client_mock.send_transaction.call_args
        self.assertIsInstance(args[0], Transaction)
        self.assertEqual(len(kwargs['signers']), 1) #  signer
        self.assertIsInstance(kwargs['signers'][0], Account)

    async def test_transfer_spl_token_success(self):
        """Тест успешного перевода SPL токена."""
        token_mock = MagicMock(spec=Token)
        # Мокаем get_accounts_by_owner
        token_mock.get_accounts_by_owner.return_value = {
            'result': {
                'value': [{'pubkey': 'sender_token_account'}, {'pubkey': 'recipient_token_account'}]
            }
        }
        # Мокаем get_mint_info, чтобы получить decimals
        token_mock.get_mint_info.return_value = {'result': {'value': {'decimals': 6}}}
        # Мокаем transfer
        self.client_mock.send_transaction.return_value = {'result': 'transaction_signature'}

        sender_private_key = base58.b58encode(Account().keypair()).decode('utf-8')
        with patch('spl.token.client.Token', return_value=token_mock):
            result = self.solana_client.transfer(sender_private_key, "recipient_address", 2.5, "token_address")

        self.assertTrue(result['success'])
        self.assertEqual(result['transaction_id'], 'transaction_signature')
        self.client_mock.send_transaction.assert_called_once()
        token_mock.get_accounts_by_owner.assert_called()
        token_mock.get_mint_info.assert_called_once()
        #  transfer вызвался с правильными аргументами
        transfer_args, transfer_kwargs = token_mock.transfer.call_args
        self.assertEqual(transfer_kwargs['source'], 'sender_token_account')
        self.assertEqual(transfer_kwargs['dest'], 'recipient_token_account')
        self.assertEqual(transfer_kwargs['amount'], 2500000) # 2.5 * 10^6

    async def test_transfer_exception(self):
        """Тест: исключение при переводе."""
        self.client_mock.send_transaction.side_effect = Exception("Network error")
        sender_private_key = base58.b58encode(Account().keypair()).decode('utf-8')
        result = self.solana_client.transfer(sender_private_key, "recipient_address", 1.0)
        self.assertFalse(result['success'])
        self.assertIn("Network error", result['error']) 