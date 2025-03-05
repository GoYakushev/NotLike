import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from services.spot.spot_service import SpotService, OrderBook, StonfiAPI
from core.database.models import User, SpotOrder, Wallet
from core.blockchain.solana_client import SolanaClient
from core.blockchain.ton_client import TONClient


class TestSpotService(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.db_mock = AsyncMock()
        self.wallet_service_mock = AsyncMock()
        self.solana_client_mock = AsyncMock(spec=SolanaClient)
        self.ton_client_mock = AsyncMock(spec=TONClient)
        self.stonfi_api_mock = AsyncMock(spec=StonfiAPI)  #  StonfiAPI
        self.spot_service = SpotService(
            self.db_mock, self.wallet_service_mock, self.solana_client_mock, self.ton_client_mock, None, self.stonfi_api_mock
        )
        self.test_user = User(telegram_id=123, username="testuser")
        self.session_mock = AsyncMock()
        self.db_mock.get_session.return_value = self.session_mock

    async def test_create_limit_order_success(self):
        """Тест успешного создания LIMIT ордера."""
        self.session_mock.query.return_value.filter_by.return_value.first.return_value = self.test_user
        result = await self.spot_service.create_limit_order(123, "SOL", "USDT", "BUY", 1.0, 50.0)
        self.assertTrue(result['success'])
        self.session_mock.add.assert_called_once()
        self.session_mock.commit.assert_called()

        order_book = self.spot_service.get_order_book("SOL", "USDT")
        self.assertEqual(len(order_book.bids), 1)
        self.assertEqual(order_book.bids[0].user_id, 123)
        self.assertEqual(order_book.bids[0].order_type, "LIMIT")

    async def test_create_limit_order_user_not_found(self):
        """Тест: пользователь не найден."""
        self.session_mock.query.return_value.filter_by.return_value.first.return_value = None
        result = await self.spot_service.create_limit_order(123, "SOL", "USDT", "BUY", 1.0, 50.0)
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'Пользователь не найден')
        self.session_mock.add.assert_not_called()
        self.session_mock.commit.assert_not_called()

    async def test_create_limit_order_exception(self):
        """Тест: исключение при создании ордера."""
        self.session_mock.query.return_value.filter_by.return_value.first.return_value = self.test_user
        self.session_mock.add.side_effect = Exception("Some DB error")
        result = await self.spot_service.create_limit_order(123, "SOL", "USDT", "BUY", 1.0, 50.0)
        self.assertFalse(result['success'])
        self.assertIn("Some DB error", result['error'])
        self.session_mock.rollback.assert_called_once()
        self.session_mock.commit.assert_not_called()

    async def test_create_market_order_success(self):
        """Тест успешного создания MARKET ордера."""
        self.session_mock.query.return_value.filter_by.return_value.first.return_value = self.test_user
        with patch.object(self.spot_service, 'process_order', new_callable=AsyncMock) as mock_process_order:
            result = await self.spot_service.create_market_order(123, "SOL", "USDT", "BUY", 1.0)

        self.assertTrue(result['success'])
        self.session_mock.add.assert_called_once()
        self.session_mock.commit.assert_called()
        mock_process_order.assert_awaited_once()

    async def test_create_market_order_user_not_found(self):
        """Тест: пользователь не найден (MARKET)."""
        self.session_mock.query.return_value.filter_by.return_value.first.return_value = None
        result = await self.spot_service.create_market_order(123, "SOL", "USDT", "BUY", 1.0)
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'Пользователь не найден')

    async def test_cancel_order_success(self):
        """Тест успешной отмены ордера."""
        order = SpotOrder(id=1, user_id=123, base_currency="SOL", quote_currency="USDT", order_type="LIMIT", side="BUY", price=50.0, quantity=1.0, status="OPEN")
        self.session_mock.query.return_value.get.return_value = order
        order_book = self.spot_service.get_order_book("SOL", "USDT")
        order_book.add_order(order)

        result = await self.spot_service.cancel_order(123, 1)
        self.assertTrue(result['success'])
        self.assertEqual(order.status, "CANCELLED")
        self.session_mock.commit.assert_called_once()
        self.assertEqual(len(order_book.bids), 0)

    async def test_cancel_order_not_found(self):
        """Тест: ордер не найден."""
        self.session_mock.query.return_value.get.return_value = None
        result = await self.spot_service.cancel_order(123, 1)
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'Ордер не найден')

    async def test_cancel_order_wrong_user(self):
        """Тест: попытка отменить чужой ордер."""
        order = SpotOrder(id=1, user_id=456, base_currency="SOL", quote_currency="USDT", order_type="LIMIT", side="BUY", price=50.0, quantity=1.0, status="OPEN")
        self.session_mock.query.return_value.get.return_value = order
        result = await self.spot_service.cancel_order(123, 1)
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'Нельзя отменить чужой ордер')

    async def test_cancel_order_wrong_status(self):
        """Тест: попытка отменить ордер не в статусе OPEN."""
        order = SpotOrder(id=1, user_id=123, base_currency="SOL", quote_currency="USDT", order_type="LIMIT", side="BUY", price=50.0, quantity=1.0, status="FILLED")
        self.session_mock.query.return_value.get.return_value = order
        result = await self.spot_service.cancel_order(123, 1)
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'Нельзя отменить ордер в статусе, отличном от OPEN')

    async def test_match_and_execute_orders(self):
        """Тест мэтчинга и исполнения ордеров."""
        order_book = self.spot_service.get_order_book("SOL", "USDT")
        buy_order = SpotOrder(id=1, user_id=1, base_currency="SOL", quote_currency="USDT", order_type="LIMIT", side="BUY", price=50.0, quantity=1.0, status="OPEN")
        sell_order = SpotOrder(id=2, user_id=2, base_currency="SOL", quote_currency="USDT", order_type="LIMIT", side="SELL", price=49.0, quantity=1.0, status="OPEN")
        order_book.add_order(buy_order)
        order_book.add_order(sell_order)

        with patch.object(self.spot_service, 'execute_matched_orders', new_callable=AsyncMock) as mock_execute:
            self.spot_service.match_and_execute_orders(order_book)

        mock_execute.assert_awaited_once_with(buy_order, sell_order)
        self.assertEqual(len(order_book.bids), 0)
        self.assertEqual(len(order_book.asks), 0)

    async def test_match_and_execute_orders_partial(self):
        """Тест мэтчинга и исполнения ордеров (частичное исполнение)."""
        order_book = self.spot_service.get_order_book("SOL", "USDT")
        buy_order = SpotOrder(id=1, user_id=1, base_currency="SOL", quote_currency="USDT", order_type="LIMIT", side="BUY", price=50.0, quantity=1.0, status="OPEN")
        sell_order = SpotOrder(id=2, user_id=2, base_currency="SOL", quote_currency="USDT", order_type="LIMIT", side="SELL", price=49.0, quantity=2.0, status="OPEN")
        order_book.add_order(buy_order)
        order_book.add_order(sell_order)

        with patch.object(self.spot_service, 'execute_matched_orders', new_callable=AsyncMock) as mock_execute:
            self.spot_service.match_and_execute_orders(order_book)

        mock_execute.assert_awaited_once_with(buy_order, sell_order)
        self.assertEqual(len(order_book.bids), 0)
        self.assertEqual(len(order_book.asks), 1)
        self.assertEqual(order_book.asks[0].quantity, 1.0)

    async def test_match_and_execute_orders_no_match(self):
        """Тест: нет мэтчинга."""
        order_book = self.spot_service.get_order_book("SOL", "USDT")
        buy_order = SpotOrder(id=1, user_id=1, base_currency="SOL", quote_currency="USDT", order_type="LIMIT", side="BUY", price=49.0, quantity=1.0, status="OPEN")
        sell_order = SpotOrder(id=2, user_id=2, base_currency="SOL", quote_currency="USDT", order_type="LIMIT", side="SELL", price=50.0, quantity=1.0, status="OPEN")
        order_book.add_order(buy_order)
        order_book.add_order(sell_order)

        with patch.object(self.spot_service, 'execute_matched_orders', new_callable=AsyncMock) as mock_execute:
            self.spot_service.match_and_execute_orders(order_book)

        mock_execute.assert_not_awaited()
        self.assertEqual(len(order_book.bids), 1)
        self.assertEqual(len(order_book.asks), 1)

    async def test_execute_matched_orders(self):
        """Тест исполнения ордеров."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock

        buy_order = SpotOrder(id=1, user_id=1, base_currency="SOL", quote_currency="USDT", order_type="LIMIT", side="BUY", price=50.0, quantity=1.0, status="OPEN", filled_amount=0.0)
        sell_order = SpotOrder(id=2, user_id=2, base_currency="SOL", quote_currency="USDT", order_type="LIMIT", side="SELL", price=49.0, quantity=1.0, status="OPEN", filled_amount=0.0)

        buy_user_wallet_base = Wallet(user_id=1, network="SOL", address="buy_base_address", balance=0.0, token_address=None)
        buy_user_wallet_quote = Wallet(user_id=1, network="SOL", address="buy_quote_address", balance=100.0, token_address="usdt_address")
        sell_user_wallet_base = Wallet(user_id=2, network="SOL", address="sell_base_address", balance=2.0, token_address=None)
        sell_user_wallet_quote = Wallet(user_id=2, network="SOL", address="sell_quote_address", balance=50.0, token_address="usdt_address")

        session_mock.query.return_value.filter_by.return_value.first.side_effect = [
            buy_user_wallet_base, buy_user_wallet_quote, sell_user_wallet_base, sell_user_wallet_quote
        ]

        await self.spot_service.execute_matched_orders(buy_order, sell_order)

        self.assertAlmostEqual(buy_user_wallet_base.balance, 1.0)
        self.assertAlmostEqual(buy_user_wallet_quote.balance, 51.0)
        self.assertAlmostEqual(sell_user_wallet_base.balance, 1.0)
        self.assertAlmostEqual(sell_user_wallet_quote.balance, 99.0)

        self.assertEqual(buy_order.status, "FILLED")
        self.assertEqual(sell_order.status, "FILLED")
        self.assertEqual(buy_order.filled_amount, 1.0)
        self.assertEqual(sell_order.filled_amount, 1.0)

        session_mock.commit.assert_called_once()

    async def test_execute_matched_orders_partial(self):
        """Тест исполнения ордеров (частичное исполнение)."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock

        buy_order = SpotOrder(id=1, user_id=1, base_currency="SOL", quote_currency="USDT", order_type="LIMIT", side="BUY", price=50.0, quantity=2.0, status="OPEN", filled_amount=0.0)
        sell_order = SpotOrder(id=2, user_id=2, base_currency="SOL", quote_currency="USDT", order_type="LIMIT", side="SELL", price=49.0, quantity=1.0, status="OPEN", filled_amount=0.0)

        buy_user_wallet_base = Wallet(user_id=1, network="SOL", address="buy_base_address", balance=0.0, token_address=None)
        buy_user_wallet_quote = Wallet(user_id=1, network="SOL", address="buy_quote_address", balance=100.0, token_address="usdt_address")
        sell_user_wallet_base = Wallet(user_id=2, network="SOL", address="sell_base_address", balance=2.0, token_address=None)
        sell_user_wallet_quote = Wallet(user_id=2, network="SOL", address="sell_quote_address", balance=50.0, token_address="usdt_address")

        session_mock.query.return_value.filter_by.return_value.first.side_effect = [
            buy_user_wallet_base, buy_user_wallet_quote, sell_user_wallet_base, sell_user_wallet_quote
        ]

        await self.spot_service.execute_matched_orders(buy_order, sell_order)

        self.assertAlmostEqual(buy_user_wallet_base.balance, 1.0)
        self.assertAlmostEqual(buy_user_wallet_quote.balance, 51.0)
        self.assertAlmostEqual(sell_user_wallet_base.balance, 1.0)
        self.assertAlmostEqual(sell_user_wallet_quote.balance, 99.0)

        self.assertEqual(buy_order.status, "PARTIALLY_FILLED")
        self.assertEqual(sell_order.status, "FILLED")
        self.assertEqual(buy_order.filled_amount, 1.0)
        self.assertEqual(sell_order.filled_amount, 1.0)
        self.assertEqual(buy_order.quantity, 1.0)

        session_mock.commit.assert_called_once()

    async def test_execute_matched_orders_wallet_not_found(self):
        """Тест: один из кошельков не найден."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        buy_order = SpotOrder(id=1, user_id=1, base_currency="SOL", quote_currency="USDT", order_type="LIMIT", side="BUY", price=50.0, quantity=1.0, status="OPEN", filled_amount=0.0)
        sell_order = SpotOrder(id=2, user_id=2, base_currency="SOL", quote_currency="USDT", order_type="LIMIT", side="SELL", price=49.0, quantity=1.0, status="OPEN", filled_amount=0.0)

        session_mock.query.return_value.filter_by.return_value.first.side_effect = [
            None, None, None, None
        ]
        with self.assertRaises(Exception) as context:
            await self.spot_service.execute_matched_orders(buy_order, sell_order)
        self.assertIn("Один из кошельков не найден", str(context.exception))
        session_mock.commit.assert_not_called()
        session_mock.rollback.assert_called_once()

    async def test_process_order_market_buy_sol_success(self):
        """Тест успешного исполнения MARKET BUY ордера (SOL)."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        order = SpotOrder(id=1, user_id=123, base_currency="SOL", quote_currency="USDT", order_type="MARKET", side="BUY", quantity=1.0, status="OPEN")
        session_mock.query.return_value.get.return_value = order

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {'price': 49.5}
        with patch('aiohttp.ClientSession.post', return_value=mock_response) as mock_post:
            result = await self.spot_service.process_order(1)

        self.assertTrue(result['success'])
        self.assertEqual(order.status, "FILLED")
        self.assertEqual(order.filled_amount, 1.0)
        self.assertAlmostEqual(order.price, 49.5)
        mock_post.assert_called_once_with("https://api.orca.so/v1/market/buy", json={"base": "SOL", "quote": "USDT", "amount": 1.0})
        session_mock.commit.assert_called()

    async def test_process_order_market_sell_sol_success(self):
        """Тест успешного исполнения MARKET SELL ордера (SOL)."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        order = SpotOrder(id=1, user_id=123, base_currency="SOL", quote_currency="USDT", order_type="MARKET", side="SELL", quantity=1.0, status="OPEN")
        session_mock.query.return_value.get.return_value = order

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {'price': 49.5}
        with patch('aiohttp.ClientSession.post', return_value=mock_response) as mock_post:
            result = await self.spot_service.process_order(1)

        self.assertTrue(result['success'])
        self.assertEqual(order.status, "FILLED")
        mock_post.assert_called_once_with("https://api.orca.so/v1/market/sell", json={"base": "SOL", "quote": "USDT", "amount": 1.0})
        session_mock.commit.assert_called()

    async def test_process_order_orca_api_error(self):
        """Тест: ошибка Orca API."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        order = SpotOrder(id=1, user_id=123, base_currency="SOL", quote_currency="USDT", order_type="MARKET", side="BUY", quantity=1.0, status="OPEN")
        session_mock.query.return_value.get.return_value = order

        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.json.return_value = {'error': 'Some Orca error'}
        with patch('aiohttp.ClientSession.post', return_value=mock_response) as mock_post:
            result = await self.spot_service.process_order(1)

        self.assertFalse(result['success'])
        self.assertIn("Orca API error", result['error'])
        session_mock.commit.assert_not_called()
        session_mock.rollback.assert_called_once()

    async def test_process_order_unsupported_currency(self):
        """Тест: неподдерживаемая валюта."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        order = SpotOrder(id=1, user_id=123, base_currency="XXX", quote_currency="USDT", order_type="MARKET", side="BUY", quantity=1.0, status="OPEN")
        session_mock.query.return_value.get.return_value = order

        result = await self.spot_service.process_order(1)
        self.assertFalse(result['success'])
        self.assertIn("Неподдерживаемая валюта", result['error'])
        session_mock.commit.assert_not_called()
        session_mock.rollback.assert_called_once()

    async def test_process_order_market_buy_ton_success(self):
        """Тест успешного исполнения MARKET BUY ордера (TON)."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        order = SpotOrder(id=1, user_id=123, base_currency="TON_JUSDT", quote_currency="TON_USDT", order_type="MARKET", side="BUY", quantity=1.0, status="OPEN")
        session_mock.query.return_value.get.return_value = order

        #  StonfiAPI
        self.stonfi_api_mock.market_buy.return_value = {'success': True, 'price': 1.5, 'executed_amount': 1.0}

        result = await self.spot_service.process_order(1)

        self.assertTrue(result['success'])
        self.assertEqual(order.status, "FILLED")
        self.assertEqual(order.filled_amount, 1.0)
        self.assertAlmostEqual(order.price, 1.5)
        self.stonfi_api_mock.market_buy.assert_awaited_once_with("JUSDT", "USDT", 1.0)  #  аргументы
        session_mock.commit.assert_called()

    async def test_process_order_market_sell_ton_success(self):
        """Тест успешного исполнения MARKET SELL ордера (TON)."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        order = SpotOrder(id=1, user_id=123, base_currency="TON_JUSDT", quote_currency="TON_USDT", order_type="MARKET", side="SELL", quantity=1.0, status="OPEN")
        session_mock.query.return_value.get.return_value = order

        self.stonfi_api_mock.market_sell.return_value = {'success': True, 'price': 1.5, 'executed_amount': 1.0}

        result = await self.spot_service.process_order(1)

        self.assertTrue(result['success'])
        self.assertEqual(order.status, "FILLED")
        self.stonfi_api_mock.market_sell.assert_awaited_once_with("JUSDT", "USDT", 1.0)
        session_mock.commit.assert_called()

    async def test_process_order_stonfi_api_error(self):
        """Тест: ошибка Ston.fi API."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        order = SpotOrder(id=1, user_id=123, base_currency="TON_JUSDT", quote_currency="TON_USDT", order_type="MARKET", side="BUY", quantity=1.0, status="OPEN")
        session_mock.query.return_value.get.return_value = order

        self.stonfi_api_mock.market_buy.return_value = {'success': False, 'error': 'Some Ston.fi error'}

        result = await self.spot_service.process_order(1)

        self.assertFalse(result['success'])
        self.assertIn("Some Ston.fi error", result['error'])
        self.assertEqual(order.status, "FAILED")  #  статус
        session_mock.commit.assert_called()  #  commit
        session_mock.rollback.assert_not_called()

    async def test_get_open_orders(self):
        """Тест получения списка открытых ордеров."""
        order1 = SpotOrder(id=1, user_id=123, status="OPEN")
        order2 = SpotOrder(id=2, user_id=123, status="OPEN")
        self.session_mock.query.return_value.filter_by.return_value.all.return_value = [order1, order2]
        orders = await self.spot_service.get_open_orders(123)
        self.assertEqual(len(orders), 2)
        self.assertEqual(orders[0].id, 1)
        self.assertEqual(orders[1].id, 2)

    async def test_get_order_history(self):
        """Тест получения истории ордеров."""
        order1 = SpotOrder(id=1, user_id=123, status="FILLED")
        order2 = SpotOrder(id=2, user_id=123, status="CANCELLED")
        self.session_mock.query.return_value.filter_by.return_value.all.return_value = [order1, order2]
        orders = await self.spot_service.get_order_history(123)
        self.assertEqual(len(orders), 2)
        self.assertEqual(orders[0].id, 1)
        self.assertEqual(orders[1].id, 2)


