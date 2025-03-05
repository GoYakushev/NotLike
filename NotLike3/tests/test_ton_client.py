import unittest
from unittest.mock import AsyncMock, patch, MagicMock  #  MagicMock
from core.blockchain.ton_client import TONClient
from toncenter_client import TonCenterClient  #  TonCenterClient
from tonsdk.utils import Address, to_nano
from tonsdk.contract.wallet import Wallets, WalletVersionEnum #  Wallets
from tonsdk.contract import JettonWallet  #  JettonWallet
from tonsdk.boc import Cell

class TestTONClient(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.client_mock = AsyncMock(spec=TonCenterClient)
        self.ton_client = TONClient(api_key="test_api_key")
        self.ton_client.client = self.client_mock  #  client
        #  ton_client
        self.ton_client.ton_client = AsyncMock()

    async def test_create_wallet(self):
        """Тест создания кошелька."""
        mock_wallet = AsyncMock()
        mock_wallet.address.to_string.return_value = "test_address"
        with patch('tonsdk.contract.wallet.Wallets.create', return_value=(["word1", "word2"], mock_wallet)):
            wallet = self.ton_client.create_wallet()

        self.assertIn('address', wallet)
        self.assertIn('private_key', wallet)
        self.assertEqual(wallet['address'], "test_address")
        self.assertEqual(wallet['private_key'], "word1 word2")
        Wallets.create.assert_called_once_with(version=WalletVersionEnum.v4r2) #  версия

    async def test_get_balance_ton(self):
        """Тест получения баланса TON."""
        self.client_mock.get_address_information.return_value = AsyncMock(balance=1234567890)  # 1.23456789 TON
        balance = await self.ton_client.get_balance("test_address")
        self.assertAlmostEqual(balance, 1.23456789)
        self.client_mock.get_address_information.assert_called_once_with(address=Address("test_address"))

    # @unittest.skip("Jetton balance retrieval not implemented") #  убираем skip
    async def test_get_balance_jetton(self):
        """Тест получения баланса Jetton."""
        mock_jetton_wallet = MagicMock(spec=JettonWallet)  #  MagicMock
        mock_jetton_wallet.get_wallet_address.return_value = "jetton_wallet_address"
        mock_jetton_wallet.get_data.return_value = {
            'balance': '1000000000',  # 1 Jetton (с 9 decimals)
            'jetton_master': MagicMock(metadata={'decimals': '9'})
        }

        with patch('tonsdk.contract.JettonWallet', return_value=mock_jetton_wallet):
            balance = await self.ton_client.get_balance("test_address", "jetton_master_address")

        self.assertAlmostEqual(balance, 1.0)
        mock_jetton_wallet.get_wallet_address.assert_called_once_with(Address("test_address"))
        mock_jetton_wallet.get_data.assert_called_once()

    async def test_get_balance_exception(self):
        """Тест: исключение при получении баланса."""
        self.client_mock.get_address_information.side_effect = Exception("Network error")
        balance = await self.ton_client.get_balance("test_address")
        self.assertEqual(balance, 0.0)

    # @unittest.skip("TON transfer not implemented") #  убираем skip
    async def test_transfer_ton_success(self):
        """Тест успешного перевода TON."""
        mock_wallet = MagicMock()
        #  from_mnemonics
        with patch('tonsdk.contract.wallet.Wallets.from_mnemonics', return_value=(None, mock_wallet)):
            self.ton_client.ton_client.get_seqno.return_value = 123  #  seqno
            #  create_transfer_message
            mock_transfer_message = MagicMock()
            mock_transfer_message.to_boc.return_value = b'mocked_boc_data'  #  boc
            mock_wallet.create_transfer_message.return_value = {"message": mock_transfer_message}
            #  raw_send_message
            self.ton_client.ton_client.raw_send_message.return_value = "ok"

            result = await self.ton_client.transfer("word1 word2", "recipient_address", 1.5)

        self.assertTrue(result['success'])
        self.assertEqual(result['transaction_id'], 'Not implemented') #  пока Not implemented
        Wallets.from_mnemonics.assert_called_once_with(["word1", "word2"], version=WalletVersionEnum.v4r2)
        self.ton_client.ton_client.get_seqno.assert_called_once_with(mock_wallet.address)
        mock_wallet.create_transfer_message.assert_called_once_with(
            to_addr="recipient_address", amount=1500000000, seqno=123
        )
        self.ton_client.ton_client.raw_send_message.assert_called_once_with(b'mocked_boc_data')

    # @unittest.skip("TON transfer not implemented") #  убираем skip
    async def test_transfer_jetton_success(self):
        """Тест успешного перевода Jetton."""
        mock_wallet = MagicMock()
        mock_jetton_wallet = MagicMock(spec=JettonWallet)
        mock_jetton_wallet.get_wallet_address.return_value = "sender_jetton_wallet_address"
        mock_jetton_wallet.get_data.return_value = {'jetton_master': MagicMock(metadata={'decimals': '9'})}

        with patch('tonsdk.contract.wallet.Wallets.from_mnemonics', return_value=(None, mock_wallet)):
            with patch('tonsdk.contract.JettonWallet', return_value=mock_jetton_wallet):
                self.ton_client.ton_client.get_seqno.return_value = 123
                mock_transfer_message = MagicMock()
                mock_transfer_message.to_boc.return_value = b'mocked_boc_data'
                mock_jetton_wallet.create_transfer_message.return_value = {"message": mock_transfer_message}
                self.ton_client.ton_client.raw_send_message.return_value = "ok"

                result = await self.ton_client.transfer("word1 word2", "recipient_address", 2.5, "jetton_master_address")

        self.assertTrue(result['success'])
        self.assertEqual(result['transaction_id'], 'Not implemented')
        Wallets.from_mnemonics.assert_called_once_with(["word1", "word2"], version=WalletVersionEnum.v4r2)
        self.ton_client.ton_client.get_seqno.assert_called_once_with(mock_wallet.address)
        mock_jetton_wallet.get_wallet_address.assert_called_once()
        mock_jetton_wallet.create_transfer_message.assert_called_once_with(
            to_address=Address("recipient_address"), amount=2500000000, seqno=123, forward_ton_amount=100000000, response_address=mock_wallet.address
        )
        self.ton_client.ton_client.raw_send_message.assert_called_once_with(b'mocked_boc_data')
        mock_jetton_wallet.get_data.assert_called_once()

    async def test_transfer_exception(self):
        """Тест: исключение при переводе."""
        with patch('tonsdk.contract.wallet.Wallets.from_mnemonics', side_effect=Exception("Some error")):
            result = await self.ton_client.transfer("word1 word2", "recipient_address", 1.5)
        self.assertFalse(result['success'])
        self.assertIn("Some error", result['error']) 