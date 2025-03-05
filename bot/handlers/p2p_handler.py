from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from services.p2p.p2p_service import P2PService
from bot.keyboards.p2p_keyboards import (
    p2p_menu_keyboard, p2p_side_keyboard, p2p_payment_method_keyboard,
    confirm_keyboard, back_to_p2p_menu_keyboard, p2p_order_keyboard,
    confirm_payment_keyboard, dispute_keyboard, leave_review_keyboard
)
from core.database.database import Database
from services.wallet.wallet_service import WalletService
from services.notifications.notification_service import NotificationService
from core.database.models import P2PPaymentMethod, P2POrderStatus
from datetime import datetime
from services.rating.rating_service import RatingService

# Инициализируем сервисы (предполагаем, что у вас есть db, wallet_service, notification_service)
db = Database()
wallet_service = WalletService()  #  WalletService
notification_service = NotificationService(bot)  #  NotificationService, bot
p2p_service = P2PService(db, wallet_service)
rating_service = RatingService(db) #  RatingService

class P2POrderStates(StatesGroup):
    waiting_for_side = State()
    waiting_for_base_currency = State()
    waiting_for_quote_currency = State()
    waiting_for_amount = State()
    waiting_for_price = State()
    waiting_for_payment_method = State()
    confirm_order = State()
    waiting_for_order_id = State() #  ID ордера
    confirming_payment = State() #  оплаты
    opening_dispute = State()
    resolving_dispute = State()
    leaving_review = State() #  отзыва
    waiting_for_rating = State() #  оценки
    waiting_for_review_comment = State() #  комментария

async def p2p_start(message: types.Message, state: FSMContext):
    """Начало работы с P2P."""
    await message.answer("Выберите действие:", reply_markup=p2p_menu_keyboard())
    await state.finish()

async def create_p2p_order_start(message: types.Message, state: FSMContext):
    """Начало создания P2P ордера."""
    await message.answer("Вы хотите купить или продать?", reply_markup=p2p_side_keyboard())
    await P2POrderStates.waiting_for_side.set()

async def choose_p2p_side(message: types.Message, state: FSMContext, p2p_service: P2PService):
    """Выбор стороны (BUY/SELL)."""
    if message.text.upper() not in ["BUY", "SELL"]:
        await message.answer("Неверный выбор. Пожалуйста, выберите 'BUY' или 'SELL'.", reply_markup=p2p_side_keyboard())
        return

    await state.update_data(side=message.text.upper())
    await message.answer("Введите базовую валюту (например, TON):")
    await P2POrderStates.waiting_for_base_currency.set()

async def enter_base_currency(message: types.Message, state: FSMContext, p2p_service: P2PService):
    await state.update_data(base_currency=message.text.upper())
    await message.answer("Введите котируемую валюту (например, USDT):")
    await P2POrderStates.waiting_for_quote_currency.set()

async def enter_quote_currency(message: types.Message, state: FSMContext, p2p_service: P2PService):
    await state.update_data(quote_currency=message.text.upper())
    await message.answer("Введите количество базовой валюты:")
    await P2POrderStates.waiting_for_amount.set()

async def enter_amount(message: types.Message, state: FSMContext, p2p_service: P2PService):
    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError
        await state.update_data(amount=amount)
        await message.answer("Введите цену за единицу базовой валюты:")
        await P2POrderStates.waiting_for_price.set()
    except ValueError:
        await message.answer("Неверное количество. Введите положительное число.")

async def enter_price(message: types.Message, state: FSMContext, p2p_service: P2PService):
    try:
        price = float(message.text)
        if price <= 0:
            raise ValueError
        await state.update_data(price=price)
        await message.answer("Выберите способ оплаты:", reply_markup=p2p_payment_method_keyboard())
        await P2POrderStates.waiting_for_payment_method.set()

    except ValueError:
        await message.answer("Неверная цена. Введите положительное число.")

async def choose_payment_method(message: types.Message, state: FSMContext, p2p_service: P2PService):
    if message.text not in [pm.name for pm in P2PPaymentMethod]:
        await message.answer("Неверный способ оплаты. Выберите из списка:", reply_markup=p2p_payment_method_keyboard())
        return
    await state.update_data(payment_method=message.text)
    user_data = await state.get_data()
    text = f"""Подтвердите создание P2P ордера:
Сторона: {user_data['side']}
Базовая валюта: {user_data['base_currency']}
Котируемая валюта: {user_data['quote_currency']}
Количество: {user_data['amount']}
Цена: {user_data['price']}
Способ оплаты: {user_data['payment_method']}"""
    await message.answer(text, reply_markup=confirm_keyboard())
    await P2POrderStates.confirm_order.set()