class TestStonfiAPI(unittest.IsolatedAsyncioTestCase):

    async def test_market_buy_success(self):
        """Тест успешной рыночной покупки."""
        stonfi_api = StonfiAPI(api_key="test_api_key")
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {'price': 1.5, 'executed_amount': 1.0}

        with patch('aiohttp.ClientSession.post', return_value=mock_response) as mock_post:
            result = await stonfi_api.market_buy("TON", "USDT", 1.0)

        self.assertTrue(result['success'])
        self.assertAlmostEqual(result['price'], 1.5)
        self.assertAlmostEqual(result['executed_amount'], 1.0)
        mock_post.assert_called_once_with(
            "https://api.ston.fi/v1/spot/buy",
            json={"base_asset": "TON", "quote_asset": "USDT", "amount": 1.0},
            headers={"X-API-KEY": "test_api_key"}
        )

    async def test_market_buy_error(self):
        """Тест ошибки Ston.fi API (покупка)."""
        stonfi_api = StonfiAPI(api_key="test_api_key")
        mock_response = AsyncMock()
        mock_response.status = 400  #  код ошибки
        mock_response.text.return_value = "Some error message"

        with patch('aiohttp.ClientSession.post', return_value=mock_response) as mock_post:
            result = await stonfi_api.market_buy("TON", "USDT", 1.0)

        self.assertFalse(result['success'])
        self.assertIn("Ston.fi API error", result['error'])
        mock_post.assert_called_once()

    async def test_market_sell_success(self):
        """Тест успешной рыночной продажи."""
        stonfi_api = StonfiAPI(api_key="test_api_key")
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {'price': 1.5, 'executed_amount': 1.0}

        with patch('aiohttp.ClientSession.post', return_value=mock_response) as mock_post:
            result = await stonfi_api.market_sell("TON", "USDT", 1.0)

        self.assertTrue(result['success'])
        self.assertAlmostEqual(result['price'], 1.5)
        self.assertAlmostEqual(result['executed_amount'], 1.0)
        mock_post.assert_called_once_with(
            "https://api.ston.fi/v1/spot/sell",
            json={"base_asset": "TON", "quote_asset": "USDT", "amount": 1.0},
            headers={"X-API-KEY": "test_api_key"}
        )

    async def test_market_sell_error(self):
        """Тест ошибки Ston.fi API (продажа)."""
        stonfi_api = StonfiAPI(api_key="test_api_key")
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text.return_value = "Internal server error"

        with patch('aiohttp.ClientSession.post', return_value=mock_response) as mock_post:
            result = await stonfi_api.market_sell("TON", "USDT", 1.0)

        self.assertFalse(result['success'])
        self.assertIn("Ston.fi API error", result['error'])
        mock_post.assert_called_once()

    async def test_get_price_success(self):
        """Тест успешного получения цены."""
        stonfi_api = StonfiAPI(api_key="test_api_key")
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"price": "10.2323"}  #  цена

        with patch('aiohttp.ClientSession.get', return_value=mock_response) as mock_get:
            result = await stonfi_api.get_price("TON", "USDT")

        self.assertAlmostEqual(result, 10.2323)
        mock_get.assert_called_once_with(
            "https://api.ston.fi/v1/spot/price",
            params={"base_asset": "TON", "quote_asset": "USDT"},
            headers={"X-API-KEY": "test_api_key"}
        )

    async def test_get_price_error(self):
        """Тест ошибки при получении цены."""
        stonfi_api = StonfiAPI(api_key="test_api_key")
        mock_response = AsyncMock()
        mock_response.status = 404  #  Not Found
        mock_response.text.return_value = "Not Found"

        with patch('aiohttp.ClientSession.get', return_value=mock_response) as mock_get:
            result = await stonfi_api.get_price("TON", "USDT")

        self.assertIsNone(result)  #  None
        mock_get.assert_called_once() 