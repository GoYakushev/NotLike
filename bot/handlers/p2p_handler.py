from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from services.p2p.p2p_service import P2PService
from bot.keyboards.p2p_keyboards import (
    p2p_menu_keyboard, p2p_side_keyboard, p2p_payment_method_keyboard,
    confirm_keyboard, back_to_p2p_menu_keyboard, p2p_order_keyboard,
    confirm_payment_keyboard, dispute_keyboard, leave_review_keyboard,
    p2p_filters_keyboard,  #  клавиатура фильтров
)
from core.database.database import Database, db
from services.wallet.wallet_service import WalletService
from services.notifications.notification_service import NotificationService, NotificationType
from core.database.models import P2PPaymentMethod, P2POrderStatus, P2POrder, User
from datetime import datetime, timedelta
from services.rating.rating_service import RatingService
from bot.config import config
import aioschedule
import asyncio
from typing import Union
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

# Инициализируем сервисы
wallet_service = WalletService()
notification_service = NotificationService(bot)
p2p_service = P2PService(db, wallet_service, notification_service)
rating_service = RatingService(db)

class P2POrderStates(StatesGroup):
    waiting_for_side = State()
    waiting_for_base_currency = State()
    waiting_for_quote_currency = State()
    waiting_for_amount = State()
    waiting_for_price = State()
    waiting_for_payment_method = State()
    confirm_order = State()
    waiting_for_order_id = State()
    confirming_payment = State()
    opening_dispute = State()
    resolving_dispute = State()
    leaving_review = State()
    waiting_for_rating = State()
    waiting_for_review_comment = State()
    setting_filters = State()  #  фильтров
    waiting_for_filter_base_currency = State()  #  базовой валюты
    waiting_for_filter_quote_currency = State()  #  котируемой валюты
    waiting_for_filter_payment_method = State()  #  способа оплаты
    waiting_for_dispute_decision = State()  #  

class P2PStates(StatesGroup):
    choosing_action = State()
    choosing_network = State()
    choosing_token = State()
    entering_amount = State()
    entering_price = State()
    entering_min_amount = State()
    entering_max_amount = State()
    confirming_order = State()
    viewing_order = State()
    entering_message = State()

p2p_service = None

async def initialize_p2p_service(db, wallet_service, notification_service):
    global p2p_service
    p2p_service = P2PService(db, wallet_service, notification_service)

async def p2p_start(message: types.Message, state: FSMContext):
    """Начало работы с P2P."""
    await message.answer("Выберите действие:", reply_markup=p2p_menu_keyboard())
    await state.finish()

async def show_menu(callback_query: types.CallbackQuery, state: FSMContext):
    """Показывает меню P2P."""
    await callback_query.message.answer("Выберите действие:", reply_markup=p2p_menu_keyboard())
    await state.finish()
    await callback_query.answer()

async def choose_side(callback_query: types.CallbackQuery, state: FSMContext):
    """Выбор стороны (BUY/SELL)."""
    await P2POrderStates.waiting_for_side.set()
    await callback_query.message.answer("Вы хотите купить или продать?", reply_markup=p2p_side_keyboard())
    await callback_query.answer()

