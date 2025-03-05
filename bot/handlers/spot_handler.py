from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from services.spot.spot_service import SpotService
from bot.keyboards.spot_keyboards import spot_menu_keyboard, order_type_keyboard, buy_sell_keyboard, back_to_spot_menu_keyboard #  клавиатуры
from core.database.database import Database
from services.wallet.wallet_service import WalletService
from bot.config import config #  config
from bot.keyboards.spot_keyboards import spot_keyboard, choose_token_keyboard, choose_side_keyboard, confirm_keyboard
from core.database.models import User, SpotOrder  #  User and SpotOrder
from typing import Union

# Инициализируем сервисы (предполагаем, что у вас есть db, wallet_service, solana_client, orca, stonfi)
db = Database()
wallet_service = WalletService()
solana_client = None  #  SolanaClient
orca_api = None  #  OrcaAPI
stonfi_api = None  #  StonfiAPI
spot_service = SpotService(db, wallet_service, solana_client, orca_api, stonfi_api)

#  FSM
class SpotOrderStates(StatesGroup):
    waiting_for_token = State()
    waiting_for_side = State()
    waiting_for_quantity = State()
    waiting_for_price = State()  #  цены (для LIMIT)
    confirm_order = State()
    waiting_for_order_id = State() #  ID ордера для отмены

class SpotStates(StatesGroup):
    choosing_base_currency = State()
    choosing_quote_currency = State()
    choosing_order_type = State()
    choosing_side = State()
    entering_quantity = State()
    entering_price = State()  #  для LIMIT ордеров
    confirming_order = State()
    cancelling_order = State()

async def show_spot_menu(message: types.Message):
    """Показывает меню спотовой торговли."""
    await message.answer("Выберите действие:", reply_markup=spot_menu_keyboard)

async def start_create_order(callback_query: types.CallbackQuery, state: FSMContext):
    """Начинает процесс создания ордера."""
    await SpotStates.choosing_base_currency.set()
    await callback_query.message.answer("Введите базовую валюту (например, SOL):")

async def process_base_currency(message: types.Message, state: FSMContext):
    """Обрабатывает ввод базовой валюты."""
    base_currency = message.text.upper()
    await state.update_data(base_currency=base_currency)
    await SpotStates.choosing_quote_currency.set()
    await message.answer("Введите котируемую валюту (например, USDT):")

async def process_quote_currency(message: types.Message, state: FSMContext):
    """Обрабатывает ввод котируемой валюты."""
    quote_currency = message.text.upper()
    await state.update_data(quote_currency=quote_currency)
    await SpotStates.choosing_order_type.set()
    await message.answer("Выберите тип ордера:", reply_markup=order_type_keyboard)

async def process_order_type(callback_query: types.CallbackQuery, state: FSMContext):
    """Обрабатывает выбор типа ордера (MARKET/LIMIT)."""
    order_type = callback_query.data.split("_")[1].upper()  # "market" or "limit"
    await state.update_data(order_type=order_type)
    await SpotStates.choosing_side.set()
    await callback_query.message.answer("Выберите сторону (BUY/SELL):", reply_markup=buy_sell_keyboard)

async def process_side(callback_query: types.CallbackQuery, state: FSMContext):
    """Обрабатывает выбор стороны (BUY/SELL)."""
    side = callback_query.data.split("_")[1].upper()  # "buy" or "sell"
    await state.update_data(side=side)
    await SpotStates.entering_quantity.set()
    await callback_query.message.answer("Введите количество:")

async def process_quantity(message: types.Message, state: FSMContext):
    """Обрабатывает ввод количества."""
    try:
        quantity = float(message.text)
        if quantity <= 0:
            raise ValueError
        await state.update_data(quantity=quantity)

        user_data = await state.get_data()
        if user_data['order_type'] == "LIMIT":
            await SpotStates.entering_price.set()
            await message.answer("Введите цену:")
        else:  # MARKET
            # Сразу переходим к подтверждению
            await SpotStates.confirming_order.set()
            await show_order_confirmation(message, state)

    except ValueError:
        await message.answer("Неверный формат. Пожалуйста, введите положительное число.")

async def process_price(message: types.Message, state: FSMContext):
    """Обрабатывает ввод цены (для LIMIT ордеров)."""
    try:
        price = float(message.text)
        if price <= 0:
            raise ValueError
        await state.update_data(price=price)
        await SpotStates.confirming_order.set()
        await show_order_confirmation(message, state)

    except ValueError:
        await message.answer("Неверный формат. Пожалуйста, введите положительное число.")