async def confirm_p2p_order(message: types.Message, state: FSMContext, p2p_service: P2PService):
    if message.text.lower() != "подтвердить":
        await message.answer("Пожалуйста, нажмите 'Подтвердить' или 'Отмена'.", reply_markup=confirm_keyboard())
        return

    user_data = await state.get_data()
    result = await p2p_service.create_order(
        user_id=message.from_user.id,
        side=user_data['side'],
        base_currency=user_data['base_currency'],
        quote_currency=user_data['quote_currency'],
        amount=user_data['amount'],
        price=user_data['price'],
        payment_method=user_data['payment_method']
    )

    if result['success']:
        await message.answer(f"P2P ордер создан! ID: {result['order_id']}")
    else:
        await message.answer(f"Ошибка при создании P2P ордера: {result['error']}")
    await state.finish()

async def cancel_p2p_order_start(message: types.Message, state: FSMContext, p2p_service: P2PService):
    """Начало процесса отмены P2P ордера."""
    open_orders = await p2p_service.get_user_p2p_orders(message.from_user.id, status="OPEN")

    if not open_orders:
        await message.answer("У вас нет открытых P2P ордеров.", reply_markup=back_to_p2p_menu_keyboard)
        await state.finish()
        return

    orders_message = "Ваши открытые P2P ордера:\n\n"
    for order in open_orders:
        orders_message += (
            f"ID: {order.id} - {order.side} {order.amount} {order.base_currency} за {order.price} {order.quote_currency}\n"
        )

    await message.answer(orders_message)
    await message.answer("Введите ID ордера, который хотите отменить:")
    await P2POrderStates.waiting_for_order_id.set()

async def cancel_p2p_order_confirm(message: types.Message, state: FSMContext, p2p_service: P2PService):
    try:
        order_id = int(message.text)
    except ValueError:
        await message.answer("Неверный ID ордера. Пожалуйста, введите число.")
        return

    result = await p2p_service.cancel_order(order_id, message.from_user.id)
    if result['success']:
        await message.answer("P2P ордер успешно отменен.")
    else:
        await message.answer(f"Ошибка при отмене P2P ордера: {result['error']}")

    await state.finish()

async def list_p2p_orders(message: types.Message, state: FSMContext, p2p_service: P2PService):
    """Показывает список открытых P2P ордеров."""
    orders = await p2p_service.get_open_orders()
    if not orders:
        await message.answer("Нет открытых P2P ордеров.", reply_markup=back_to_p2p_menu_keyboard)
        return

    orders_message = "Открытые P2P ордера:\n\n"
    for order in orders:
        #  информацию об ордере,  имя пользователя
        user = await message.bot.get_chat(order.user_id)  #  aiogram
        username = user.username if user.username else "Неизвестный пользователь"

        #  P2P ордера,  премиум
        if order.user.hide_p2p_orders and not (await is_premium(message)):
            continue

        orders_message += (
            f"ID: {order.id} - {order.side} {order.amount} {order.base_currency} за {order.price} {order.quote_currency} "
            f"({order.payment_method.value})\n"
            f"Пользователь: @{username}\n"
        )
        #  Inline клавиатуру
        keyboard = p2p_order_keyboard(order.id, order_status=order.status.value)
        await message.answer(orders_message, reply_markup=keyboard)
        orders_message = "" #  следующего ордера

    if orders_message != "":
      await message.answer(orders_message) #  ""

async def my_p2p_orders(message: types.Message, state: FSMContext, p2p_service: P2PService):
    """Показывает P2P ордера пользователя (созданные и принятые)."""
    created_orders = await p2p_service.get_user_p2p_orders(message.from_user.id)
    taken_orders = await p2p_service.get_user_taken_p2p_orders(message.from_user.id)

    if not created_orders and not taken_orders:
        await message.answer("У вас нет P2P ордеров.", reply_markup=back_to_p2p_menu_keyboard)
        return

    response_text = "Ваши P2P ордера:\n\n"
    if created_orders:
        response_text += "Созданные вами ордера:\n"
        for order in created_orders:
            #  Inline клавиатуру
            keyboard = p2p_order_keyboard(order.id, is_owner=True, order_status=order.status.value)
            response_text += (
                f"ID: {order.id} - {order.side} {order.amount} {order.base_currency} за {order.price} {order.quote_currency} "
                f"({order.payment_method.value}) - Статус: {order.status.value}\n"
            )
            await message.answer(response_text, reply_markup=keyboard)
            response_text = ""

    if taken_orders:
        response_text += "\nПринятые вами ордера:\n"
        for order in taken_orders:
            response_text += (
                f"ID: {order.id} - {order.side} {order.amount} {order.base_currency} за {order.price} {order.quote_currency} "
                f"({order.payment_method.value}) - Статус: {order.status.value}\n"
            )
            #  Inline клавиатуру (без кнопки отмены)
            keyboard = p2p_order_keyboard(order.id, order_status=order.status.value)
            await message.answer(response_text, reply_markup=keyboard)
            response_text = ""

    if response_text != "":
        await message.answer(response_text)

