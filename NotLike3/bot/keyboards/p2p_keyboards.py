from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from core.database.models import P2PPaymentMethod

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

def p2p_payment_method_keyboard():
    """Клавиатура выбора способа оплаты."""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [KeyboardButton(pm.name) for pm in P2PPaymentMethod]
    buttons.append(KeyboardButton("Назад")) #  в главное меню
    keyboard.add(*buttons)
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