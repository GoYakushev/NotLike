import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from aiogram.dispatcher import FSMContext
from aiogram.types import Message, CallbackQuery, User as AioUser
from bot.handlers.p2p_handler import (
    p2p_start, create_p2p_order_start, choose_p2p_side, enter_base_currency,
    enter_quote_currency, enter_amount, enter_price, choose_payment_method,
    confirm_p2p_order, cancel_p2p_order_start, cancel_p2p_order_confirm,
    list_p2p_orders, my_p2p_orders, back_to_p2p_menu_handler,
    take_p2p_order_handler, cancel_p2p_order_handler, is_premium,
    P2POrderStates
)
from services.p2p.p2p_service import P2PService
from core.database.models import P2POrder, User
from datetime import datetime, timedelta
from unittest.mock import ANY


class TestP2PHandler(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.p2p_service_mock = AsyncMock(spec=P2PService)
        self.state_mock = AsyncMock(spec=FSMContext)
        self.message_mock = MagicMock(spec=Message)
        self.callback_query_mock = MagicMock(spec=CallbackQuery)
        self.message_mock.from_user.id = 123
        self.message_mock.from_user.username = "testuser"
        self.callback_query_mock.from_user.id = 123
        self.callback_query_mock.message = self.message_mock  #  message

    async def test_p2p_start(self):
        """Тест p2p_start."""
        await p2p_start(self.message_mock, self.state_mock)
        self.message_mock.answer.assert_called_once_with("Выберите действие:", reply_markup=ANY)
        self.state_mock.finish.assert_called_once()

    async def test_create_p2p_order_start(self):
        """Тест create_p2p_order_start."""
        await create_p2p_order_start(self.message_mock, self.state_mock)
        self.message_mock.answer.assert_called_once_with("Вы хотите купить или продать?", reply_markup=ANY)
        self.state_mock.set_state.assert_called_once_with(P2POrderStates.waiting_for_side.state)

    async def test_choose_p2p_side_valid(self):
        """Тест choose_p2p_side (валидный ввод)."""
        self.message_mock.text = "BUY"
        await choose_p2p_side(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.state_mock.update_data.assert_called_once_with(side="BUY")
        self.message_mock.answer.assert_called_with("Введите базовую валюту (например, TON):")
        self.state_mock.set_state.assert_called_once_with(P2POrderStates.waiting_for_base_currency.state)

    async def test_choose_p2p_side_invalid(self):
        """Тест choose_p2p_side (невалидный ввод)."""
        self.message_mock.text = "INVALID"
        await choose_p2p_side(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called_with("Неверный выбор. Пожалуйста, выберите 'BUY' или 'SELL'.", reply_markup=ANY)
        self.state_mock.update_data.assert_not_called()
        self.state_mock.set_state.assert_not_called()

    async def test_enter_base_currency(self):
        """Тест enter_base_currency."""
        self.message_mock.text = "TON"
        await enter_base_currency(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.state_mock.update_data.assert_called_once_with(base_currency="TON")
        self.message_mock.answer.assert_called_with("Введите котируемую валюту (например, USDT):")
        self.state_mock.set_state.assert_called_once_with(P2POrderStates.waiting_for_quote_currency.state)

    async def test_enter_quote_currency(self):
        """Тест enter_quote_currency."""
        self.message_mock.text = "USDT"
        await enter_quote_currency(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.state_mock.update_data.assert_called_once_with(quote_currency="USDT")
        self.message_mock.answer.assert_called_with("Введите количество базовой валюты:")
        self.state_mock.set_state.assert_called_once_with(P2POrderStates.waiting_for_amount.state)

    async def test_enter_amount_valid(self):
        """Тест enter_amount (валидный ввод)."""
        self.message_mock.text = "10.5"
        await enter_amount(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.state_mock.update_data.assert_called_once_with(amount=10.5)
        self.message_mock.answer.assert_called_with("Введите цену за единицу базовой валюты:")
        self.state_mock.set_state.assert_called_once_with(P2POrderStates.waiting_for_price.state)

    async def test_enter_amount_invalid(self):
        """Тест enter_amount (невалидный ввод)."""
        self.message_mock.text = "INVALID"
        await enter_amount(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called_with("Неверное количество. Введите положительное число.")
        self.state_mock.update_data.assert_not_called()
        self.state_mock.set_state.assert_not_called()

    async def test_enter_price_valid(self):
        """Тест enter_price (валидный ввод)."""
        self.message_mock.text = "2.5"
        await enter_price(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.state_mock.update_data.assert_called_once_with(price=2.5)
        self.message_mock.answer.assert_called_with("Выберите способ оплаты:", reply_markup=ANY)
        self.state_mock.set_state.assert_called_once_with(P2POrderStates.waiting_for_payment_method.state)

    async def test_enter_price_invalid(self):
        """Тест enter_price (невалидный ввод)."""
        self.message_mock.text = "INVALID"
        await enter_price(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called_with("Неверная цена. Введите положительное число.")
        self.state_mock.update_data.assert_not_called()
        self.state_mock.set_state.assert_not_called()

    async def test_choose_payment_method_valid(self):
        """Тест choose_payment_method (валидный ввод)."""
        self.message_mock.text = "TINKOFF"  #  способ оплаты
        await choose_payment_method(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.state_mock.update_data.assert_called_once_with(payment_method="TINKOFF")
        self.message_mock.answer.assert_called_with(ANY, reply_markup=ANY)  #  ANY
        self.state_mock.set_state.assert_called_once_with(P2POrderStates.confirm_order.state)

    async def test_choose_payment_method_invalid(self):
        """Тест choose_payment_method (невалидный ввод)."""
        self.message_mock.text = "INVALID"
        await choose_payment_method(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called_with("Неверный способ оплаты. Выберите из списка:", reply_markup=ANY)
        self.state_mock.update_data.assert_not_called()
        self.state_mock.set_state.assert_not_called()

    async def test_confirm_p2p_order_success(self):
        """Тест confirm_p2p_order (успех)."""
        self.message_mock.text = "Подтвердить"
        self.state_mock.get_data.return_value = {
            'side': "BUY",
            'base_currency': "TON",
            'quote_currency': "USDT",
            'amount': 10.0,
            'price': 2.5,
            'payment_method': "TINKOFF"
        }
        self.p2p_service_mock.create_order.return_value = {'success': True, 'order_id': 1}
        await confirm_p2p_order(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.p2p_service_mock.create_order.assert_awaited_once_with(
            user_id=123, side="BUY", base_currency="TON", quote_currency="USDT",
            amount=10.0, price=2.5, payment_method="TINKOFF"
        )
        self.message_mock.answer.assert_called_with("P2P ордер создан! ID: 1")
        self.state_mock.finish.assert_called_once()

    async def test_confirm_p2p_order_failure(self):
        """Тест confirm_p2p_order (ошибка)."""
        self.message_mock.text = "Подтвердить"
        self.state_mock.get_data.return_value = {
            'side': "BUY",
            'base_currency': "TON",
            'quote_currency': "USDT",
            'amount': 10.0,
            'price': 2.5,
            'payment_method': "TINKOFF"
        }
        self.p2p_service_mock.create_order.return_value = {'success': False, 'error': 'Some error'}
        await confirm_p2p_order(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called_with("Ошибка при создании P2P ордера: Some error")
        self.state_mock.finish.assert_called_once()

    async def test_confirm_p2p_order_invalid(self):
        """Тест confirm_p2p_order (неверный ввод)."""
        self.message_mock.text = "INVALID"
        await confirm_p2p_order(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called_with("Пожалуйста, нажмите 'Подтвердить' или 'Отмена'.", reply_markup=ANY)
        self.state_mock.finish.assert_not_called()

    async def test_cancel_p2p_order_start_no_orders(self):
        """Тест cancel_p2p_order_start (нет ордеров)."""
        self.p2p_service_mock.get_user_p2p_orders.return_value = []
        await cancel_p2p_order_start(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called_with("У вас нет открытых P2P ордеров.", reply_markup=ANY)
        self.state_mock.finish.assert_called_once()

    async def test_cancel_p2p_order_start_with_orders(self):
        """Тест cancel_p2p_order_start (есть ордера)."""
        order1 = P2POrder(id=1, side="BUY", amount=1.0, base_currency="TON", price=2.5, quote_currency="USDT")
        order2 = P2POrder(id=2, side="SELL", amount=5.0, base_currency="SOL", price=50.0, quote_currency="USDT")
        self.p2p_service_mock.get_user_p2p_orders.return_value = [order1, order2]
        await cancel_p2p_order_start(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called_with(ANY)  #  список ордеров
        self.message_mock.answer.assert_called_with("Введите ID ордера, который хотите отменить:")
        self.state_mock.set_state.assert_called_once_with(P2POrderStates.waiting_for_order_id.state)

    async def test_cancel_p2p_order_confirm_success(self):
        """Тест cancel_p2p_order_confirm (успех)."""
        self.message_mock.text = "1"
        self.p2p_service_mock.cancel_order.return_value = {'success': True}
        await cancel_p2p_order_confirm(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.p2p_service_mock.cancel_order.assert_awaited_once_with(1, 123)
        self.message_mock.answer.assert_called_with("P2P ордер успешно отменен.")
        self.state_mock.finish.assert_called_once()

    async def test_cancel_p2p_order_confirm_failure(self):
        """Тест cancel_p2p_order_confirm (ошибка)."""
        self.message_mock.text = "1"
        self.p2p_service_mock.cancel_order.return_value = {'success': False, 'error': 'Some error'}
        await cancel_p2p_order_confirm(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called_with("Ошибка при отмене P2P ордера: Some error")
        self.state_mock.finish.assert_called_once()

    async def test_cancel_p2p_order_confirm_invalid(self):
        """Тест cancel_p2p_order_confirm (неверный ввод)."""
        self.message_mock.text = "INVALID"
        await cancel_p2p_order_confirm(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called_with("Неверный ID ордера. Пожалуйста, введите число.")
        self.state_mock.finish.assert_not_called()

    @patch('bot.handlers.p2p_handler.p2p_order_keyboard', return_value=MagicMock())  #  p2p_order_keyboard
    @patch('bot.handlers.p2p_handler.is_premium', return_value=False)  #  is_premium
    async def test_list_p2p_orders_no_orders(self, mock_is_premium, mock_keyboard):
        """Тест list_p2p_orders (нет ордеров)."""
        self.p2p_service_mock.get_open_orders.return_value = []
        await list_p2p_orders(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called_with("Нет открытых P2P ордеров.", reply_markup=ANY)

    @patch('bot.handlers.p2p_handler.p2p_order_keyboard', return_value=MagicMock())  #  p2p_order_keyboard
    @patch('bot.handlers.p2p_handler.is_premium', return_value=False)  #  is_premium
    async def test_list_p2p_orders_with_orders(self, mock_is_premium, mock_keyboard):
        """Тест list_p2p_orders (есть ордера)."""
        order1 = P2POrder(id=1, user_id=456, side="BUY", amount=1.0, base_currency="TON", price=2.5, quote_currency="USDT", payment_method="TINKOFF")
        order2 = P2POrder(id=2, user_id=789, side="SELL", amount=5.0, base_currency="SOL", price=50.0, quote_currency="USDT", payment_method="SBERBANK")
        order1.user = User(telegram_id=456, username="user1", hide_p2p_orders=False)  #  hide_p2p_orders
        order2.user = User(telegram_id=789, username="user2", hide_p2p_orders=False)
        self.p2p_service_mock.get_open_orders.return_value = [order1, order2]
        self.message_mock.bot.get_chat = AsyncMock(side_effect=[
            MagicMock(username="user1"), MagicMock(username="user2")  #  get_chat
        ])
        await list_p2p_orders(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called()  #  вызван
        #  2 раза (для каждого ордера) + 1  ""
        self.assertEqual(self.message_mock.answer.call_count, 3)

    @patch('bot.handlers.p2p_handler.p2p_order_keyboard', return_value=MagicMock())  #  p2p_order_keyboard
    async def test_my_p2p_orders_no_orders(self, mock_keyboard):
        """Тест my_p2p_orders (нет ордеров)."""
        self.p2p_service_mock.get_user_p2p_orders.return_value = []
        self.p2p_service_mock.get_user_taken_p2p_orders.return_value = []
        await my_p2p_orders(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called_with("У вас нет P2P ордеров.", reply_markup=ANY)

    @patch('bot.handlers.p2p_handler.p2p_order_keyboard', return_value=MagicMock())  #  p2p_order_keyboard
    async def test_my_p2p_orders_with_orders(self, mock_keyboard):
        """Тест my_p2p_orders (есть ордера)."""
        order1 = P2POrder(id=1, user_id=123, side="BUY", amount=1.0, base_currency="TON", price=2.5, quote_currency="USDT", payment_method="TINKOFF", status="OPEN")
        order2 = P2POrder(id=2, user_id=456, taker_id=123, side="SELL", amount=5.0, base_currency="SOL", price=50.0, quote_currency="USDT", payment_method="SBERBANK", status="IN_PROGRESS")
        self.p2p_service_mock.get_user_p2p_orders.return_value = [order1]
        self.p2p_service_mock.get_user_taken_p2p_orders.return_value = [order2]
        await my_p2p_orders(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called()  #  вызван
        #  2 раза (для каждого типа ордеров) + 1  ""
        self.assertEqual(self.message_mock.answer.call_count, 3)

    async def test_back_to_p2p_menu_handler(self):
        """Тест back_to_p2p_menu_handler."""
        await back_to_p2p_menu_handler(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called_with("Выберите действие:", reply_markup=ANY)
        self.state_mock.finish.assert_called_once()

    async def test_take_p2p_order_handler_success(self):
        """Тест take_p2p_order_handler (успех)."""
        self.callback_query_mock.data = "p2p_take_1"
        self.p2p_service_mock.take_order.return_value = {'success': True}
        await take_p2p_order_handler(self.callback_query_mock, self.state_mock, self.p2p_service_mock)
        self.p2p_service_mock.take_order.assert_awaited_once_with(1, 123)
        self.callback_query_mock.message.answer.assert_called_with("Вы приняли ордер!")
        self.callback_query_mock.answer.assert_called_once()

    async def test_take_p2p_order_handler_failure(self):
        """Тест take_p2p_order_handler (ошибка)."""
        self.callback_query_mock.data = "p2p_take_1"
        self.p2p_service_mock.take_order.return_value = {'success': False, 'error': 'Some error'}
        await take_p2p_order_handler(self.callback_query_mock, self.state_mock, self.p2p_service_mock)
        self.callback_query_mock.message.answer.assert_called_with("Ошибка: Some error")
        self.callback_query_mock.answer.assert_called_once()

    async def test_cancel_p2p_order_handler_success(self):
        """Тест cancel_p2p_order_handler (успех)."""
        self.callback_query_mock.data = "p2p_cancel_1"
        self.p2p_service_mock.cancel_order.return_value = {'success': True}
        await cancel_p2p_order_handler(self.callback_query_mock, self.state_mock, self.p2p_service_mock)
        self.p2p_service_mock.cancel_order.assert_awaited_once_with(1, 123)
        self.callback_query_mock.message.answer.assert_called_with("Ордер отменен.")
        self.callback_query_mock.answer.assert_called_once()

    async def test_cancel_p2p_order_handler_failure(self):
        """Тест cancel_p2p_order_handler (ошибка)."""
        self.callback_query_mock.data = "p2p_cancel_1"
        self.p2p_service_mock.cancel_order.return_value = {'success': False, 'error': 'Some error'}
        await cancel_p2p_order_handler(self.callback_query_mock, self.state_mock, self.p2p_service_mock)
        self.callback_query_mock.message.answer.assert_called_with("Ошибка: Some error")
        self.callback_query_mock.answer.assert_called_once()

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