async def back_to_p2p_menu_handler(message: types.Message, state: FSMContext, p2p_service: P2PService):
    """Возвращает пользователя в главное меню P2P."""
    await message.answer("Выберите действие:", reply_markup=p2p_menu_keyboard())
    await state.finish()

async def take_p2p_order_handler(callback_query: types.CallbackQuery, state: FSMContext, p2p_service: P2PService):
    order_id = int(callback_query.data.split("_")[2]) #  callback data
    result = await p2p_service.take_order(order_id, callback_query.from_user.id)
    if result['success']:
        await callback_query.message.answer("Вы приняли ордер!")
        #  уведомление  создателю ордера
        order = await p2p_service.get_order_by_id(order_id)
        if order:
            await callback_query.message.bot.send_message(
                order.user_id,
                f"Ваш P2P ордер #{order_id} был принят пользователем @{callback_query.from_user.username}!"
            )
    else:
        await callback_query.message.answer(f"Ошибка: {result['error']}")
    await callback_query.answer()  #  уведомление

async def cancel_p2p_order_handler(callback_query: types.CallbackQuery, state: FSMContext, p2p_service: P2PService):
    order_id = int(callback_query.data.split("_")[2])
    result = await p2p_service.cancel_order(order_id, callback_query.from_user.id)
    if result['success']:
        await callback_query.message.answer("Ордер отменен.")
        #  уведомление второму участнику,  он есть
        order = await p2p_service.get_order_by_id(order_id)
        if order and order.taker_id:
            await callback_query.message.bot.send_message(
                order.taker_id,
                f"P2P ордер #{order_id} был отменен пользователем @{callback_query.from_user.username}."
            )
    else:
        await callback_query.message.answer(f"Ошибка: {result['error']}")
    await callback_query.answer()

async def is_premium(message: types.Message) -> bool:
    """Проверяет, является ли пользователь премиум-пользователем."""
    session = Database().get_session()  #  сессию
    user = session.query(User).filter(User.telegram_id == message.from_user.id).first()
    session.close()
    if user and user.is_premium and user.premium_expires_at and user.premium_expires_at > datetime.utcnow():
        return True
    return False

async def confirm_payment_handler(callback_query: types.CallbackQuery, state: FSMContext, p2p_service: P2PService):
    """Обработчик подтверждения получения оплаты."""
    order_id = int(callback_query.data.split("_")[2])
    order = await p2p_service.get_order_by_id(order_id)

    if not order:
        await callback_query.message.answer("Ордер не найден.")
        await callback_query.answer()
        return

    #  -  ,   -  
    if callback_query.from_user.id != order.user_id:
         await callback_query.message.answer("Вы не можете подтвердить оплату для этого ордера.")
         await callback_query.answer()
         return

    if order.status != P2POrderStatus.IN_PROGRESS:
        await callback_query.message.answer("Неверный статус ордера.")
        await callback_query.answer()
        return

    result = await p2p_service.complete_order(order_id, callback_query.from_user.id)
    if result['success']:
        await callback_query.message.answer("Оплата подтверждена. Ордер завершен.")
        #  уведомление второму участнику
        if order.taker_id:
            await callback_query.message.bot.send_message(
                order.taker_id,
                f"Пользователь @{callback_query.from_user.username} подтвердил получение оплаты по ордеру #{order_id}."
            )
        #  оставить отзыв
        keyboard = leave_review_keyboard(order_id)
        await callback_query.message.bot.send_message(
            order.taker_id,
            f"Пожалуйста, оставьте отзыв о пользователе @{callback_query.message.bot.get_chat(order.taker_id).username}:",
            reply_markup=keyboard
        )
        await callback_query.message.bot.send_message( #  второму
            order.user_id,
            f"Пожалуйста, оставьте отзыв о пользователе @{callback_query.message.bot.get_chat(order.taker_id).username}:",
            reply_markup=keyboard
        )

    else:
        await callback_query.message.answer(f"Ошибка: {result['error']}")

    await callback_query.answer()

