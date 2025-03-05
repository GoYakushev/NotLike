import unittest
from unittest.mock import AsyncMock, patch
from core.database.models import User, P2POrder
from services.p2p.p2p_service import P2PService
from bot.config import Config

# Предполагаем, что у вас есть класс Config с настройками
config = Config()

class TestP2PService(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Создаем моки для зависимостей
        self.db_mock = AsyncMock()
        self.wallet_service_mock = AsyncMock()
        self.notification_service_mock = AsyncMock()

        # Создаем экземпляр P2PService с моками
        self.p2p_service = P2PService(
            self.db_mock,
            self.wallet_service_mock,
            self.notification_service_mock
        )

        # Создаем тестового пользователя
        self.test_user = User(telegram_id=12345, username="testuser")
        self.test_user2 = User(telegram_id=67890, username="testuser2")

    async def test_create_p2p_order_success(self):
        """Тест успешного создания P2P ордера."""

        # Подготовка данных для теста
        order_type = "BUY"
        crypto_amount = 1.0
        fiat_amount = 100.0
        fiat_currency = "USD"
        payment_method = "Bank Transfer"
        limit_min = 50.0
        limit_max = 200.0
        time_limit = 30

        # Мокируем метод get_session
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock

        # Мокируем методы сессии
        session_mock.query.return_value.filter_by.return_value.first.return_value = self.test_user
        session_mock.add = AsyncMock()
        session_mock.commit = AsyncMock()

        # Вызываем метод create_p2p_order
        result = await self.p2p_service.create_p2p_order(
            self.test_user.telegram_id,
            order_type,
            crypto_amount,
            fiat_amount,
            fiat_currency,
            payment_method,
            limit_min,
            limit_max,
            time_limit
        )

        # Проверяем, что ордер был создан и добавлен в базу данных
        self.assertTrue(result['success'])
        self.assertIsNotNone(result['order_id'])
        session_mock.add.assert_called_once()
        session_mock.commit.assert_called_once()

    async def test_create_p2p_order_user_not_found(self):
        """Тест: пользователь не найден."""

        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        session_mock.query.return_value.filter_by.return_value.first.return_value = None

        result = await self.p2p_service.create_p2p_order(
            99999, "BUY", 1.0, 100.0, "USD", "Bank", 50.0, 200.0, 30
        )

        self.assertFalse(result['success'])
        self.assertEqual(result['error'], "Пользователь не найден")

    async def test_create_p2p_order_invalid_limits(self):
        """Тест: неверные лимиты."""

        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        session_mock.query.return_value.filter_by.return_value.first.return_value = self.test_user

        result = await self.p2p_service.create_p2p_order(
            self.test_user.telegram_id, "BUY", 1.0, 100.0, "USD", "Bank", 200.0, 50.0, 30
        )  # min > max

        self.assertFalse(result['success'])
        self.assertEqual(result['error'], "Минимальный лимит не может быть больше максимального")

    async def test_create_p2p_order_exception(self):
        """Тест: исключение при создании ордера."""

        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        session_mock.query.return_value.filter_by.return_value.first.return_value = self.test_user
        session_mock.commit.side_effect = Exception("Database error") # Симулируем ошибку БД

        result = await self.p2p_service.create_p2p_order(
            self.test_user.telegram_id, "BUY", 1.0, 100.0, "USD", "Bank", 50.0, 200.0, 30
        )

        self.assertFalse(result['success'])
        self.assertIn("Ошибка при создании P2P ордера", result['error'])

    async def test_find_matching_p2p_orders(self):
        """Тест поиска подходящих ордеров."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock

        # Создаем ордер, для которого будем искать подходящие
        order = P2POrder(
            id=1, user_id=self.test_user.id, type="BUY",
            crypto_amount=1.0, fiat_amount=100.0, fiat_currency="USD",
            payment_method="Bank", status="OPEN"
        )
        session_mock.query.return_value.get.return_value = order

        # Создаем список подходящих ордеров
        matching_order1 = P2POrder(
            id=2, user_id=self.test_user2.id, type="SELL",
            crypto_amount=1.1, fiat_amount=110.0, fiat_currency="USD",
            payment_method="Bank", status="OPEN"
        )
        matching_order2 = P2POrder(
            id=3, user_id=self.test_user2.id, type="SELL",
            crypto_amount=0.95, fiat_amount=95.0, fiat_currency="USD",
            payment_method="Bank", status="OPEN"
        )
        # Неподходящий ордер (другой тип)
        non_matching_order1 = P2POrder(
            id=4, user_id=self.test_user2.id, type="BUY",
            crypto_amount=1.0, fiat_amount=100.0, fiat_currency="USD",
            payment_method="Bank", status="OPEN"
        )
        # Неподходящий ордер (другая валюта)
        non_matching_order2 = P2POrder(
            id=5, user_id=self.test_user2.id, type="SELL",
            crypto_amount=1.0, fiat_amount=100.0, fiat_currency="EUR",
            payment_method="Bank", status="OPEN"
        )
        # Неподходящий ордер (закрыт)
        non_matching_order3 = P2POrder(
            id=6, user_id=self.test_user2.id, type="SELL",
            crypto_amount=1.0, fiat_amount=100.0, fiat_currency="USD",
            payment_method="Bank", status="CLOSED"
        )

        session_mock.query.return_value.filter.return_value.all.return_value = [
            matching_order1, matching_order2, non_matching_order1, non_matching_order2, non_matching_order3
        ]

        result = await self.p2p_service.find_matching_p2p_orders(order.id)

        # Проверяем, что найдены только подходящие ордера
        self.assertEqual(len(result), 2)
        self.assertIn(matching_order1, result)
        self.assertIn(matching_order2, result)
        self.assertNotIn(non_matching_order1, result)
        self.assertNotIn(non_matching_order2, result)
        self.assertNotIn(non_matching_order3, result)

    async def test_find_matching_p2p_orders_no_order(self):
        """Тест: ордер не найден."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        session_mock.query.return_value.get.return_value = None  # Ордер не найден

        result = await self.p2p_service.find_matching_p2p_orders(999)
        self.assertEqual(result, [])

    async def test_find_matching_p2p_orders_exception(self):
        """Тест: ошибка при поиске."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        session_mock.query.return_value.get.return_value = P2POrder(id=1) # Возвращаем ордер
        session_mock.query.return_value.filter.return_value.all.side_effect = Exception("DB Error")

        result = await self.p2p_service.find_matching_p2p_orders(1)
        self.assertEqual(result, [])

    async def test_confirm_p2p_order_success(self):
        """Тест успешного подтверждения."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock

        order = P2POrder(id=1, user_id=self.test_user.id, type="BUY", status="OPEN")
        counterparty_order = P2POrder(id=2, user_id=self.test_user2.id, type="SELL", status="OPEN")
        order.user = self.test_user # Добавляем user
        counterparty_order.user = self.test_user2 # Добавляем user

        session_mock.query.return_value.get.side_effect = [order, counterparty_order]
        session_mock.commit = AsyncMock()

        result = await self.p2p_service.confirm_p2p_order(1, 2)
        self.assertTrue(result['success'])
        self.assertEqual(order.status, "CONFIRMED")
        self.assertEqual(counterparty_order.status, "CONFIRMED")
        session_mock.commit.assert_called_once()

    async def test_confirm_p2p_order_order_not_found(self):
        """Тест: ордер не найден."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        session_mock.query.return_value.get.return_value = None

        result = await self.p2p_service.confirm_p2p_order(1, 2)
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'Ордер не найден')

    async def test_confirm_p2p_order_invalid_status(self):
        """Тест: неверный статус ордера."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock

        order = P2POrder(id=1, user_id=self.test_user.id, type="BUY", status="CLOSED")
        counterparty_order = P2POrder(id=2, user_id=self.test_user2.id, type="SELL", status="OPEN")

        session_mock.query.return_value.get.side_effect = [order, counterparty_order]

        result = await self.p2p_service.confirm_p2p_order(1, 2)
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'Один из ордеров неактивен')

    async def test_confirm_p2p_order_same_type(self):
        """Тест: ордера одного типа."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock

        order = P2POrder(id=1, user_id=self.test_user.id, type="BUY", status="OPEN")
        counterparty_order = P2POrder(id=2, user_id=self.test_user2.id, type="BUY", status="OPEN")

        session_mock.query.return_value.get.side_effect = [order, counterparty_order]

        result = await self.p2p_service.confirm_p2p_order(1, 2)
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], "Нельзя подтвердить ордер того же типа")

    async def test_confirm_p2p_order_exception(self):
        """Тест: ошибка при подтверждении."""
        session_mock = AsyncMock()
        self.db_mock.get_session.return_value = session_mock
        order = P2POrder(id=1, user_id=self.test_user.id, type="BUY", status="OPEN")
        counterparty_order = P2POrder(id=2, user_id=self.test_user2.id, type="SELL", status="OPEN")
        session_mock.query.return_value.get.side_effect = [order, counterparty_order]
        session_mock.commit.side_effect = Exception("DB Error")

        result = await self.p2p_service.confirm_p2p_order(1, 2)
        self.assertFalse(result['success'])
        self.assertIn("Ошибка при подтверждении P2P ордера", result['error'])

    # ... тесты для complete_p2p_order, cancel_p2p_order ...

    # Добавьте тесты для find_matching_p2p_orders, confirm_p2p_order, и т.д.
    # ... другие тесты для P2PService ... 