async def show_order_confirmation(message: types.Message, state: FSMContext):
    """Показывает подтверждение ордера."""
    user_data = await state.get_data()
    text = (
        f"Подтвердите создание ордера:\n\n"
        f"Базовая валюта: {user_data['base_currency']}\n"
        f"Котируемая валюта: {user_data['quote_currency']}\n"
        f"Тип ордера: {user_data['order_type']}\n"
        f"Сторона: {user_data['side']}\n"
        f"Количество: {user_data['quantity']}\n"
    )
    if user_data['order_type'] == "LIMIT":
        text += f"Цена: {user_data['price']}\n"

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_order"))
    keyboard.add(types.InlineKeyboardButton("❌ Отменить", callback_data="cancel_order"))
    await message.answer(text, reply_markup=keyboard)

async def process_order_confirmation(callback_query: types.CallbackQuery, state: FSMContext):
    """Обрабатывает подтверждение/отмену ордера."""
    if callback_query.data == "confirm_order":
        user_data = await state.get_data()
        if user_data['order_type'] == "LIMIT":
            result = await spot_service.create_limit_order(
                callback_query.from_user.id,
                user_data['base_currency'],
                user_data['quote_currency'],
                user_data['side'],
                user_data['quantity'],
                user_data['price']
            )
        else:  # MARKET
            result = await spot_service.create_market_order(
                callback_query.from_user.id,
                user_data['base_currency'],
                user_data['quote_currency'],
                user_data['side'],
                user_data['quantity']
            )

        if result['success']:
            await callback_query.message.answer(f"✅ Ордер создан! ID: {result['order_id']}")
        else:
            await callback_query.message.answer(f"❌ Ошибка при создании ордера: {result['error']}")
        await state.finish()

    elif callback_query.data == "cancel_order":
        await callback_query.message.answer("❌ Создание ордера отменено.")
        await state.finish()

async def start_cancel_order(callback_query: types.CallbackQuery, state: FSMContext):
    """Начинает процесс отмены ордера."""
    await SpotStates.cancelling_order.set()
    await callback_query.message.answer("Введите ID ордера, который хотите отменить:")

async def process_cancel_order(message: types.Message, state: FSMContext):
    """Обрабатывает ввод ID ордера для отмены."""
    try:
        order_id = int(message.text)
        result = await spot_service.cancel_order(message.from_user.id, order_id)
        if result['success']:
            await message.answer("✅ Ордер отменен.")
        else:
            await message.answer(f"❌ Ошибка при отмене ордера: {result['error']}")
        await state.finish()
    except ValueError:
        await message.answer("Неверный формат ID. Пожалуйста, введите целое число.")

async def show_my_spot_orders(callback_query: types.CallbackQuery):
    """Показывает список открытых ордеров пользователя."""
    orders = await spot_service.get_open_orders(callback_query.from_user.id)
    if not orders:
        await callback_query.message.answer("У вас нет открытых ордеров.", reply_markup=back_to_spot_menu_keyboard)
        return

    text = "Ваши открытые ордера:\n\n"
    for order in orders:
        text += (
            f"ID: {order.id} - {order.side} {order.quantity} {order.base_currency} за {order.price} {order.quote_currency}\n"
            f"Статус: {order.status}\n"
            # Добавьте другую информацию об ордере, если нужно
        )
    await callback_query.message.answer(text, reply_markup=back_to_spot_menu_keyboard)

async def show_spot_order_history(callback_query: types.CallbackQuery):
    """Показывает историю ордеров пользователя."""
    orders = await spot_service.get_order_history(callback_query.from_user.id)
    if not orders:
        await callback_query.message.answer("У вас нет истории ордеров.", reply_markup=back_to_spot_menu_keyboard)
        return

    text = "Ваша история ордеров:\n\n"
    for order in orders:
        text += (
            f"ID: {order.id} - {order.side} {order.quantity} {order.base_currency} за {order.price} {order.quote_currency}\n"
            f"Статус: {order.status}\n"
            # Добавьте другую информацию об ордере, если нужно
        )
    await callback_query.message.answer(text, reply_markup=back_to_spot_menu_keyboard)

async def back_to_spot_menu_handler(callback_query: types.CallbackQuery):
    """Возвращает в главное меню spot."""
    await show_spot_menu(callback_query.message)