async def open_dispute_handler(callback_query: types.CallbackQuery, state: FSMContext, p2p_service: P2PService):
    order_id = int(callback_query.data.split("_")[2])
    order = await p2p_service.get_order_by_id(order_id)

    if not order:
        await callback_query.message.answer("Ордер не найден.")
        await callback_query.answer()
        return

    if callback_query.from_user.id != order.user_id and callback_query.from_user.id != order.taker_id:
        await callback_query.message.answer("Вы не можете открыть диспут по этому ордеру.")
        await callback_query.answer()
        return

    if order.status != P2POrderStatus.IN_PROGRESS:
        await callback_query.message.answer("Неверный статус ордера.")
        await callback_query.answer()
        return

    result = await p2p_service.open_dispute(order_id, callback_query.from_user.id)
    if result['success']:
        await callback_query.message.answer("Диспут открыт. Ожидайте решения администрации.")
    else:
        await callback_query.message.answer(f"Ошибка: {result['error']}")

    await callback_query.answer()

async def resolve_dispute_handler(message: types.Message, state: FSMContext, p2p_service: P2PService):
    session = Database().get_session()
    user = session.query(User).filter(User.telegram_id == message.from_user.id).first()
    if not user or not user.is_admin:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    await message.answer("Введите ID ордера, по которому нужно разрешить диспут:")
    await P2POrderStates.resolving_dispute.set()
    await state.update_data(admin_id=message.from_user.id)

async def process_dispute_resolution(message: types.Message, state: FSMContext, p2p_service: P2PService):
    try:
        order_id = int(message.text)
    except ValueError:
        await message.answer("Неверный ID ордера. Пожалуйста, введите число.")
        return

    order = await p2p_service.get_order_by_id(order_id)
    if not order:
        await message.answer("Ордер не найден.")
        await state.finish()
        return

    if order.status != P2POrderStatus.DISPUTE:
        await message.answer("Неверный статус ордера.")
        await state.finish()
        return

    admin_data = await state.get_data()
    admin_id = admin_data['admin_id']

    keyboard = dispute_keyboard(order_id)
    await message.answer(f"Выберите решение для ордера #{order_id}:", reply_markup=keyboard)

async def handle_dispute_decision(callback_query: types.CallbackQuery, state: FSMContext, p2p_service: P2PService):
    data = callback_query.data.split("_")
    order_id = int(data[2])
    decision = data[3]

    admin_data = await state.get_data()
    admin_id = admin_data['admin_id']

    result = await p2p_service.resolve_dispute(order_id, admin_id, decision)

    if result['success']:
        await callback_query.message.answer(f"Диспут по ордеру #{order_id} разрешен.")
    else:
        await callback_query.message.answer(f"Ошибка: {result['error']}")

    await state.finish()
    await callback_query.answer()

async def leave_review_handler(callback_query: types.CallbackQuery, state: FSMContext, rating_service: RatingService):
    """Начало процесса оставления отзыва."""
    order_id = int(callback_query.data.split("_")[2])
    await state.update_data(order_id=order_id)
    await P2POrderStates.waiting_for_rating.set()
    await callback_query.message.answer("Пожалуйста, оцените сделку по шкале от 1 до 5:")
    await callback_query.answer()

async def process_rating(message: types.Message, state: FSMContext, rating_service: RatingService):
    """Обрабатывает оценку пользователя."""   
    try:
        rating = int(message.text)
        if not 1 <= rating <= 5:
            raise ValueError
        await state.update_data(rating=rating)
        await P2POrderStates.waiting_for_review_comment.set()
        await message.answer("Хотите оставить комментарий к отзыву? (необязательно)")

    except ValueError:
        await message.answer("Пожалуйста, введите число от 1 до 5.")

