import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from aiogram.dispatcher import FSMContext
from aiogram.types import Message, CallbackQuery
from bot.handlers.p2p_handler import (
    open_dispute_handler, resolve_dispute_handler, process_dispute_resolution,
    handle_dispute_decision, P2POrderStates
)
from services.p2p.p2p_service import P2PService
from core.database.models import P2POrder, User, P2POrderStatus
from unittest.mock import ANY

class TestP2PDisputes(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.p2p_service_mock = AsyncMock(spec=P2PService)
        self.state_mock = AsyncMock(spec=FSMContext)
        self.message_mock = MagicMock(spec=Message)
        self.callback_query_mock = MagicMock(spec=CallbackQuery)
        self.message_mock.from_user.id = 123
        self.message_mock.from_user.username = "testuser"
        self.callback_query_mock.from_user.id = 123
        self.callback_query_mock.message = self.message_mock
        self.callback_query_mock.from_user.username = "testcallbackuser"

    async def test_open_dispute_handler_success(self):
        self.callback_query_mock.data = "p2p_open_dispute_1"
        order = P2POrder(id=1, user_id=123, taker_id=456, status=P2POrderStatus.IN_PROGRESS)
        self.p2p_service_mock.get_order_by_id.return_value = order
        self.p2p_service_mock.open_dispute.return_value = {'success': True}
        await open_dispute_handler(self.callback_query_mock, self.state_mock, self.p2p_service_mock)
        self.p2p_service_mock.open_dispute.assert_awaited_once_with(1, 123)
        self.callback_query_mock.message.answer.assert_called_with("Диспут открыт. Ожидайте решения администрации.")
        self.callback_query_mock.answer.assert_called_once()

    async def test_open_dispute_handler_order_not_found(self):
        self.callback_query_mock.data = "p2p_open_dispute_1"
        self.p2p_service_mock.get_order_by_id.return_value = None
        await open_dispute_handler(self.callback_query_mock, self.state_mock, self.p2p_service_mock)
        self.callback_query_mock.message.answer.assert_called_with("Ордер не найден.")
        self.callback_query_mock.answer.assert_called_once()
        self.p2p_service_mock.open_dispute.assert_not_awaited()

    async def test_open_dispute_handler_wrong_user(self):
        self.callback_query_mock.data = "p2p_open_dispute_1"
        order = P2POrder(id=1, user_id=456, taker_id=789, status=P2POrderStatus.IN_PROGRESS)
        self.p2p_service_mock.get_order_by_id.return_value = order
        await open_dispute_handler(self.callback_query_mock, self.state_mock, self.p2p_service_mock)
        self.callback_query_mock.message.answer.assert_called_with("Вы не можете открыть диспут по этому ордеру.")
        self.callback_query_mock.answer.assert_called_once()
        self.p2p_service_mock.open_dispute.assert_not_awaited()

    async def test_open_dispute_handler_wrong_status(self):
        self.callback_query_mock.data = "p2p_open_dispute_1"
        order = P2POrder(id=1, user_id=123, taker_id=456, status=P2POrderStatus.OPEN)
        self.p2p_service_mock.get_order_by_id.return_value = order
        await open_dispute_handler(self.callback_query_mock, self.state_mock, self.p2p_service_mock)
        self.callback_query_mock.message.answer.assert_called_with("Неверный статус ордера.")
        self.callback_query_mock.answer.assert_called_once()
        self.p2p_service_mock.open_dispute.assert_not_awaited()

    async def test_open_dispute_handler_failure(self):
        self.callback_query_mock.data = "p2p_open_dispute_1"
        order = P2POrder(id=1, user_id=123, taker_id=456, status=P2POrderStatus.IN_PROGRESS)
        self.p2p_service_mock.get_order_by_id.return_value = order
        self.p2p_service_mock.open_dispute.return_value = {'success': False, 'error': 'Some error'}
        await open_dispute_handler(self.callback_query_mock, self.state_mock, self.p2p_service_mock)
        self.callback_query_mock.message.answer.assert_called_with("Ошибка: Some error")
        self.callback_query_mock.answer.assert_called_once()

    @patch('bot.handlers.p2p_handler.Database')
    async def test_resolve_dispute_handler_not_admin(self, mock_db):
        mock_db.return_value.get_session.return_value.query.return_value.filter.return_value.first.return_value = User(is_admin=False)
        await resolve_dispute_handler(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called_with("У вас нет прав для выполнения этой команды.")
        self.state_mock.set_state.assert_not_called()
        self.state_mock.update_data.assert_not_called()

    @patch('bot.handlers.p2p_handler.Database')
    async def test_resolve_dispute_handler_admin(self, mock_db):
        mock_db.return_value.get_session.return_value.query.return_value.filter.return_value.first.return_value = User(is_admin=True)
        await resolve_dispute_handler(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called_with("Введите ID ордера, по которому нужно разрешить диспут:")
        self.state_mock.set_state.assert_called_once_with(P2POrderStates.resolving_dispute.state)
        self.state_mock.update_data.assert_called_once_with(admin_id=123)

    async def test_process_dispute_resolution_invalid_order_id(self):
        self.message_mock.text = "INVALID"
        await process_dispute_resolution(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called_with("Неверный ID ордера. Пожалуйста, введите число.")
        self.p2p_service_mock.get_order_by_id.assert_not_awaited()
        self.state_mock.set_state.assert_not_called()

    async def test_process_dispute_resolution_order_not_found(self):
        self.message_mock.text = "1"
        self.p2p_service_mock.get_order_by_id.return_value = None
        await process_dispute_resolution(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called_with("Ордер не найден.")
        self.p2p_service_mock.get_order_by_id.assert_awaited_once_with(1)
        self.state_mock.set_state.assert_not_called()

    async def test_process_dispute_resolution_order_not_in_dispute(self):
        self.message_mock.text = "1"
        order = P2POrder(id=1, status=P2POrderStatus.IN_PROGRESS)  #  DISPUTE
        self.p2p_service_mock.get_order_by_id.return_value = order
        await process_dispute_resolution(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called_with("Ордер не находится в статусе диспута.")
        self.state_mock.set_state.assert_not_called()

    async def test_process_dispute_resolution_success(self):
        self.message_mock.text = "1"
        order = P2POrder(id=1, user_id=123, taker_id=456, status=P2POrderStatus.DISPUTE)
        self.p2p_service_mock.get_order_by_id.return_value = order
        self.state_mock.get_data.return_value = {'admin_id': 789}  #  admin_id
        await process_dispute_resolution(self.message_mock, self.state_mock, self.p2p_service_mock)
        self.message_mock.answer.assert_called_with(ANY, reply_markup=ANY)  #  клавиатура
        self.state_mock.update_data.assert_called_with(order_id=1, admin_id=789)  #  admin_id
        self.state_mock.set_state.assert_called_once_with(P2POrderStates.waiting_for_dispute_decision.state)

    async def test_handle_dispute_decision_refund(self):
        self.callback_query_mock.data = "p2p_dispute_decision_refund"
        self.state_mock.get_data.return_value = {'order_id': 1, 'admin_id': 789}
        order = P2POrder(id=1, user_id=123, taker_id=456, status=P2POrderStatus.DISPUTE)
        self.p2p_service_mock.get_order_by_id.return_value = order
        self.p2p_service_mock.resolve_dispute.return_value = {'success': True}
        await handle_dispute_decision(self.callback_query_mock, self.state_mock, self.p2p_service_mock)
        self.p2p_service_mock.resolve_dispute.assert_awaited_once_with(1, 789, 'refund')  #  admin_id
        self.callback_query_mock.message.answer.assert_called_with("Диспут разрешен: возврат средств покупателю.")
        self.callback_query_mock.answer.assert_called_once()
        self.state_mock.finish.assert_called_once()

    async def test_handle_dispute_decision_complete(self):
        self.callback_query_mock.data = "p2p_dispute_decision_complete"
        self.state_mock.get_data.return_value = {'order_id': 1, 'admin_id': 789}
        order = P2POrder(id=1, user_id=123, taker_id=456, status=P2POrderStatus.DISPUTE)
        self.p2p_service_mock.get_order_by_id.return_value = order
        self.p2p_service_mock.resolve_dispute.return_value = {'success': True}
        await handle_dispute_decision(self.callback_query_mock, self.state_mock, self.p2p_service_mock)
        self.p2p_service_mock.resolve_dispute.assert_awaited_once_with(1, 789, 'complete')  #  admin_id
        self.callback_query_mock.message.answer.assert_called_with("Диспут разрешен: завершение в пользу продавца.")
        self.callback_query_mock.answer.assert_called_once()
        self.state_mock.finish.assert_called_once()

    async def test_handle_dispute_decision_failure(self):
        self.callback_query_mock.data = "p2p_dispute_decision_refund"
        self.state_mock.get_data.return_value = {'order_id': 1, 'admin_id': 789}
        order = P2POrder(id=1, user_id=123, taker_id=456, status=P2POrderStatus.DISPUTE)
        self.p2p_service_mock.get_order_by_id.return_value = order
        self.p2p_service_mock.resolve_dispute.return_value = {'success': False, 'error': 'Some error'}
        await handle_dispute_decision(self.callback_query_mock, self.state_mock, self.p2p_service_mock)
        self.callback_query_mock.message.answer.assert_called_with("Ошибка при разрешении диспута: Some error")
        self.callback_query_mock.answer.assert_called_once()
        self.state_mock.finish.assert_called_once() 