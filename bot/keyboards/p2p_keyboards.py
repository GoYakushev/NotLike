from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from core.database.models import P2PPaymentMethod
from typing import List
from services.p2p.p2p_service import P2PService  #  P2PService

def p2p_menu_keyboard():
    """Клавиатура главного меню P2P."""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("Создать P2P ордер"),
        KeyboardButton("Список P2P ордеров"),
        KeyboardButton("Мои P2P ордера"),
        KeyboardButton("Назад")  #  в главное меню
    ]
    keyboard.add(*buttons)
    return keyboard

def p2p_side_keyboard():
    """Клавиатура выбора стороны (BUY/SELL)."""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("BUY"),
        KeyboardButton("SELL"),
        KeyboardButton("Назад") #  в главное меню
    ]
    keyboard.add(*buttons)
    return keyboard

async def p2p_payment_method_keyboard(p2p_service: P2PService) -> InlineKeyboardMarkup:
    """Клавиатура со списком способов оплаты."""
    session = p2p_service.db.get_session()
    payment_methods: List[P2PPaymentMethod] = session.query(P2PPaymentMethod).all()
    keyboard = InlineKeyboardMarkup(row_width=2)
    for method in payment_methods:
        keyboard.add(
            InlineKeyboardButton(method.name, callback_data=f"p2p_paymentmethod_{method.id}")
        )
    session.close()
    return keyboard

def confirm_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("Подтвердить"),
        KeyboardButton("Назад")
    ]
    keyboard.add(*buttons)
    return keyboard

def back_to_p2p_menu_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("Назад в P2P меню"))
    return keyboard

def p2p_order_keyboard(order_id: int, is_owner: bool = False):
    """
    Генерирует клавиатуру для конкретного P2P ордера.

    :param order_id: ID ордера.
    :param is_owner: Является ли текущий пользователь владельцем ордера.
    :return: InlineKeyboardMarkup.
    """
    keyboard = InlineKeyboardMarkup(row_width=1)
    buttons = []

    if is_owner:
        buttons.append(InlineKeyboardButton("Отменить ордер", callback_data=f"p2p_cancel_{order_id}"))
        buttons.append(InlineKeyboardButton("Подтвердить получение оплаты", callback_data=f"p2p_confirm_payment_{order_id}"))
    else:
        buttons.append(InlineKeyboardButton("Принять ордер", callback_data=f"p2p_take_{order_id}"))

    buttons.append(InlineKeyboardButton("Назад", callback_data="p2p_back_to_list")) #  к списку
    keyboard.add(*buttons)
    return keyboard

def confirm_payment_keyboard():
    """Клавиатура для подтверждения получения оплаты."""
    keyboard = InlineKeyboardMarkup(row_width=1)
    confirm_button = InlineKeyboardButton("✅ Подтвердить получение оплаты", callback_data="confirm_payment")
    keyboard.add(confirm_button)

def dispute_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для решения диспута (для админа)."""
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("Вернуть средства покупателю", callback_data=f"p2p_dispute_decision_refund_{order_id}"),
        InlineKeyboardButton("Завершить в пользу продавца", callback_data=f"p2p_dispute_decision_complete_{order_id}")
    )
    return keyboard

def leave_review_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для оставления отзыва."""
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("👍", callback_data=f"p2p_leave_review_positive_{order_id}"),
        InlineKeyboardButton("👎", callback_data=f"p2p_leave_review_negative_{order_id}"),
        InlineKeyboardButton("Пропустить", callback_data=f"p2p_leave_review_skip_{order_id}")
    )
    return keyboard

def p2p_filters_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора фильтров P2P."""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("Базовая валюта", callback_data="p2p_filter_base"),
        InlineKeyboardButton("Котируемая валюта", callback_data="p2p_filter_quote")
    )
    keyboard.add(
        InlineKeyboardButton("Способ оплаты", callback_data="p2p_filter_payment"),
        InlineKeyboardButton("Сбросить фильтры", callback_data="p2p_filter_reset")
    )
    keyboard.add(InlineKeyboardButton("Применить", callback_data="p2p_filter_apply"))
    return keyboard 