async def process_review_comment(message: types.Message, state: FSMContext, rating_service: RatingService, p2p_service: P2PService):
    """Обрабатывает комментарий к отзыву и сохраняет отзыв."""
    comment = message.text if message.text else None
    user_data = await state.get_data()
    order_id = user_data.get('order_id')
    rating = user_data.get('rating')

    order = await p2p_service.get_order_by_id(order_id)
    if not order:
        await message.answer("Ордер не найден.")
        await state.finish()
        return

    #  ,   
    reviewer_id = message.from_user.id
    if reviewer_id == order.user_id:
        reviewee_id = order.taker_id
    elif reviewer_id == order.taker_id:
        reviewee_id = order.user_id
    else:
        await message.answer("Вы не можете оставить отзыв по этому ордеру.")
        await state.finish()
        return

    result = await rating_service.add_review(reviewer_id, reviewee_id, order_id, rating, comment)

    if result['success']:
        await message.answer("Спасибо за ваш отзыв!")
    else:
        await message.answer(f"Ошибка при добавлении отзыва: {result['error']}")

    await state.finish()

async def show_user_rating_handler(message: types.Message, state: FSMContext, rating_service: RatingService):
    """Показывает рейтинг пользователя."""
    #  ID  из аргумента команды  /rating 123
    try:
        user_id = int(message.text.split()[1]) #  аргумент
    except (IndexError, ValueError):
        user_id = message.from_user.id #  ID

    rating = await rating_service.get_user_rating(user_id)

    if rating is not None:
        await message.answer(f"Рейтинг пользователя: {rating:.2f}") #  2  
    else:
        await message.answer("Пользователь не найден или у него еще нет рейтинга.")

def register_handlers_p2p(dp: Dispatcher, p2p_service: P2PService, rating_service: RatingService):
    dp.register_message_handler(p2p_start, commands="p2p", state="*")
    dp.register_message_handler(lambda msg: msg.text.lower() == "p2p", state="*")
    dp.register_message_handler(create_p2p_order_start, lambda msg: msg.text.lower() == "создать p2p ордер", state="*")
    dp.register_message_handler(choose_p2p_side, state=P2POrderStates.waiting_for_side)
    dp.register_message_handler(enter_base_currency, state=P2POrderStates.waiting_for_base_currency)
    dp.register_message_handler(enter_quote_currency, state=P2POrderStates.waiting_for_quote_currency)
    dp.register_message_handler(enter_amount, state=P2POrderStates.waiting_for_amount)
    dp.register_message_handler(enter_price, state=P2POrderStates.waiting_for_price)
    dp.register_message_handler(choose_payment_method, state=P2POrderStates.waiting_for_payment_method)
    dp.register_message_handler(confirm_p2p_order, state=P2POrderStates.confirm_order)
    dp.register_message_handler(cancel_p2p_order_start, lambda msg: msg.text.lower() == "отменить p2p ордер", state="*")  #  отмены
    dp.register_message_handler(cancel_p2p_order_confirm, state=P2POrderStates.waiting_for_order_id)  #  ID
    dp.register_message_handler(list_p2p_orders, lambda msg: msg.text.lower() == "список p2p ордеров", state="*")
    dp.register_message_handler(my_p2p_orders, lambda msg: msg.text.lower() == "мои p2p ордера", state="*")
    dp.register_message_handler(back_to_p2p_menu_handler, lambda msg: msg.text.lower() == "назад в p2p меню", state="*")
    dp.register_message_handler(back_to_p2p_menu_handler, lambda msg: msg.text.lower() == "назад", state="*") #  назад
    dp.register_callback_query_handler(take_p2p_order_handler, lambda c: c.data and c.data.startswith("p2p_take_"))
    dp.register_callback_query_handler(cancel_p2p_order_handler, lambda c: c.data and c.data.startswith("p2p_cancel_"))
    dp.register_callback_query_handler(confirm_payment_handler, lambda c: c.data and c.data.startswith("p2p_confirm_payment_"))
    dp.register_callback_query_handler(open_dispute_handler, lambda c: c.data and c.data.startswith("p2p_open_dispute_"))
    dp.register_message_handler(resolve_dispute_handler, commands=["resolve_dispute"], state="*")
    dp.register_message_handler(process_dispute_resolution, state=P2POrderStates.resolving_dispute)
    dp.register_callback_query_handler(handle_dispute_decision, lambda c: c.data and c.data.startswith("p2p_dispute_decision_"), state="*")
    dp.register_callback_query_handler(leave_review_handler, lambda c: c.data and c.data.startswith("p2p_leave_review_")) #  отзыва
    dp.register_message_handler(process_rating, state=P2POrderStates.waiting_for_rating) #  оценки
    dp.register_message_handler(process_review_comment, state=P2POrderStates.waiting_for_review_comment) #  комментария
    dp.register_message_handler(show_user_rating_handler, commands=["rating"], state="*") #  /rating 