async def spot_start(message: types.Message, state: FSMContext):
    """Начало работы со spot."""
    await message.answer("Выберите действие:", reply_markup=spot_keyboard())
    await state.set_state(SpotOrderStates.waiting_for_token.state)

async def choose_token(message: types.Message, state: FSMContext, spot_service: SpotService):
    """Выбор токена."""
    if message.text == "Назад":
        await message.answer("Выберите действие:", reply_markup=spot_keyboard())
        await state.set_state(SpotOrderStates.waiting_for_token.state)
        return

    if message.text not in ["SOL/USDT", "TON/USDT"]:  #  токены
        await message.answer("Неверный токен. Выберите из списка:", reply_markup=choose_token_keyboard())
        return

    await state.update_data(chosen_token=message.text)
    await message.answer("Выберите сторону (BUY/SELL):", reply_markup=choose_side_keyboard())
    await state.set_state(SpotOrderStates.waiting_for_side.state)

async def choose_side(message: types.Message, state: FSMContext, spot_service: SpotService):
    """Выбор стороны (BUY/SELL)."""
    if message.text == "Назад":
        await message.answer("Выберите токен:", reply_markup=choose_token_keyboard())
        await state.set_state(SpotOrderStates.waiting_for_token.state)
        return

    if message.text not in ["BUY", "SELL"]:
        await message.answer("Неверная сторона. Выберите BUY или SELL:", reply_markup=choose_side_keyboard())
        return

    await state.update_data(chosen_side=message.text)
    await message.answer("Введите количество:")
    await state.set_state(SpotOrderStates.waiting_for_quantity.state)

async def enter_quantity(message: types.Message, state: FSMContext, spot_service: SpotService):
    """Ввод количества."""
    if message.text == "Назад":
        await message.answer("Выберите сторону (BUY/SELL):", reply_markup=choose_side_keyboard())
        await state.set_state(SpotOrderStates.waiting_for_side.state)
        return
    try:
        quantity = float(message.text)
        if quantity <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Неверное количество. Введите положительное число.")
        return

    await state.update_data(quantity=quantity)
    await message.answer("Введите цену (или 'рынок' для MARKET ордера):")  #  цена
    await state.set_state(SpotOrderStates.waiting_for_price.state)

async def enter_price(message: types.Message, state: FSMContext, spot_service: SpotService):
    """Ввод цены (или 'рынок' для MARKET ордера)."""
    if message.text == "Назад":
        await message.answer("Введите количество:")
        await state.set_state(SpotOrderStates.waiting_for_quantity.state)
        return

    if message.text.lower() == "рынок":
        price = None  #  MARKET ордер
    else:
        try:
            price = float(message.text)
            if price <= 0:
                raise ValueError
        except ValueError:
            await message.answer("Неверная цена. Введите положительное число или 'рынок'.")
            return

    await state.update_data(price=price)

    user_data = await state.get_data()
    token = user_data['chosen_token']
    side = user_data['chosen_side']
    quantity = user_data['quantity']

    if price is None:
        confirm_text = (f"Подтвердите создание MARKET ордера:\n"
                       f"Токен: {token}\n"
                       f"Сторона: {side}\n"
                       f"Количество: {quantity}\n")
    else:
        confirm_text = (f"Подтвердите создание LIMIT ордера:\n"
                       f"Токен: {token}\n"
                       f"Сторона: {side}\n"
                       f"Количество: {quantity}\n"
                       f"Цена: {price}\n")

    await message.answer(confirm_text, reply_markup=confirm_keyboard())
    await state.set_state(SpotOrderStates.confirm_order.state)

async def confirm_order(message: types.Message, state: FSMContext, spot_service: SpotService):
    """Подтверждение ордера."""
    if message.text == "Назад":
        await message.answer("Введите цену (или 'рынок' для MARKET ордера):")
        await state.set_state(SpotOrderStates.waiting_for_price.state)
        return

    if message.text != "Подтвердить":
        await message.answer("Неверный ввод. Нажмите 'Подтвердить' или 'Назад'.", reply_markup=confirm_keyboard())
        return

    user_data = await state.get_data()
    token = user_data['chosen_token']
    side = user_data['chosen_side']
    quantity = user_data['quantity']
    price = user_data['price']

    base_currency, quote_currency = token.split("/")  #  "SOL/USDT" -> "SOL", "USDT"

    if price is None:  #  MARKET
        result = await spot_service.create_market_order(
            user_id=message.from_user.id,
            base_currency=base_currency,
            quote_currency=quote_currency,
            side=side,
            quantity=quantity
        )
    else:  #  LIMIT
        result = await spot_service.create_limit_order(
            user_id=message.from_user.id,
            base_currency=base_currency,
            quote_currency=quote_currency,
            side=side,
            quantity=quantity,
            price=price
        )

    if result['success']:
        await message.answer("Ордер создан!")
    else:
        await message.answer(f"Ошибка при создании ордера: {result['error']}")

    await state.finish()

