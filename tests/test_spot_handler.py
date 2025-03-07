import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from aiogram.dispatcher import FSMContext
from aiogram.types import Message, CallbackQuery, User as AioUser
from bot.handlers.spot_handler import (
    show_spot_menu, start_create_order, process_base_currency,
    process_quote_currency, process_order_type, process_side,
    process_quantity, process_price, show_order_confirmation,
    process_order_confirmation, start_cancel_order, process_cancel_order,
    SpotStates, show_my_spot_orders, show_spot_order_history, back_to_spot_menu_handler,
    spot_start, choose_token, choose_side, enter_quantity,
    enter_price, confirm_order, cancel_spot_order,
    SpotOrderStates
)
from services.spot.spot_service import SpotService  #  SpotService
from bot.keyboards.spot_keyboards import spot_menu_keyboard, order_type_keyboard, buy_sell_keyboard, back_to_spot_menu_keyboard
from unittest.mock import ANY #  ANY
from core.database.models import SpotOrder


class TestSpotHandler(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.message_mock = AsyncMock()
        self.callback_query_mock = AsyncMock()
        self.state_mock = AsyncMock(spec=FSMContext)
        self.spot_service_mock = AsyncMock(spec=SpotService)

        # Патчим spot_service, чтобы он не создавался заново
        self.spot_service_patch = patch('bot.handlers.spot_handler.spot_service', new=self.spot_service_mock)
        self.spot_service_patch.start()

    async def asyncTearDown(self):
        self.spot_service_patch.stop()

    async def test_show_spot_menu(self):
        """Тест отображения меню spot."""
        await show_spot_menu(self.message_mock)
        self.message_mock.answer.assert_called_once_with("Выберите действие:", reply_markup=spot_menu_keyboard)

    async def test_start_create_order(self):
        """Тест начала создания ордера."""
        self.callback_query_mock.data = "create_spot_order"
        self.callback_query_mock.message = self.message_mock  # Добавляем message
        await start_create_order(self.callback_query_mock, self.state_mock)
        await self.state_mock.set_state.assert_called_once_with(SpotStates.choosing_base_currency)
        self.message_mock.answer.assert_called_once_with("Введите базовую валюту (например, SOL):")

    async def test_process_base_currency(self):
        """Тест обработки базовой валюты."""
        self.message_mock.text = "sol"
        await process_base_currency(self.message_mock, self.state_mock)
        await self.state_mock.update_data.assert_called_once_with(base_currency="SOL")
        await self.state_mock.set_state.assert_called_once_with(SpotStates.choosing_quote_currency)
        self.message_mock.answer.assert_called_once_with("Введите котируемую валюту (например, USDT):")

    async def test_process_quote_currency(self):
        """Тест обработки котируемой валюты."""
        self.message_mock.text = "usdt"
        await process_quote_currency(self.message_mock, self.state_mock)
        await self.state_mock.update_data.assert_called_once_with(quote_currency="USDT")
        await self.state_mock.set_state.assert_called_once_with(SpotStates.choosing_order_type)
        self.message_mock.answer.assert_called_once_with("Выберите тип ордера:", reply_markup=order_type_keyboard)

    async def test_process_order_type_limit(self):
        """Тест выбора типа ордера (LIMIT)."""
        self.callback_query_mock.data = "order_type_limit"
        self.callback_query_mock.message = self.message_mock
        await process_order_type(self.callback_query_mock, self.state_mock)
        await self.state_mock.update_data.assert_called_once_with(order_type="LIMIT")
        await self.state_mock.set_state.assert_called_once_with(SpotStates.choosing_side)
        self.message_mock.answer.assert_called_once_with("Выберите сторону (BUY/SELL):", reply_markup=buy_sell_keyboard)

    async def test_process_order_type_market(self):
        """Тест выбора типа ордера (MARKET)."""
        self.callback_query_mock.data = "order_type_market"
        self.callback_query_mock.message = self.message_mock
        await process_order_type(self.callback_query_mock, self.state_mock)
        await self.state_mock.update_data.assert_called_once_with(order_type="MARKET")
        await self.state_mock.set_state.assert_called_once_with(SpotStates.choosing_side)
        self.message_mock.answer.assert_called_once_with("Выберите сторону (BUY/SELL):", reply_markup=buy_sell_keyboard)

    async def test_process_side_buy(self):
        """Тест выбора стороны (BUY)."""
        self.callback_query_mock.data = "side_buy"
        self.callback_query_mock.message = self.message_mock
        await process_side(self.callback_query_mock, self.state_mock)
        await self.state_mock.update_data.assert_called_once_with(side="BUY")
        await self.state_mock.set_state.assert_called_once_with(SpotStates.entering_quantity)
        self.message_mock.answer.assert_called_once_with("Введите количество:")

    async def test_process_side_sell(self):
        """Тест выбора стороны (SELL)."""
        self.callback_query_mock.data = "side_sell"
        self.callback_query_mock.message = self.message_mock
        await process_side(self.callback_query_mock, self.state_mock)
        await self.state_mock.update_data.assert_called_once_with(side="SELL")
        await self.state_mock.set_state.assert_called_once_with(SpotStates.entering_quantity)
        self.message_mock.answer.assert_called_once_with("Введите количество:")

    async def test_process_quantity_valid(self):
        """Тест ввода корректного количества."""
        self.message_mock.text = "1.5"
        self.state_mock.get_data.return_value = {'order_type': 'LIMIT'}  #  LIMIT
        await process_quantity(self.message_mock, self.state_mock)
        await self.state_mock.update_data.assert_called_once_with(quantity=1.5)
        await self.state_mock.set_state.assert_called_once_with(SpotStates.entering_price)
        self.message_mock.answer.assert_called_once_with("Введите цену:")

    async def test_process_quantity_valid_market(self):
        """Тест ввода корректного количества (MARKET)."""
        self.message_mock.text = "2.0"
        self.state_mock.get_data.return_value = {'order_type': 'MARKET'}  #  MARKET
        await process_quantity(self.message_mock, self.state_mock)
        await self.state_mock.update_data.assert_called_once_with(quantity=2.0)
        await self.state_mock.set_state.assert_called_once_with(SpotStates.confirming_order)
        # Проверяем вызов show_order_confirmation (косвенно)
        self.message_mock.answer.assert_called()

    async def test_process_quantity_invalid(self):
        """Тест ввода некорректного количества."""
        self.message_mock.text = "abc"
        await process_quantity(self.message_mock, self.state_mock)
        self.message_mock.answer.assert_called_once_with("Неверный формат. Пожалуйста, введите положительное число.")
        self.state_mock.update_data.assert_not_called()

    async def test_process_quantity_negative(self):
        """Тест ввода отрицательного количества."""
        self.message_mock.text = "-1"
        await process_quantity(self.message_mock, self.state_mock)
        self.message_mock.answer.assert_called_once_with("Неверный формат. Пожалуйста, введите положительное число.")
        self.state_mock.update_data.assert_not_called()

    async def test_process_price_valid(self):
        """Тест ввода корректной цены."""
        self.message_mock.text = "5.2"
        await process_price(self.message_mock, self.state_mock)
        await self.state_mock.update_data.assert_called_once_with(price=5.2)
        await self.state_mock.set_state.assert_called_once_with(SpotStates.confirming_order)
        # Проверяем вызов show_order_confirmation (косвенно)
        self.message_mock.answer.assert_called()

    async def test_process_price_invalid(self):
        """Тест ввода некорректной цены."""
        self.message_mock.text = "xyz"
        await process_price(self.message_mock, self.state_mock)
        self.message_mock.answer.assert_called_once_with("Неверный формат. Пожалуйста, введите положительное число.")
        self.state_mock.update_data.assert_not_called()

    async def test_process_price_negative(self):
        """Тест ввода отрицательной цены."""
        self.message_mock.text = "-5"
        await process_price(self.message_mock, self.state_mock)
        self.message_mock.answer.assert_called_once_with("Неверный формат. Пожалуйста, введите положительное число.")
        self.state_mock.update_data.assert_not_called()

    async def test_show_order_confirmation(self):
        """Тест отображения подтверждения ордера (LIMIT)."""
        self.state_mock.get_data.return_value = {
            'base_currency': 'SOL', 'quote_currency': 'USDT', 'order_type': 'LIMIT',
            'side': 'BUY', 'quantity': 1.23, 'price': 4.56
        }
        await show_order_confirmation(self.message_mock, self.state_mock)
        self.message_mock.answer.assert_called_once()
        args, kwargs = self.message_mock.answer.call_args
        self.assertIn("Подтвердите создание ордера", args[0])
        self.assertIn("Базовая валюта: SOL", args[0])
        self.assertIn("Котируемая валюта: USDT", args[0])
        self.assertIn("Тип ордера: LIMIT", args[0])
        self.assertIn("Сторона: BUY", args[0])
        self.assertIn("Количество: 1.23", args[0])
        self.assertIn("Цена: 4.56", args[0])
        self.assertIn("reply_markup", kwargs)

    async def test_show_order_confirmation_market(self):
        """Тест отображения подтверждения ордера (MARKET)."""
        self.state_mock.get_data.return_value = {
            'base_currency': 'TON', 'quote_currency': 'USDT', 'order_type': 'MARKET',
            'side': 'SELL', 'quantity': 2.5
        }
        await show_order_confirmation(self.message_mock, self.state_mock)
        self.message_mock.answer.assert_called_once()
        args, kwargs = self.message_mock.answer.call_args
        self.assertIn("Подтвердите создание ордера", args[0])
        self.assertIn("Базовая валюта: TON", args[0])
        self.assertIn("Тип ордера: MARKET", args[0])
        self.assertIn("Сторона: SELL", args[0])
        self.assertNotIn("Цена:", args[0])  # Нет цены для MARKET
        self.assertIn("reply_markup", kwargs)

    async def test_process_order_confirmation_confirm_limit(self):
        """Тест подтверждения LIMIT ордера."""
        self.callback_query_mock.data = "confirm_order"
        self.callback_query_mock.from_user.id = 123
        self.callback_query_mock.message = self.message_mock
        self.state_mock.get_data.return_value = {
            'base_currency': 'SOL', 'quote_currency': 'USDT', 'order_type': 'LIMIT',
            'side': 'BUY', 'quantity': 1.0, 'price': 5.0
        }
        self.spot_service_mock.create_limit_order.return_value = {'success': True, 'order_id': 42}
        await process_order_confirmation(self.callback_query_mock, self.state_mock)
        self.spot_service_mock.create_limit_order.assert_awaited_once_with(123, 'SOL', 'USDT', 'BUY', 1.0, 5.0)
        self.message_mock.answer.assert_called_once_with("✅ Ордер создан! ID: 42")
        await self.state_mock.finish.assert_called_once()

    async def test_process_order_confirmation_confirm_market(self):
        """Тест подтверждения MARKET ордера."""
        self.callback_query_mock.data = "confirm_order"
        self.callback_query_mock.from_user.id = 456
        self.callback_query_mock.message = self.message_mock
        self.state_mock.get_data.return_value = {
            'base_currency': 'TON', 'quote_currency': 'USDT', 'order_type': 'MARKET',
            'side': 'SELL', 'quantity': 2.0
        }
        self.spot_service_mock.create_market_order.return_value = {'success': True, 'order_id': 77}
        await process_order_confirmation(self.callback_query_mock, self.state_mock)
        self.spot_service_mock.create_market_order.assert_awaited_once_with(456, 'TON', 'USDT', 'SELL', 2.0)
        self.message_mock.answer.assert_called_once_with("✅ Ордер создан! ID: 77")
        await self.state_mock.finish.assert_called_once()

    async def test_process_order_confirmation_cancel(self):
        """Тест отмены создания ордера."""
        self.callback_query_mock.data = "cancel_order"
        self.callback_query_mock.message = self.message_mock
        await process_order_confirmation(self.callback_query_mock, self.state_mock)
        self.message_mock.answer.assert_called_once_with("❌ Создание ордера отменено.")
        await self.state_mock.finish.assert_called_once()

    async def test_process_order_confirmation_create_order_fail(self):
        """Тест: ошибка при создании ордера."""
        self.callback_query_mock.data = "confirm_order"
        self.callback_query_mock.from_user.id = 123
        self.callback_query_mock.message = self.message_mock
        self.state_mock.get_data.return_value = {
            'base_currency': 'SOL', 'quote_currency': 'USDT', 'order_type': 'LIMIT',
            'side': 'BUY', 'quantity': 1.0, 'price': 5.0
        }
        # Мокаем create_limit_order/create_market_order, чтобы он возвращал ошибку
        self.spot_service_mock.create_limit_order.return_value = {'success': False, 'error': 'Some error'}
        self.spot_service_mock.create_market_order.return_value = {'success': False, 'error': 'Some error'}
        await process_order_confirmation(self.callback_query_mock, self.state_mock)
        self.message_mock.answer.assert_called_once_with("❌ Ошибка при создании ордера: Some error")
        await self.state_mock.finish.assert_called_once()

    async def test_start_cancel_order(self):
        """Тест начала отмены ордера."""
        self.callback_query_mock.data = "cancel_spot_order"
        self.callback_query_mock.message = self.message_mock
        await start_cancel_order(self.callback_query_mock, self.state_mock)
        await self.state_mock.set_state.assert_called_once_with(SpotStates.cancelling_order)
        self.message_mock.answer.assert_called_once_with("Введите ID ордера, который хотите отменить:")

    async def test_process_cancel_order_success(self):
        """Тест успешной отмены ордера."""
        self.message_mock.text = "123"
        self.message_mock.from_user.id = 456
        self.spot_service_mock.cancel_order.return_value = {'success': True}
        await process_cancel_order(self.message_mock, self.state_mock)
        self.spot_service_mock.cancel_order.assert_awaited_once_with(456, 123)
        self.message_mock.answer.assert_called_once_with("✅ Ордер отменен.")
        await self.state_mock.finish.assert_called_once()

    async def test_process_cancel_order_fail(self):
        """Тест ошибки при отмене ордера."""
        self.message_mock.text = "456"
        self.message_mock.from_user.id = 789
        self.spot_service_mock.cancel_order.return_value = {'success': False, 'error': 'Some error'}
        await process_cancel_order(self.message_mock, self.state_mock)
        self.spot_service_mock.cancel_order.assert_awaited_once_with(789, 456)
        self.message_mock.answer.assert_called_once_with("❌ Ошибка при отмене ордера: Some error")
        await self.state_mock.finish.assert_called_once()

    async def test_process_cancel_order_invalid_input(self):
        """Тест неверного ввода ID ордера."""
        self.message_mock.text = "abc"
        await process_cancel_order(self.message_mock, self.state_mock)
        self.message_mock.answer.assert_called_once_with("Неверный формат ID. Пожалуйста, введите целое число.")
        self.spot_service_mock.cancel_order.assert_not_awaited()
        await self.state_mock.finish.assert_not_called()

    async def test_show_my_spot_orders_no_orders(self):
        """Тест: нет открытых ордеров."""
        self.callback_query_mock.from_user.id = 123
        self.callback_query_mock.message = self.message_mock
        self.spot_service_mock.get_open_orders.return_value = []  # Нет ордеров
        await show_my_spot_orders(self.callback_query_mock)
        self.spot_service_mock.get_open_orders.assert_awaited_once_with(123)
        self.message_mock.answer.assert_called_once_with("У вас нет открытых ордеров.", reply_markup=back_to_spot_menu_keyboard)

    async def test_show_my_spot_orders_with_orders(self):
        """Тест: есть открытые ордера."""
        self.callback_query_mock.from_user.id = 456
        self.callback_query_mock.message = self.message_mock
        order1 = SpotOrder(id=1, side="BUY", quantity=1.0, base_currency="SOL", price=5.0, quote_currency="USDT", status="OPEN")
        order2 = SpotOrder(id=2, side="SELL", quantity=2.5, base_currency="TON", price=2.0, quote_currency="USDT", status="OPEN")
        self.spot_service_mock.get_open_orders.return_value = [order1, order2]
        await show_my_spot_orders(self.callback_query_mock)
        self.spot_service_mock.get_open_orders.assert_awaited_once_with(456)
        self.message_mock.answer.assert_called_once()
        args, kwargs = self.message_mock.answer.call_args
        self.assertIn("Ваши открытые ордера", args[0])
        self.assertIn("ID: 1 - BUY 1.0 SOL за 5.0 USDT", args[0])
        self.assertIn("Статус: OPEN", args[0])
        self.assertIn("ID: 2 - SELL 2.5 TON за 2.0 USDT", args[0])
        self.assertIn("reply_markup", kwargs)  #  reply_markup

    async def test_show_spot_order_history_no_orders(self):
        """Тест: нет истории ордеров."""
        self.callback_query_mock.from_user.id = 789
        self.callback_query_mock.message = self.message_mock
        self.spot_service_mock.get_order_history.return_value = []
        await show_spot_order_history(self.callback_query_mock)
        self.spot_service_mock.get_order_history.assert_awaited_once_with(789)
        self.message_mock.answer.assert_called_once_with("У вас нет истории ордеров.", reply_markup=back_to_spot_menu_keyboard)

    async def test_show_spot_order_history_with_orders(self):
        """Тест: есть история ордеров."""
        self.callback_query_mock.from_user.id = 101
        self.callback_query_mock.message = self.message_mock
        order1 = SpotOrder(id=3, side="BUY", quantity=0.5, base_currency="SOL", price=5.2, quote_currency="USDT", status="FILLED")
        order2 = SpotOrder(id=4, side="SELL", quantity=1.0, base_currency="TON", price=2.1, quote_currency="USDT", status="CANCELLED")
        self.spot_service_mock.get_order_history.return_value = [order1, order2]
        await show_spot_order_history(self.callback_query_mock)
        self.spot_service_mock.get_order_history.assert_awaited_once_with(101)
        self.message_mock.answer.assert_called_once()
        args, kwargs = self.message_mock.answer.call_args
        self.assertIn("Ваша история ордеров", args[0])
        self.assertIn("ID: 3 - BUY 0.5 SOL за 5.2 USDT", args[0])
        self.assertIn("Статус: FILLED", args[0])
        self.assertIn("ID: 4 - SELL 1.0 TON за 2.1 USDT", args[0])
        self.assertIn("Статус: CANCELLED", args[0])
        self.assertIn("reply_markup", kwargs)

    async def test_back_to_spot_menu(self):
        """Тест возврата в меню spot."""
        self.callback_query_mock.data = "back_to_spot_menu"
        self.callback_query_mock.message = self.message_mock
        await back_to_spot_menu_handler(self.callback_query_mock)
        # Проверяем, что вызвался show_spot_menu (косвенно, через answer)
        self.message_mock.answer.assert_called_once_with("Выберите действие:", reply_markup=spot_menu_keyboard)

    async def test_spot_start(self):
        """Тест /spot."""
        await spot_start(self.message_mock, self.state_mock)
        self.message_mock.answer.assert_called_once_with("Выберите действие:", reply_markup=ANY)  #  ANY
        self.state_mock.set_state.assert_called_once_with(SpotOrderStates.waiting_for_token.state)

    async def test_choose_token_valid(self):
        """Тест: выбор токена (валидный)."""
        self.message_mock.text = "SOL/USDT"
        await choose_token(self.message_mock, self.state_mock, self.spot_service_mock)
        self.state_mock.update_data.assert_called_once_with(chosen_token="SOL/USDT")
        self.message_mock.answer.assert_called_with("Выберите сторону (BUY/SELL):", reply_markup=ANY)
        self.state_mock.set_state.assert_called_once_with(SpotOrderStates.waiting_for_side.state)

    async def test_choose_token_invalid(self):
        """Тест: выбор токена (невалидный)."""
        self.message_mock.text = "INVALID"
        await choose_token(self.message_mock, self.state_mock, self.spot_service_mock)
        self.message_mock.answer.assert_called_with("Неверный токен. Выберите из списка:", reply_markup=ANY)
        self.state_mock.update_data.assert_not_called()
        self.state_mock.set_state.assert_not_called()

    async def test_choose_token_back(self):
        """Тест: выбор токена (назад)."""
        self.message_mock.text = "Назад"
        await choose_token(self.message_mock, self.state_mock, self.spot_service_mock)
        self.message_mock.answer.assert_called_with("Выберите действие:", reply_markup=ANY)
        self.state_mock.set_state.assert_called_with(SpotOrderStates.waiting_for_token.state)

    async def test_choose_side_valid(self):
        """Тест: выбор стороны (валидный)."""
        self.message_mock.text = "BUY"
        await choose_side(self.message_mock, self.state_mock, self.spot_service_mock)
        self.state_mock.update_data.assert_called_once_with(chosen_side="BUY")
        self.message_mock.answer.assert_called_with("Введите количество:")
        self.state_mock.set_state.assert_called_once_with(SpotOrderStates.waiting_for_quantity.state)

    async def test_choose_side_invalid(self):
        """Тест: выбор стороны (невалидный)."""
        self.message_mock.text = "INVALID"
        await choose_side(self.message_mock, self.state_mock, self.spot_service_mock)
        self.message_mock.answer.assert_called_with("Неверная сторона. Выберите BUY или SELL:", reply_markup=ANY)
        self.state_mock.update_data.assert_not_called()
        self.state_mock.set_state.assert_not_called()

    async def test_choose_side_back(self):
        """Тест: выбор стороны (назад)."""
        self.message_mock.text = "Назад"
        await choose_side(self.message_mock, self.state_mock, self.spot_service_mock)
        self.message_mock.answer.assert_called_with("Выберите токен:", reply_markup=ANY)
        self.state_mock.set_state.assert_called_with(SpotOrderStates.waiting_for_token.state)

    async def test_enter_quantity_valid(self):
        """Тест: ввод количества (валидный)."""
        self.message_mock.text = "1.5"
        await enter_quantity(self.message_mock, self.state_mock, self.spot_service_mock)
        self.state_mock.update_data.assert_called_once_with(quantity=1.5)
        self.message_mock.answer.assert_called_with("Введите цену (или 'рынок' для MARKET ордера):")
        self.state_mock.set_state.assert_called_once_with(SpotOrderStates.waiting_for_price.state)

    async def test_enter_quantity_invalid(self):
        """Тест: ввод количества (невалидный)."""
        self.message_mock.text = "INVALID"
        await enter_quantity(self.message_mock, self.state_mock, self.spot_service_mock)
        self.message_mock.answer.assert_called_with("Неверное количество. Введите положительное число.")
        self.state_mock.update_data.assert_not_called()
        self.state_mock.set_state.assert_not_called()

    async def test_enter_quantity_back(self):
        """Тест: ввод количества (назад)."""
        self.message_mock.text = "Назад"
        await enter_quantity(self.message_mock, self.state_mock, self.spot_service_mock)
        self.message_mock.answer.assert_called_with("Выберите сторону (BUY/SELL):", reply_markup=ANY)
        self.state_mock.set_state.assert_called_with(SpotOrderStates.waiting_for_side.state)

    async def test_enter_price_market(self):
        """Тест: ввод цены (рынок)."""
        self.message_mock.text = "рынок"
        await enter_price(self.message_mock, self.state_mock, self.spot_service_mock)
        self.state_mock.update_data.assert_called_once_with(price=None)
        self.message_mock.answer.assert_called_with(ANY, reply_markup=ANY)  #  MARKET
        self.state_mock.set_state.assert_called_once_with(SpotOrderStates.confirm_order.state)

    async def test_enter_price_limit(self):
        """Тест: ввод цены (лимитный ордер)."""
        self.message_mock.text = "50.5"
        await enter_price(self.message_mock, self.state_mock, self.spot_service_mock)
        self.state_mock.update_data.assert_called_once_with(price=50.5)
        self.message_mock.answer.assert_called_with(ANY, reply_markup=ANY)  #  LIMIT
        self.state_mock.set_state.assert_called_once_with(SpotOrderStates.confirm_order.state)

    async def test_enter_price_invalid(self):
        """Тест: ввод цены (невалидный)."""
        self.message_mock.text = "INVALID"
        await enter_price(self.message_mock, self.state_mock, self.spot_service_mock)
        self.message_mock.answer.assert_called_with("Неверная цена. Введите положительное число или 'рынок'.")
        self.state_mock.update_data.assert_not_called()
        self.state_mock.set_state.assert_not_called()

    async def test_enter_price_back(self):
        """Тест: ввод цены (назад)."""
        self.message_mock.text = "Назад"
        await enter_price(self.message_mock, self.state_mock, self.spot_service_mock)
        self.message_mock.answer.assert_called_with("Введите количество:")
        self.state_mock.set_state.assert_called_with(SpotOrderStates.waiting_for_quantity.state)

    async def test_confirm_order_market_success(self):
        """Тест: подтверждение MARKET ордера (успех)."""
        self.message_mock.text = "Подтвердить"
        self.state_mock.get_data.return_value = {
            'chosen_token': "SOL/USDT",
            'chosen_side': "BUY",
            'quantity': 1.5,
            'price': None  #  MARKET
        }
        self.spot_service_mock.create_market_order.return_value = {'success': True}
        await confirm_order(self.message_mock, self.state_mock, self.spot_service_mock)
        self.spot_service_mock.create_market_order.assert_awaited_once_with(
            user_id=123, base_currency="SOL", quote_currency="USDT", side="BUY", quantity=1.5
        )
        self.message_mock.answer.assert_called_with("Ордер создан!")
        self.state_mock.finish.assert_called_once()

    async def test_confirm_order_limit_success(self):
        """Тест: подтверждение LIMIT ордера (успех)."""
        self.message_mock.text = "Подтвердить"
        self.state_mock.get_data.return_value = {
            'chosen_token': "SOL/USDT",
            'chosen_side': "BUY",
            'quantity': 1.5,
            'price': 50.5  #  LIMIT
        }
        self.spot_service_mock.create_limit_order.return_value = {'success': True}
        await confirm_order(self.message_mock, self.state_mock, self.spot_service_mock)
        self.spot_service_mock.create_limit_order.assert_awaited_once_with(
            user_id=123, base_currency="SOL", quote_currency="USDT", side="BUY", quantity=1.5, price=50.5
        )
        self.message_mock.answer.assert_called_with("Ордер создан!")
        self.state_mock.finish.assert_called_once()

    async def test_confirm_order_error(self):
        """Тест: подтверждение ордера (ошибка)."""
        self.message_mock.text = "Подтвердить"
        self.state_mock.get_data.return_value = {
            'chosen_token': "SOL/USDT",
            'chosen_side': "BUY",
            'quantity': 1.5,
            'price': 50.5
        }
        self.spot_service_mock.create_limit_order.return_value = {'success': False, 'error': 'Some error'}
        await confirm_order(self.message_mock, self.state_mock, self.spot_service_mock)
        self.message_mock.answer.assert_called_with("Ошибка при создании ордера: Some error")
        self.state_mock.finish.assert_called_once()

    async def test_confirm_order_back(self):
        """Тест: подтверждение ордера (назад)."""
        self.message_mock.text = "Назад"
        await confirm_order(self.message_mock, self.state_mock, self.spot_service_mock)
        self.message_mock.answer.assert_called_with("Введите цену (или 'рынок' для MARKET ордера):")
        self.state_mock.set_state.assert_called_with(SpotOrderStates.waiting_for_price.state)

    async def test_confirm_order_invalid(self):
        """Тест: подтверждение ордера (неверный ввод)."""
        self.message_mock.text = "INVALID"
        await confirm_order(self.message_mock, self.state_mock, self.spot_service_mock)
        self.message_mock.answer.assert_called_with("Неверный ввод. Нажмите 'Подтвердить' или 'Назад'.", reply_markup=ANY)
        self.state_mock.set_state.assert_not_called()  #  состояние

    async def test_cancel_spot_order(self):
        """Тест: отмена ордера."""
        await cancel_spot_order(self.message_mock, self.state_mock, self.spot_service_mock)
        self.message_mock.answer.assert_called_once_with("Отмена ордера пока не реализована.")
        self.state_mock.finish.assert_called_once()

    async def test_cancel_spot_order_start_no_orders(self):
        """Тест: начало отмены ордера (нет ордеров)."""
        self.spot_service_mock.get_open_orders.return_value = []  #  ордеров
        await cancel_spot_order_start(self.message_mock, self.state_mock, self.spot_service_mock)
        self.message_mock.answer.assert_called_with("У вас нет открытых ордеров для отмены.", reply_markup=ANY)
        self.state_mock.finish.assert_called_once()

    async def test_cancel_spot_order_start_with_orders(self):
        """Тест: начало отмены ордера (есть ордера)."""
        order1 = SpotOrder(id=1, side="BUY", quantity=1.0, base_currency="SOL", price=50.0, quote_currency="USDT")
        order2 = SpotOrder(id=2, side="SELL", quantity=2.5, base_currency="TON", price=2.0, quote_currency="USDT")
        self.spot_service_mock.get_open_orders.return_value = [order1, order2]
        await cancel_spot_order_start(self.message_mock, self.state_mock, self.spot_service_mock)
        self.message_mock.answer.assert_called_with(ANY)  #  список ордеров
        self.message_mock.answer.assert_called_with("Введите ID ордера, который хотите отменить:")
        self.state_mock.set_state.assert_called_once_with(SpotOrderStates.waiting_for_order_id.state)

    async def test_cancel_spot_order_confirm_success(self):
        """Тест: подтверждение отмены ордера (успех)."""
        self.message_mock.text = "1"
        self.spot_service_mock.cancel_order.return_value = {'success': True}
        await cancel_spot_order_confirm(self.message_mock, self.state_mock, self.spot_service_mock)
        self.spot_service_mock.cancel_order.assert_awaited_once_with(123, 1)  #  ID
        self.message_mock.answer.assert_called_with("Ордер успешно отменен.")
        self.state_mock.finish.assert_called_once()

    async def test_cancel_spot_order_confirm_error(self):
        """Тест: подтверждение отмены ордера (ошибка)."""
        self.message_mock.text = "1"
        self.spot_service_mock.cancel_order.return_value = {'success': False, 'error': 'Some error'}
        await cancel_spot_order_confirm(self.message_mock, self.state_mock, self.spot_service_mock)
        self.message_mock.answer.assert_called_with("Ошибка при отмене ордера: Some error")
        self.state_mock.finish.assert_called_once()

    async def test_cancel_spot_order_confirm_invalid_input(self):
        """Тест: подтверждение отмены ордера (неверный ввод)."""
        self.message_mock.text = "INVALID"
        await cancel_spot_order_confirm(self.message_mock, self.state_mock, self.spot_service_mock)
        self.message_mock.answer.assert_called_with("Неверный ID ордера. Пожалуйста, введите число.")
        self.state_mock.finish.assert_not_called()  #  FSM

    async def test_show_my_spot_orders_no_orders(self):
        self.message_mock.from_user.id = 1
        self.spot_service_mock.get_open_orders.return_value = []
        await show_my_spot_orders(self.message_mock, self.state_mock, self.spot_service_mock)
        self.message_mock.answer.assert_called_with("У вас нет открытых ордеров.", reply_markup=ANY)

    async def test_show_my_spot_orders_with_orders(self):
        order1 = SpotOrder(id=1, side="BUY", quantity=1.0, base_currency="SOL", price=5.0, quote_currency="USDT", status="OPEN")
        order2 = SpotOrder(id=2, side="SELL", quantity=2.5, base_currency="TON", price=2.0, quote_currency="USDT", status="OPEN")
        self.message_mock.from_user.id = 1
        self.spot_service_mock.get_open_orders.return_value = [order1, order2]
        await show_my_spot_orders(self.message_mock, self.state_mock, self.spot_service_mock)
        self.message_mock.answer.assert_called_with(ANY, reply_markup=ANY)

    async def test_show_spot_order_history_no_orders(self):
        self.message_mock.from_user.id = 1
        self.spot_service_mock.get_order_history.return_value = []
        await show_spot_order_history(self.message_mock, self.state_mock, self.spot_service_mock)
        self.message_mock.answer.assert_called_with("У вас нет истории ордеров.", reply_markup=ANY)

    async def test_show_spot_order_history_with_orders(self):
        order1 = SpotOrder(id=3, side="BUY", quantity=0.5, base_currency="SOL", price=5.2, quote_currency="USDT", status="FILLED")
        order2 = SpotOrder(id=4, side="SELL", quantity=1.0, base_currency="TON", price=2.1, quote_currency="USDT", status="CANCELLED")
        self.message_mock.from_user.id = 1
        self.spot_service_mock.get_order_history.return_value = [order1, order2]
        await show_spot_order_history(self.message_mock, self.state_mock, self.spot_service_mock)
        self.message_mock.answer.assert_called_with(ANY, reply_markup=ANY)

    async def test_back_to_spot_menu_handler(self):
        await back_to_spot_menu_handler(self.message_mock, self.state_mock, self.spot_service_mock)
        self.message_mock.answer.assert_called_with("Выберите действие:", reply_markup=ANY)
        self.state_mock.finish.assert_called_once() 