async def process_side(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработка выбора стороны."""
    side = callback_query.data.split('_')[1].upper()
    await state.update_data(side=side)
    await P2POrderStates.waiting_for_base_currency.set()
    await callback_query.message.answer("Введите базовую валюту (например, TON):")
    await callback_query.answer()

async def process_base_currency(message: types.Message, state: FSMContext):
    """Обработка ввода базовой валюты."""
    base_currency = message.text.upper()
    await state.update_data(base_currency=base_currency)
    await P2POrderStates.waiting_for_quote_currency.set()
    await message.answer("Введите котируемую валюту (например, USDT):")

async def process_quote_currency(message: types.Message, state: FSMContext):
    """Обработка ввода котируемой валюты."""
    quote_currency = message.text.upper()
    await state.update_data(quote_currency=quote_currency)
    await P2POrderStates.waiting_for_amount.set()
    await message.answer("Введите количество базовой валюты:")

async def process_amount(message: types.Message, state: FSMContext):
    """Обработка ввода количества."""
    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError
        await state.update_data(amount=amount)
        await P2POrderStates.waiting_for_price.set()
        await message.answer("Введите цену за единицу базовой валюты:")
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число (больше нуля).")

async def process_price(message: types.Message, state: FSMContext):
    """Обработка ввода цены."""
    try:
        price = float(message.text)
        if price <= 0:
            raise ValueError
        await state.update_data(price=price)
        await P2POrderStates.waiting_for_payment_method.set()
        await message.answer("Выберите способ оплаты:", reply_markup=await p2p_payment_method_keyboard(p2p_service))
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число (больше нуля).")

async def process_payment_method(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработка выбора способа оплаты."""
    payment_method = callback_query.data.split('_')[2]
    await state.update_data(payment_method=payment_method)
    order_data = await state.get_data()

    text = (
        "Подтвердите создание ордера:\n\n"
        f"Тип: {order_data['side']}\n"
        f"Базовая валюта: {order_data['base_currency']}\n"
        f"Котируемая валюта: {order_data['quote_currency']}\n"
        f"Количество: {order_data['amount']}\n"
        f"Цена: {order_data['price']}\n"
        f"Способ оплаты: {payment_method}\n"
    )

    await callback_query.message.answer(text, reply_markup=confirm_keyboard())
    await P2POrderStates.confirm_order.set()
    await callback_query.answer()

async def confirm_create_order(callback_query: types.CallbackQuery, state: FSMContext):
    """Подтверждение создания ордера."""
    if callback_query.data == 'confirm':
        order_data = await state.get_data()
        payment_method_id = order_data.get('payment_method')
        session = db.get_session()
        payment_method = session.query(P2PPaymentMethod).get(payment_method_id)
        if not payment_method:
            await callback_query.message.answer("Способ оплаты не найден.")
            await state.finish()
            return
        payment_method_name = payment_method.name
        session.close()

        result = await p2p_service.create_order(
            user_id=callback_query.from_user.id,
            side=order_data['side'],
            base_currency=order_data['base_currency'],
            quote_currency=order_data['quote_currency'],
            amount=order_data['amount'],
            price=order_data['price'],
            payment_method=payment_method_name,
        )

        if result['success']:
            await callback_query.message.answer(f"✅ Ордер создан! ID: {result['order_id']}")
        else:
            await callback_query.message.answer(f"❌ Ошибка: {result['error']}")
    else:
        await callback_query.message.answer("❌ Создание ордера отменено.")

    await state.finish()
    await callback_query.answer()

async def cancel_p2p_order(callback_query: types.CallbackQuery, state: FSMContext):
    """Отмена P2P ордера."""
    order_id = int(callback_query.data.split('_')[2])
    result = await p2p_service.cancel_p2p_order(order_id, callback_query.from_user.id)
    if result['success']:
        await callback_query.message.answer("✅ Ордер отменен.")
    else:
        await callback_query.message.answer(f"❌ Ошибка: {result['error']}")
    await callback_query.answer()

async def confirm_payment_handler(callback_query: types.CallbackQuery, state: FSMContext):
    """Подтверждение получения оплаты."""
    order_id = int(callback_query.data.split('_')[2])
    await state.update_data(order_id=order_id)
    await P2POrderStates.confirming_payment.set()
    await callback_query.message.answer("Вы уверены, что получили оплату?", reply_markup=confirm_payment_keyboard(order_id))
    await callback_query.answer()

async def process_confirm_payment(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработка подтверждения оплаты."""
    order_id = int(callback_query.data.split('_')[2])
    if callback_query.data.startswith("p2p_confirm_payment_yes_"):
        result = await p2p_service.complete_p2p_order(order_id)
        if result['success']:
            await callback_query.message.answer("✅ Ордер успешно завершен!")
        else:
            await callback_query.message.answer(f"❌ Ошибка: {result['error']}")
    else:
        await callback_query.message.answer("❌ Подтверждение оплаты отменено.")
    await state.finish()
    await callback_query.answer()

async def open_dispute_handler(callback_query: types.CallbackQuery, state: FSMContext):
    """Открытие диспута."""
    order_id = int(callback_query.data.split('_')[2])
    result = await p2p_service.open_dispute(order_id, callback_query.from_user.id)
    if result['success']:
        await callback_query.message.answer("⚠️ Диспут открыт. Ожидайте решения администрации.")
    else:
        await callback_query.message.answer(f"❌ Ошибка: {result['error']}")
    await callback_query.answer()

async def process_dispute_resolution(message: types.Message, state: FSMContext, p2p_service: P2PService):
    try:
        order_id = int(message.text)
    except ValueError:
        await message.answer("Пожалуйста, введите корректный ID ордера.")
        return

    order = await p2p_service.get_order_by_id(order_id)
    if not order:
        await message.answer("Ордер с таким ID не найден.")
        return

    if order.status != P2POrderStatus.DISPUTE:
        await message.answer("Этот ордер не находится в статусе диспута.")
        return

    await message.answer(f"Выберите решение для ордера #{order_id}:", reply_markup=dispute_keyboard(order_id))
    await P2POrderStates.resolving_dispute.set()

async def handle_dispute_decision(callback_query: types.CallbackQuery, state: FSMContext):
    order_id = int(callback_query.data.split('_')[-1])
    decision = callback_query.data.split('_')[3]

    if decision == "refund":
        result = await p2p_service.resolve_dispute(order_id, callback_query.from_user.id, "refund")
    elif decision == "complete":
        result = await p2p_service.resolve_dispute(order_id, callback_query.from_user.id, "complete")
    else:
        await callback_query.message.answer("Неверное решение.")
        return

    if result and result.get('success'):
        await callback_query.message.answer(f"✅ Диспут по ордеру #{order_id} разрешен.")
    else:
        await callback_query.message.answer(f"❌ Ошибка при разрешении диспута: {result.get('error')}")

    await state.finish()
    await callback_query.answer()

async def leave_review_handler(callback_query: types.CallbackQuery, state: FSMContext):
    order_id = int(callback_query.data.split('_')[-1])
    await state.update_data(order_id=order_id)
    await P2POrderStates.waiting_for_rating.set()
    await callback_query.message.answer("Пожалуйста, оцените сделку (от 1 до 5):")
    await callback_query.answer()

async def process_rating(message: types.Message, state: FSMContext):
    try:
        rating = int(message.text)
        if not 1 <= rating <= 5:
            raise ValueError
        await state.update_data(rating=rating)
        await P2POrderStates.waiting_for_review_comment.set()
        await message.answer("Оставьте комментарий к отзыву (необязательно):")
    except ValueError:
        await message.answer("Пожалуйста, введите число от 1 до 5.")

async def process_review_comment(message: types.Message, state: FSMContext):
    comment = message.text
    data = await state.get_data()
    order_id = data['order_id']
    rating = data['rating']

    order = await p2p_service.get_order_by_id(order_id)
    if not order:
        await message.answer("Ордер не найден.")
        await state.finish()
        return

    #  ID  ,   
    if order.user_id == message.from_user.id:
        reviewee_id = order.taker_id
    elif order.taker_id == message.from_user.id:
        reviewee_id = order.user_id
    else:
        await message.answer("Вы не являетесь участником этого ордера.")
        await state.finish()
        return

    result = await rating_service.add_review(message.from_user.id, reviewee_id, rating, comment, order_id)

    if result['success']:
        await message.answer("✅ Спасибо за ваш отзыв!")
    else:
        await message.answer(f"❌ Ошибка: {result['error']}")

    await state.finish()

async def show_user_rating_handler(message: types.Message):
    try:
        user_id = int(message.text.split()[1]) #  аргумент
    except (IndexError, ValueError):
        user_id = message.from_user.id #  ID

    rating = await rating_service.get_user_rating(user_id)

    if rating is not None:
        await message.answer(f"Рейтинг пользователя: {rating:.2f}") #  2  
    else:
        await message.answer("Пользователь не найден или у него еще нет рейтинга.")

async def show_p2p_ads(callback_query: types.CallbackQuery, order_type: str, state: FSMContext):
    """Показывает список P2P ордеров с учетом фильтров."""
    user_data = await state.get_data()
    base_currency = user_data.get('filter_base_currency')
    quote_currency = user_data.get('filter_quote_currency')
    payment_method_id = user_data.get('filter_payment_method')

    payment_method_name = None
    if payment_method_id:
        session = db.get_session()
        payment_method = session.query(P2PPaymentMethod).get(payment_method_id)
        if payment_method:
            payment_method_name = payment_method.name
        session.close()

    orders = await p2p_service.get_open_orders(
        side=order_type,
        base_currency=base_currency,
        quote_currency=quote_currency,
        payment_method=payment_method_name
    )
    text = f"Доступные ордера ({order_type}):\n\n"

    for order in orders:
        text += (
            f"ID: {order.id}\n"
            f"Цена: {order.price}\n"
            f"Количество: {order.crypto_amount}\n"
            f"Способ оплаты: {order.payment_method}\n\n"
        )

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("Назад", callback_data="p2p_menu"))
    keyboard.add(
        types.InlineKeyboardButton("Фильтры", callback_data="p2p_filters")
    )
    await callback_query.message.answer(text, reply_markup=keyboard)
    await callback_query.answer()

async def take_p2p_order(callback_query: types.CallbackQuery):
    order_id = int(callback_query.data.split('_')[2])
    result = await p2p_service.take_order(order_id, callback_query.from_user.id)

    if result['success']:
        await callback_query.message.answer("✅ Вы приняли ордер!")
    else:
        await callback_query.message.answer(f"❌ Ошибка: {result['error']}")
    await callback_query.answer()

async def confirm_p2p_payment(callback_query: types.CallbackQuery):
    order_id = int(callback_query.data.split('_')[2])
    result = await p2p_service.confirm_payment(order_id, callback_query.from_user.id)
    if result['success']:
        await callback_query.message.answer("✅ Вы подтвердили оплату!")
    else:
        await callback_query.message.answer(f"❌ Ошибка: {result['error']}")
    await callback_query.answer()

async def complete_p2p_order_handler(callback_query: types.CallbackQuery):
    order_id = int(callback_query.data.split('_')[2])
    result = await p2p_service.complete_p2p_order(order_id, callback_query.from_user.id)
    if result['success']:
        await callback_query.message.answer("✅ Ордер завершен!")
    else:
        await callback_query.message.answer(f"❌ Ошибка: {result['error']}")
    await callback_query.answer()

async def cancel_p2p_order_handler(callback_query: types.CallbackQuery):
    order_id = int(callback_query.data.split('_')[2])
    result = await p2p_service.cancel_p2p_order(order_id, callback_query.from_user.id)
    if result['success']:
        await callback_query.message.answer("✅ Ордер отменен!")
    else:
        await callback_query.message.answer(f"❌ Ошибка: {result['error']}")
    await callback_query.answer()

async def my_p2p_orders_handler(callback_query: types.CallbackQuery):
    orders = await p2p_service.get_user_p2p_orders(callback_query.from_user.id)
    if not orders:
        await callback_query.message.answer("У вас нет активных P2P ордеров.")
        return

    text = "Ваши P2P ордера:\n\n"
    for order in orders:
        text += (
            f"ID: {order.id}\n"
            f"Тип: {order.side}\n"
            f"Статус: {order.status}\n"
            f"Цена: {order.price}\n"
            f"Количество: {order.crypto_amount}\n\n"
        )

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("Назад", callback_data="p2p_menu"))
    await callback_query.message.answer(text, reply_markup=keyboard)
    await callback_query.answer()

async def create_p2p_order_handler(callback_query: types.CallbackQuery):
    await choose_side(callback_query, callback_query.message.from_user.id)
    await callback_query.answer()

async def process_p2p_callback(callback_query: types.CallbackQuery, state: FSMContext):
    action = callback_query.data.split('_')[1]

    if action in ('buy', 'sell'):
        await show_p2p_ads(callback_query, 'SELL' if action == 'buy' else 'BUY', state=state)
    elif action == 'menu':
        await show_p2p_menu(callback_query.message)
    elif action == 'take':
        await take_p2p_order(callback_query)
    elif action == 'confirm':
        await confirm_p2p_payment(callback_query)
    elif action == 'complete':
        await complete_p2p_order_handler(callback_query)
    elif action == 'cancel':
        await cancel_p2p_order_handler(callback_query)
    elif action == 'my':
        await my_p2p_orders_handler(callback_query)
    elif action == 'create':
        await create_p2p_order_handler(callback_query)
    elif action == 'view':
        await view_p2p_order_handler(callback_query)
    elif action == 'filters':
        await set_p2p_filters(callback_query, state)  #  фильтров

async def view_p2p_order_handler(callback_query: types.CallbackQuery):
    order_id = int(callback_query.data.split('_')[2])
    order = await p2p_service.get_order_by_id(order_id)

    if not order:
        await callback_query.message.answer("Ордер не найден.")
        return

    text = (
        f"Детали ордера #{order.id}:\n\n"
        f"Тип: {order.side}\n"
        f"Базовая валюта: {order.base_currency}\n"
        f"Котируемая валюта: {order.quote_currency}\n"
        f"Количество: {order.crypto_amount}\n"
        f"Цена: {order.price}\n"
        f"Способ оплаты: {order.payment_method}\n"
        f"Статус: {order.status}\n"
    )

    keyboard = types.InlineKeyboardMarkup()
    if order.status == P2POrderStatus.OPEN and order.user_id != callback_query.from_user.id:
        keyboard.add(types.InlineKeyboardButton("Принять", callback_data=f"p2p_take_{order.id}"))
    if order.status == P2POrderStatus.IN_PROGRESS and order.user_id == callback_query.from_user.id:
        keyboard.add(types.InlineKeyboardButton("Подтвердить оплату", callback_data=f"p2p_confirm_payment_{order.id}"))
    if order.status == P2POrderStatus.IN_PROGRESS and (order.user_id == callback_query.from_user.id or order.taker_id == callback_query.from_user.id):
        keyboard.add(types.InlineKeyboardButton("Открыть диспут", callback_data=f"p2p_open_dispute_{order.id}"))
    if order.user_id == callback_query.from_user.id or order.taker_id == callback_query.from_user.id:
        keyboard.add(types.InlineKeyboardButton("Отменить", callback_data=f"p2p_cancel_{order.id}"))
    keyboard.add(types.InlineKeyboardButton("Назад", callback_data="p2p_menu"))

    await callback_query.message.answer(text, reply_markup=keyboard)
    await callback_query.answer()

async def check_expired_orders():
    """Проверяет и отменяет просроченные P2P ордера."""
    session = db.get_session()
    now = datetime.utcnow()
    expired_orders = session.query(P2POrder).filter(P2POrder.status == P2POrderStatus.OPEN, P2POrder.expires_at <= now).all()

    for order in expired_orders:
        try:
            await p2p_service.cancel_p2p_order(order.id, order.user_id)
            print(f"P2P order #{order.id} expired and canceled.")
        except Exception as e:
            print(f"Error canceling expired P2P order #{order.id}: {e}")

    session.close()

async def set_p2p_filters(callback_query: types.CallbackQuery, state: FSMContext):
    """Начало установки фильтров для P2P."""
    await P2POrderStates.setting_filters.set()
    await callback_query.message.answer("Выберите фильтры:", reply_markup=p2p_filters_keyboard())
    await callback_query.answer()

async def process_p2p_filter_choice(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработка выбора фильтра."""
    filter_type = callback_query.data.split('_')[2]  #  "p2p_filter_base" -> "base"

    if filter_type == "base":
        await P2POrderStates.waiting_for_filter_base_currency.set()
        await callback_query.message.answer("Введите базовую валюту (например, TON):")
    elif filter_type == "quote":
        await P2POrderStates.waiting_for_filter_quote_currency.set()
        await callback_query.message.answer("Введите котируемую валюту (например, USDT):")
    elif filter_type == "payment":
        await P2POrderStates.waiting_for_filter_payment_method.set()
        await callback_query.message.answer("Выберите способ оплаты:", reply_markup=await p2p_payment_method_keyboard(p2p_service))
    elif filter_type == "reset":
        await state.update_data(filter_base_currency=None, filter_quote_currency=None, filter_payment_method=None)
        await callback_query.message.answer("Фильтры сброшены.")
        await state.finish()
        await show_menu(callback_query, state)  #  в меню
    elif filter_type == "apply":
        await callback_query.message.answer("Фильтры применены.")
        await state.finish()
        await show_menu(callback_query, state)  #  в меню

    await callback_query.answer()

async def process_filter_base_currency(message: types.Message, state: FSMContext):
    """Обработка ввода базовой валюты для фильтра."""
    base_currency = message.text.upper()
    await state.update_data(filter_base_currency=base_currency)
    await P2POrderStates.setting_filters.set()  #  к выбору фильтров
    await message.answer("Фильтр базовой валюты установлен. Выберите следующее действие:", reply_markup=p2p_filters_keyboard())

async def process_filter_quote_currency(message: types.Message, state: FSMContext):
    """Обработка ввода котируемой валюты для фильтра."""
    quote_currency = message.text.upper()
    await state.update_data(filter_quote_currency=quote_currency)
    await P2POrderStates.setting_filters.set()  #  к выбору фильтров
    await message.answer("Фильтр котируемой валюты установлен. Выберите следующее действие:", reply_markup=p2p_filters_keyboard())

async def process_filter_payment_method(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработка выбора способа оплаты для фильтра."""
    payment_method_id = callback_query.data.split('_')[2]
    await state.update_data(filter_payment_method=payment_method_id)
    await P2POrderStates.setting_filters.set()  #  к выбору фильтров
    await callback_query.message.answer("Фильтр способа оплаты установлен. Выберите следующее действие:", reply_markup=p2p_filters_keyboard())
    await callback_query.answer()

async def scheduler():
    aioschedule.every(1).minutes.do(check_expired_orders)
    while True:
        await aioschedule.run_pending()
        await asyncio.sleep(1)

def register_p2p_handlers(dp: Dispatcher, p2p_service: P2PService, rating_service: RatingService):
    dp.register_message_handler(p2p_start, commands=['p2p'], state="*")
    dp.register_callback_query_handler(show_menu, lambda c: c.data == 'p2p_menu', state="*")
    dp.register_callback_query_handler(choose_side, lambda c: c.data.startswith('p2p_'), state="*")
    dp.register_message_handler(process_base_currency, state=P2POrderStates.waiting_for_base_currency)
    dp.register_message_handler(process_quote_currency, state=P2POrderStates.waiting_for_quote_currency)
    dp.register_message_handler(process_amount, state=P2POrderStates.waiting_for_amount)
    dp.register_message_handler(process_price, state=P2POrderStates.waiting_for_price)
    dp.register_callback_query_handler(process_payment_method, lambda c: c.data.startswith('p2p_paymentmethod_'), state=P2POrderStates.waiting_for_payment_method)
    dp.register_callback_query_handler(confirm_create_order, lambda c: c.data == 'confirm' or c.data == 'cancel', state=P2POrderStates.confirm_order)
    dp.register_callback_query_handler(cancel_p2p_order, lambda c: c.data.startswith('p2p_cancel_'))
    dp.register_callback_query_handler(confirm_payment_handler, lambda c: c.data.startswith('p2p_confirm_payment_'))
    dp.register_callback_query_handler(process_confirm_payment, lambda c: c.data.startswith('p2p_confirm_payment_yes_') or c.data.startswith('p2p_confirm_payment_no_'))
    dp.register_callback_query_handler(open_dispute_handler, lambda c: c.data.startswith('p2p_open_dispute_'))
    dp.register_message_handler(process_dispute_resolution, state=P2POrderStates.resolving_dispute)
    dp.register_callback_query_handler(handle_dispute_decision, lambda c: c.data and c.data.startswith("p2p_dispute_decision_"), state="*")
    dp.register_callback_query_handler(leave_review_handler, lambda c: c.data and c.data.startswith("p2p_leave_review_"))
    dp.register_message_handler(process_rating, state=P2POrderStates.waiting_for_rating)
    dp.register_message_handler(process_review_comment, state=P2POrderStates.waiting_for_review_comment)
    dp.register_message_handler(show_user_rating_handler, commands=["rating"], state="*")
    dp.register_callback_query_handler(view_p2p_order_handler, lambda c: c.data.startswith("p2p_view_"))
    dp.register_callback_query_handler(set_p2p_filters, lambda c: c.data == "p2p_filters", state="*")
    dp.register_callback_query_handler(process_p2p_filter_choice, lambda c: c.data.startswith("p2p_filter_"), state=P2POrderStates.setting_filters)
    dp.register_message_handler(process_filter_base_currency, state=P2POrderStates.waiting_for_filter_base_currency)
    dp.register_message_handler(process_filter_quote_currency, state=P2POrderStates.waiting_for_filter_quote_currency)
    dp.register_callback_query_handler(process_filter_payment_method, lambda c: c.data.startswith("p2p_paymentmethod_"), state=P2POrderStates.waiting_for_filter_payment_method)
    dp.register_callback_query_handler(process_p2p_callback, lambda c: c.data.startswith("p2p_"))

    dp.register_message_handler(cancel_p2p_order_confirm, state=P2POrderStates.waiting_for_order_id)
    dp.register_callback_query_handler(take_p2p_order_handler, lambda c: c.data.startswith("p2p_take_"))
    dp.register_callback_query_handler(confirm_payment_handler, lambda c: c.data.startswith("p2p_confirm_payment_"))
    dp.register_callback_query_handler(handle_dispute_decision, lambda c: c.data.startswith("p2p_dispute_decision_"), state=P2POrderStates.waiting_for_dispute_decision)

    dp.register_message_handler(resolve_dispute_handler, commands=["resolve_dispute"], state="*")
    dp.register_message_handler(process_dispute_resolution, state=P2POrderStates.resolving_dispute)

async def show_p2p_menu(message: types.Message):
    """Показывает главное меню P2P торговли."""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(
            "📈 Создать объявление",
            callback_data="p2p_create"
        ),
        types.InlineKeyboardButton(
            "🔍 Найти объявления",
            callback_data="p2p_search"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "📋 Мои объявления",
            callback_data="p2p_my_orders"
        ),
        types.InlineKeyboardButton(
            "💼 Мои сделки",
            callback_data="p2p_my_deals"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "⭐️ Избранные продавцы",
            callback_data="p2p_favorites"
        ),
        types.InlineKeyboardButton(
            "📊 Статистика",
            callback_data="p2p_stats"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "◀️ Назад",
            callback_data="main_menu"
        )
    )

    await message.answer(
        "🤝 P2P Торговля\n\n"
        "Здесь вы можете покупать и продавать криптовалюту напрямую у других пользователей.\n"
        "Выберите действие:",
        reply_markup=keyboard
    )

async def process_p2p_callback(
    callback_query: types.CallbackQuery,
    state: FSMContext,
    p2p_service: P2PService
):
    """Обрабатывает callback-и меню P2P."""
    action = callback_query.data.split('_')[1]

    if action == "create":
        await start_order_creation(callback_query.message, state)
    elif action == "search":
        await show_search_filters(callback_query.message, state)
    elif action == "my_orders":
        await show_my_orders(callback_query.message, p2p_service)
    elif action == "my_deals":
        await show_my_deals(callback_query.message, p2p_service)
    elif action == "favorites":
        await show_favorite_sellers(callback_query.message, p2p_service)
    elif action == "stats":
        await show_p2p_stats(callback_query.message, p2p_service)
    else:
        await callback_query.answer("Неизвестное действие")

async def start_order_creation(message: types.Message, state: FSMContext):
    """Начинает процесс создания объявления."""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(
            "📈 Продать",
            callback_data="p2p_action_sell"
        ),
        types.InlineKeyboardButton(
            "📉 Купить",
            callback_data="p2p_action_buy"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "◀️ Назад",
            callback_data="p2p_menu"
        )
    )

    await message.edit_text(
        "📝 Создание P2P объявления\n\n"
        "Выберите тип объявления:",
        reply_markup=keyboard
    )
    await P2PStates.choosing_action.set()

async def process_action_selection(
    callback_query: types.CallbackQuery,
    state: FSMContext
):
    """Обрабатывает выбор типа объявления."""
    action = callback_query.data.split('_')[2]
    await state.update_data(action=action)

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(
            "🌐 Solana",
            callback_data="p2p_network_solana"
        ),
        types.InlineKeyboardButton(
            "💎 TON",
            callback_data="p2p_network_ton"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "◀️ Назад",
            callback_data="p2p_create"
        )
    )

    await callback_query.message.edit_text(
        "📝 Создание P2P объявления\n\n"
        "Выберите сеть:",
        reply_markup=keyboard
    )
    await P2PStates.choosing_network.set()

async def process_network_selection(
    callback_query: types.CallbackQuery,
    state: FSMContext
):
    """Обрабатывает выбор сети."""
    network = callback_query.data.split('_')[2]
    await state.update_data(network=network)

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    if network == 'solana':
        popular_tokens = [
            ('SOL', 'So11111111111111111111111111111111111111112'),
            ('USDT', 'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB'),
            ('USDC', 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'),
            ('RAY', '4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R')
        ]
    else:  # TON
        popular_tokens = [
            ('TON', 'ton-token-address'),
            ('USDT', 'usdt-token-address'),
            ('BOLT', 'bolt-token-address'),
            ('STONE', 'stone-token-address')
        ]

    for token_name, token_address in popular_tokens:
        keyboard.add(
            types.InlineKeyboardButton(
                f"{token_name}",
                callback_data=f"p2p_token_{token_address}"
            )
        )

    keyboard.add(
        types.InlineKeyboardButton(
            "🔍 Другой токен",
            callback_data="p2p_token_custom"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "◀️ Назад",
            callback_data="p2p_create"
        )
    )

    await callback_query.message.edit_text(
        "📝 Создание P2P объявления\n\n"
        "Выберите токен:",
        reply_markup=keyboard
    )
    await P2PStates.choosing_token.set()

async def process_token_selection(
    callback_query: types.CallbackQuery,
    state: FSMContext
):
    """Обрабатывает выбор токена."""
    if callback_query.data == "p2p_token_custom":
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                "◀️ Назад",
                callback_data="p2p_network_solana"
            )
        )

        await callback_query.message.edit_text(
            "📝 Создание P2P объявления\n\n"
            "Введите адрес токена:",
            reply_markup=keyboard
        )
        return

    token_address = callback_query.data.split('_')[2]
    await process_token_address(callback_query.message, token_address, state)

async def process_token_address(
    message: types.Message,
    token_address: str,
    state: FSMContext
):
    """Обрабатывает адрес токена."""
    await state.update_data(token_address=token_address)

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton(
            "◀️ Назад",
            callback_data="p2p_network_solana"
        )
    )

    await message.edit_text(
        "📝 Создание P2P объявления\n\n"
        "Введите количество токенов:",
        reply_markup=keyboard
    )
    await P2PStates.entering_amount.set()

async def process_amount(message: types.Message, state: FSMContext):
    """Обрабатывает ввод количества токенов."""
    try:
        amount = Decimal(message.text)
        if amount <= 0:
            await message.answer("❌ Количество должно быть больше 0")
            return

        await state.update_data(amount=str(amount))

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                "◀️ Назад",
                callback_data="p2p_token_custom"
            )
        )

        await message.answer(
            "📝 Создание P2P объявления\n\n"
            "Введите цену за токен в USDT:",
            reply_markup=keyboard
        )
        await P2PStates.entering_price.set()

    except ValueError:
        await message.answer("❌ Введите корректное число")

async def process_price(message: types.Message, state: FSMContext):
    """Обрабатывает ввод цены."""
    try:
        price = Decimal(message.text)
        if price <= 0:
            await message.answer("❌ Цена должна быть больше 0")
            return

        await state.update_data(price=str(price))

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                "◀️ Назад",
                callback_data="p2p_amount"
            )
        )

        await message.answer(
            "📝 Создание P2P объявления\n\n"
            "Введите минимальную сумму сделки в USDT:",
            reply_markup=keyboard
        )
        await P2PStates.entering_min_amount.set()

    except ValueError:
        await message.answer("❌ Введите корректное число")

async def process_min_amount(message: types.Message, state: FSMContext):
    """Обрабатывает ввод минимальной суммы."""
    try:
        min_amount = Decimal(message.text)
        if min_amount <= 0:
            await message.answer("❌ Минимальная сумма должна быть больше 0")
            return

        await state.update_data(min_amount=str(min_amount))

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                "◀️ Назад",
                callback_data="p2p_price"
            )
        )

        await message.answer(
            "📝 Создание P2P объявления\n\n"
            "Введите максимальную сумму сделки в USDT:",
            reply_markup=keyboard
        )
        await P2PStates.entering_max_amount.set()

    except ValueError:
        await message.answer("❌ Введите корректное число")

async def process_max_amount(
    message: types.Message,
    state: FSMContext,
    p2p_service: P2PService
):
    """Обрабатывает ввод максимальной суммы и создает объявление."""
    try:
        max_amount = Decimal(message.text)
        state_data = await state.get_data()
        min_amount = Decimal(state_data['min_amount'])

        if max_amount <= 0:
            await message.answer("❌ Максимальная сумма должна быть больше 0")
            return
        if max_amount < min_amount:
            await message.answer("❌ Максимальная сумма должна быть больше минимальной")
            return

        # Создаем объявление
        order = await p2p_service.create_order(
            user_id=message.from_user.id,
            action=state_data['action'],
            network=state_data['network'],
            token_address=state_data['token_address'],
            amount=Decimal(state_data['amount']),
            price=Decimal(state_data['price']),
            min_amount=min_amount,
            max_amount=max_amount
        )

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                "📋 Просмотреть объявление",
                callback_data=f"p2p_view_{order['order_id']}"
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "◀️ В меню P2P",
                callback_data="p2p_menu"
            )
        )

        await message.answer(
            "✅ Объявление успешно создано!\n\n"
            f"ID объявления: #{order['order_id']}\n"
            f"Тип: {'Продажа' if state_data['action'] == 'sell' else 'Покупка'}\n"
            f"Сеть: {state_data['network'].upper()}\n"
            f"Количество: {state_data['amount']}\n"
            f"Цена: ${state_data['price']}\n"
            f"Лимиты: ${min_amount} - ${max_amount}",
            reply_markup=keyboard
        )
        await state.finish()

    except ValueError:
        await message.answer("❌ Введите корректное число")
    except Exception as e:
        logger.error(f"Ошибка при создании объявления: {str(e)}")
        await message.answer(
            "❌ Произошла ошибка при создании объявления.\n"
            "Пожалуйста, попробуйте позже."
        )
        await state.finish()

async def show_search_filters(message: types.Message, state: FSMContext):
    """Показывает фильтры поиска объявлений."""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(
            "📈 Купить",
            callback_data="p2p_filter_buy"
        ),
        types.InlineKeyboardButton(
            "📉 Продать",
            callback_data="p2p_filter_sell"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "🌐 Solana",
            callback_data="p2p_filter_solana"
        ),
        types.InlineKeyboardButton(
            "💎 TON",
            callback_data="p2p_filter_ton"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "💰 По цене (мин)",
            callback_data="p2p_filter_price_min"
        ),
        types.InlineKeyboardButton(
            "💰 По цене (макс)",
            callback_data="p2p_filter_price_max"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "⭐️ Только проверенные",
            callback_data="p2p_filter_verified"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "🔍 Поиск",
            callback_data="p2p_search_apply"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "◀️ Назад",
            callback_data="p2p_menu"
        )
    )

    await message.edit_text(
        "🔍 Поиск P2P объявлений\n\n"
        "Настройте фильтры поиска:",
        reply_markup=keyboard
    )

async def show_my_orders(message: types.Message, p2p_service: P2PService):
    """Показывает список объявлений пользователя."""
    try:
        orders = await p2p_service.get_user_orders(message.from_user.id)

        if not orders:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(
                types.InlineKeyboardButton(
                    "📝 Создать объявление",
                    callback_data="p2p_create"
                ),
                types.InlineKeyboardButton(
                    "◀️ Назад",
                    callback_data="p2p_menu"
                )
            )

            await message.edit_text(
                "У вас пока нет объявлений.",
                reply_markup=keyboard
            )
            return

        keyboard = types.InlineKeyboardMarkup()
        for order in orders[:10]:  # Показываем только 10 последних
            status_emoji = {
                'active': "✅",
                'paused': "⏸",
                'cancelled': "❌",
                'completed': "✨"
            }.get(order['status'], "❓")

            keyboard.add(
                types.InlineKeyboardButton(
                    f"{status_emoji} #{order['id']} - {order['amount']} {order['token_symbol']}",
                    callback_data=f"p2p_view_{order['id']}"
                )
            )

        keyboard.add(
            types.InlineKeyboardButton(
                "📝 Создать объявление",
                callback_data="p2p_create"
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "◀️ Назад",
                callback_data="p2p_menu"
            )
        )

        await message.edit_text(
            "📋 Ваши объявления:\n\n"
            "Выберите объявление для просмотра:",
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка при получении списка объявлений: {str(e)}")
        await message.edit_text(
            "❌ Произошла ошибка при получении списка объявлений.\n"
            "Пожалуйста, попробуйте позже."
        )

async def show_my_deals(message: types.Message, p2p_service: P2PService):
    """Показывает список сделок пользователя."""
    try:
        deals = await p2p_service.get_user_deals(message.from_user.id)

        if not deals:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(
                types.InlineKeyboardButton(
                    "🔍 Найти объявления",
                    callback_data="p2p_search"
                ),
                types.InlineKeyboardButton(
                    "◀️ Назад",
                    callback_data="p2p_menu"
                )
            )

            await message.edit_text(
                "У вас пока нет сделок.",
                reply_markup=keyboard
            )
            return

        keyboard = types.InlineKeyboardMarkup()
        for deal in deals[:10]:  # Показываем только 10 последних
            status_emoji = {
                'pending': "⏳",
                'completed': "✅",
                'cancelled': "❌",
                'disputed': "⚠️"
            }.get(deal['status'], "❓")

            keyboard.add(
                types.InlineKeyboardButton(
                    f"{status_emoji} #{deal['id']} - {deal['amount']} {deal['token_symbol']}",
                    callback_data=f"p2p_deal_{deal['id']}"
                )
            )

        keyboard.add(
            types.InlineKeyboardButton(
                "🔍 Найти объявления",
                callback_data="p2p_search"
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "◀️ Назад",
                callback_data="p2p_menu"
            )
        )

        await message.edit_text(
            "💼 Ваши сделки:\n\n"
            "Выберите сделку для просмотра:",
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка при получении списка сделок: {str(e)}")
        await message.edit_text(
            "❌ Произошла ошибка при получении списка сделок.\n"
            "Пожалуйста, попробуйте позже."
        )

async def show_favorite_sellers(message: types.Message, p2p_service: P2PService):
    """Показывает список избранных продавцов."""
    try:
        favorites = await p2p_service.get_favorite_sellers(message.from_user.id)

        if not favorites:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(
                types.InlineKeyboardButton(
                    "🔍 Найти продавцов",
                    callback_data="p2p_search"
                ),
                types.InlineKeyboardButton(
                    "◀️ Назад",
                    callback_data="p2p_menu"
                )
            )

            await message.edit_text(
                "У вас пока нет избранных продавцов.",
                reply_markup=keyboard
            )
            return

        keyboard = types.InlineKeyboardMarkup()
        for seller in favorites:
            keyboard.add(
                types.InlineKeyboardButton(
                    f"⭐️ {seller['username']} - Рейтинг: {seller['rating']:.1f}",
                    callback_data=f"p2p_seller_{seller['user_id']}"
                )
            )

        keyboard.add(
            types.InlineKeyboardButton(
                "🔍 Найти продавцов",
                callback_data="p2p_search"
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "◀️ Назад",
                callback_data="p2p_menu"
            )
        )

        await message.edit_text(
            "⭐️ Избранные продавцы:\n\n"
            "Выберите продавца для просмотра:",
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка при получении списка избранных: {str(e)}")
        await message.edit_text(
            "❌ Произошла ошибка при получении списка избранных продавцов.\n"
            "Пожалуйста, попробуйте позже."
        )

async def show_p2p_stats(message: types.Message, p2p_service: P2PService):
    """Показывает статистику P2P торговли."""
    try:
        stats = await p2p_service.get_user_stats(message.from_user.id)

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                "📊 Подробная статистика",
                callback_data="p2p_stats_detailed"
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "◀️ Назад",
                callback_data="p2p_menu"
            )
        )

        await message.edit_text(
            "📊 Ваша P2P статистика:\n\n"
            f"Всего сделок: {stats['total_deals']}\n"
            f"Успешных сделок: {stats['successful_deals']}\n"
            f"Объем торгов: ${stats['total_volume']:.2f}\n"
            f"Средний объем сделки: ${stats['average_deal_volume']:.2f}\n"
            f"Рейтинг: {stats['rating']:.1f}/5.0\n"
            f"Верификация: {'✅' if stats['is_verified'] else '❌'}\n\n"
            f"Статус: {stats['status']}",
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {str(e)}")
        await message.edit_text(
            "❌ Произошла ошибка при получении статистики.\n"
            "Пожалуйста, попробуйте позже."
        )