async def cancel_spot_order_start(message: types.Message, state: FSMContext, spot_service: SpotService):
    """Начало процесса отмены ордера."""
    # Получаем список открытых ордеров пользователя
    open_orders = await spot_service.get_open_orders(message.from_user.id)

    if not open_orders:
        await message.answer("У вас нет открытых ордеров для отмены.", reply_markup=back_to_spot_menu_keyboard)
        await state.finish()
        return

    # Формируем сообщение со списком ордеров
    orders_message = "Выберите ордер для отмены:\n\n"
    for order in open_orders:
        orders_message += (
            f"ID: {order.id} - {order.side} {order.quantity} {order.base_currency} за {order.price} {order.quote_currency}\n"
        )

    await message.answer(orders_message)
    await message.answer("Введите ID ордера, который хотите отменить:")
    await state.set_state(SpotOrderStates.waiting_for_order_id.state)

async def cancel_spot_order_confirm(message: types.Message, state: FSMContext, spot_service: SpotService):
    """Ввод и обработка ID ордера для отмены."""
    try:
        order_id = int(message.text)
    except ValueError:
        await message.answer("Неверный ID ордера. Пожалуйста, введите число.")
        return

    result = await spot_service.cancel_order(message.from_user.id, order_id)
    if result['success']:
        await message.answer("Ордер успешно отменен.")
    else:
        await message.answer(f"Ошибка при отмене ордера: {result['error']}")

    await state.finish()

def register_spot_handlers(dp: Dispatcher):
    dp.register_message_handler(show_spot_menu, commands=['spot'])
    dp.register_callback_query_handler(start_create_order, lambda c: c.data == "create_spot_order")
    dp.register_message_handler(process_base_currency, state=SpotStates.choosing_base_currency)
    dp.register_message_handler(process_quote_currency, state=SpotStates.choosing_quote_currency)
    dp.register_callback_query_handler(process_order_type, state=SpotStates.choosing_order_type)
    dp.register_callback_query_handler(process_side, state=SpotStates.choosing_side)
    dp.register_message_handler(process_quantity, state=SpotStates.entering_quantity)
    dp.register_message_handler(process_price, state=SpotStates.entering_price)
    dp.register_callback_query_handler(process_order_confirmation, state=SpotStates.confirming_order)
    dp.register_callback_query_handler(start_cancel_order, lambda c: c.data == "cancel_spot_order")
    dp.register_message_handler(process_cancel_order, state=SpotStates.cancelling_order)
    dp.register_callback_query_handler(show_my_spot_orders, lambda c: c.data == "my_spot_orders")
    dp.register_callback_query_handler(show_spot_order_history, lambda c: c.data == "spot_order_history")
    dp.register_callback_query_handler(back_to_spot_menu_handler, lambda c: c.data == "back_to_spot_menu")
    dp.register_message_handler(spot_start, commands="spot", state="*")
    dp.register_message_handler(lambda msg: msg.text.lower() == "спот", state="*")
    dp.register_message_handler(choose_token, state=SpotOrderStates.waiting_for_token)
    dp.register_message_handler(choose_side, state=SpotOrderStates.waiting_for_side)
    dp.register_message_handler(enter_quantity, state=SpotOrderStates.waiting_for_quantity)
    dp.register_message_handler(enter_price, state=SpotOrderStates.waiting_for_price)  #  цены
    dp.register_message_handler(confirm_order, state=SpotOrderStates.confirm_order)
    dp.register_message_handler(cancel_spot_order_start, lambda msg: msg.text.lower() == "отменить ордер", state="*")  #  отмены
    dp.register_message_handler(cancel_spot_order_confirm, state=SpotOrderStates.waiting_for_order_id)  #  ID
    dp.register_message_handler(show_my_spot_orders, lambda msg: msg.text.lower() == "мои ордера", state="*")
    dp.register_message_handler(show_spot_order_history, lambda msg: msg.text.lower() == "история ордеров", state="*")
    dp.register_message_handler(back_to_spot_menu_handler, lambda msg: msg.text.lower() == "назад", state="*") 