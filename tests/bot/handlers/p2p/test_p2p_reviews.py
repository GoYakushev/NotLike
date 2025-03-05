import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from aiogram.dispatcher import FSMContext
from aiogram.types import Message, CallbackQuery
from bot.handlers.p2p_handler import (
    confirm_payment_handler, leave_review_handler, process_rating,
    process_review_comment, show_user_rating_handler, P2POrderStates
)
from services.p2p.p2p_service import P2PService
from core.database.models import P2POrder, User, P2POrderStatus
from services.rating.rating_service import RatingService
from unittest.mock import ANY

class TestP2PReviews(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.p2p_service_mock = AsyncMock(spec=P2PService)
        self.rating_service_mock = AsyncMock(spec=RatingService)
        self.state_mock = AsyncMock(spec=FSMContext)
        self.message_mock = MagicMock(spec=Message)
        self.callback_query_mock = MagicMock(spec=CallbackQuery)
        self.message_mock.from_user.id = 123
        self.message_mock.from_user.username = "testuser"
        self.callback_query_mock.from_user.id = 123
        self.callback_query_mock.message = self.message_mock
        self.callback_query_mock.from_user.username = "testcallbackuser"

    async def test_confirm_payment_handler_success(self):
        """Тест confirm_payment_handler (успех)."""
        self.callback_query_mock.data = "p2p_confirm_payment_1"
        order = P2POrder(id=1, user_id=123, taker_id=456, status=P2POrderStatus.IN_PROGRESS)
        order.user = User(telegram_id=123)  #  user
        order.taker = User(telegram_id=456)  #  taker
        self.p2p_service_mock.get_order_by_id.return_value = order
        self.p2p_service_mock.complete_order.return_value = {'success': True}
        await confirm_payment_handler(self.callback_query_mock, self.state_mock, self.p2p_service_mock)
        self.p2p_service_mock.complete_order.assert_awaited_once_with(1, 123)
        self.callback_query_mock.message.answer.assert_called_with("Оплата подтверждена. Ордер завершен.")
        self.callback_query_mock.answer.assert_called_once()
        #  2  (taker  user)
        self.assertEqual(self.callback_query_mock.message.bot.send_message.call_count, 2)

    async def test_confirm_payment_handler_order_not_found(self):
        """Тест confirm_payment_handler: ордер не найден."""
        self.callback_query_mock.data = "p2p_confirm_payment_1"
        self.p2p_service_mock.get_order_by_id.return_value = None
        await confirm_payment_handler(self.callback_query_mock, self.state_mock, self.p2p_service_mock)
        self.callback_query_mock.message.answer.assert_called_with("Ордер не найден.")
        self.callback_query_mock.answer.assert_called_once()
        self.p2p_service_mock.complete_order.assert_not_awaited()

    async def test_confirm_payment_handler_wrong_user(self):
        """Тест confirm_payment_handler: не тот пользователь."""
        self.callback_query_mock.data = "p2p_confirm_payment_1"
        order = P2POrder(id=1, user_id=456, taker_id=789, status=P2POrderStatus.IN_PROGRESS)
        self.p2p_service_mock.get_order_by_id.return_value = order
        await confirm_payment_handler(self.callback_query_mock, self.state_mock, self.p2p_service_mock)
        self.callback_query_mock.message.answer.assert_called_with("Вы не можете подтвердить оплату по этому ордеру.")
        self.callback_query_mock.answer.assert_called_once()
        self.p2p_service_mock.complete_order.assert_not_awaited()

    async def test_confirm_payment_handler_wrong_status(self):
        """Тест confirm_payment_handler: неверный статус."""
        self.callback_query_mock.data = "p2p_confirm_payment_1"
        order = P2POrder(id=1, user_id=123, taker_id=456, status=P2POrderStatus.OPEN)
        self.p2p_service_mock.get_order_by_id.return_value = order
        await confirm_payment_handler(self.callback_query_mock, self.state_mock, self.p2p_service_mock)
        self.callback_query_mock.message.answer.assert_called_with("Неверный статус ордера.")
        self.callback_query_mock.answer.assert_called_once()
        self.p2p_service_mock.complete_order.assert_not_awaited()

    async def test_confirm_payment_handler_failure(self):
        """Тест confirm_payment_handler: ошибка при завершении."""
        self.callback_query_mock.data = "p2p_confirm_payment_1"
        order = P2POrder(id=1, user_id=123, taker_id=456, status=P2POrderStatus.IN_PROGRESS)
        self.p2p_service_mock.get_order_by_id.return_value = order
        self.p2p_service_mock.complete_order.return_value = {'success': False, 'error': 'Some error'}
        await confirm_payment_handler(self.callback_query_mock, self.state_mock, self.p2p_service_mock)
        self.callback_query_mock.message.answer.assert_called_with("Ошибка: Some error")
        self.callback_query_mock.answer.assert_called_once()
        self.callback_query_mock.message.bot.send_message.assert_not_awaited()

    async def test_leave_review_handler(self):
        """Тест leave_review_handler."""
        self.callback_query_mock.data = "p2p_leave_review_1"
        await leave_review_handler(self.callback_query_mock, self.state_mock, self.rating_service_mock)
        self.state_mock.update_data.assert_called_once_with(order_id=1)
        self.state_mock.set_state.assert_called_once_with(P2POrderStates.waiting_for_rating.state)
        self.callback_query_mock.message.answer.assert_called_with("Пожалуйста, оцените сделку по шкале от 1 до 5:")
        self.callback_query_mock.answer.assert_called_once()

    async def test_process_rating_valid(self):
        """Тест process_rating (валидный рейтинг)."""
        self.message_mock.text = "4"
        await process_rating(self.message_mock, self.state_mock, self.rating_service_mock)
        self.state_mock.update_data.assert_called_once_with(rating=4)
        self.state_mock.set_state.assert_called_once_with(P2POrderStates.waiting_for_review_comment.state)
        self.message_mock.answer.assert_called_with("Хотите оставить комментарий к отзыву? (необязательно)")

    async def test_process_rating_invalid(self):
        """Тест process_rating (невалидный рейтинг)."""
        self.message_mock.text = "6"
        await process_rating(self.message_mock, self.state_mock, self.rating_service_mock)
        self.message_mock.answer.assert_called_with("Пожалуйста, введите число от 1 до 5.")
        self.state_mock.update_data.assert_not_called()
        self.state_mock.set_state.assert_not_called()

    async def test_process_review_comment_success(self):
        """Тест process_review_comment (успех)."""
        self.message_mock.text = "Great transaction!"
        self.state_mock.get_data.return_value = {'order_id': 1, 'rating': 5}
        order = P2POrder(id=1, user_id=123, taker_id=456)  # user_id  taker_id  
        self.p2p_service_mock.get_order_by_id.return_value = order
        self.rating_service_mock.add_review.return_value = {'success': True}
        await process_review_comment(self.message_mock, self.state_mock, self.rating_service_mock, self.p2p_service_mock)
        self.rating_service_mock.add_review.assert_awaited_once_with(123, 456, 1, 5, "Great transaction!")  # reviewer, reviewee, order_id
        self.message_mock.answer.assert_called_with("Спасибо за ваш отзыв!")
        self.state_mock.finish.assert_called_once()

    async def test_process_review_comment_order_not_found(self):
        """Тест process_review_comment: ордер не найден."""
        self.message_mock.text = "Some comment"
        self.state_mock.get_data.return_value = {'order_id': 1, 'rating': 5}
        self.p2p_service_mock.get_order_by_id.return_value = None
        await process_review_comment(self.message_mock, self.state_mock, self.rating_service_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called_with("Ордер не найден.")
        self.state_mock.finish.assert_called_once()
        self.rating_service_mock.add_review.assert_not_awaited()

    async def test_process_review_comment_wrong_user(self):
        """Тест process_review_comment: не тот пользователь."""
        self.message_mock.text = "Some comment"
        self.state_mock.get_data.return_value = {'order_id': 1, 'rating': 5}
        order = P2POrder(id=1, user_id=789, taker_id=101)  #  user_id  taker_id
        self.p2p_service_mock.get_order_by_id.return_value = order
        await process_review_comment(self.message_mock, self.state_mock, self.rating_service_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called_with("Вы не можете оставить отзыв по этому ордеру.")
        self.state_mock.finish.assert_called_once()
        self.rating_service_mock.add_review.assert_not_awaited()

    async def test_process_review_comment_failure(self):
        """Тест process_review_comment: ошибка при добавлении."""
        self.message_mock.text = "Some comment"
        self.state_mock.get_data.return_value = {'order_id': 1, 'rating': 5}
        order = P2POrder(id=1, user_id=123, taker_id=456)
        self.p2p_service_mock.get_order_by_id.return_value = order
        self.rating_service_mock.add_review.return_value = {'success': False, 'error': 'Some error'}
        await process_review_comment(self.message_mock, self.state_mock, self.rating_service_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called_with("Ошибка при добавлении отзыва: Some error")
        self.state_mock.finish.assert_called_once()

    async def test_show_user_rating_handler_no_user_id(self):
        """Тест show_user_rating_handler (без user_id)."""
        self.message_mock.get_args.return_value = None  #  аргументов
        self.rating_service_mock.get_user_rating.return_value = 4.5
        await show_user_rating_handler(self.message_mock, self.state_mock, self.rating_service_mock)
        self.rating_service_mock.get_user_rating.assert_awaited_once_with(123)  #  ID текущего пользователя
        self.message_mock.answer.assert_called_with("Ваш рейтинг: 4.5")

    async def test_show_user_rating_handler_with_user_id(self):
        """Тест show_user_rating_handler (с user_id)."""
        self.message_mock.get_args.return_value = "456"  #  аргумент
        self.rating_service_mock.get_user_rating.return_value = 4.0
        await show_user_rating_handler(self.message_mock, self.state_mock, self.rating_service_mock)
        self.rating_service_mock.get_user_rating.assert_awaited_once_with(456)
        self.message_mock.answer.assert_called_with("Рейтинг пользователя 456: 4.0")

    async def test_show_user_rating_handler_no_rating(self):
        """Тест show_user_rating_handler: нет рейтинга."""
        self.message_mock.get_args.return_value = None
        self.rating_service_mock.get_user_rating.return_value = None
        await show_user_rating_handler(self.message_mock, self.state_mock, self.rating_service_mock)
        self.message_mock.answer.assert_called_with("У вас пока нет рейтинга.") 