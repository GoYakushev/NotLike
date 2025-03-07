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
import logging
from services.dex.dex_service import DEXService
from services.notifications.notification_service import NotificationService
from decimal import Decimal

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
    waiting_for_price = State() 
    confirm_order = State()
    waiting_for_order_id = State()

class SpotStates(StatesGroup):
    choosing_network = State()
    choosing_token = State()
    entering_amount = State()
    confirming_swap = State()

def _create_spot_menu_keyboard(): #  Приватная функция для создания клавиатуры
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("🌐 Solana", callback_data="spot_network_solana"),
        types.InlineKeyboardButton("💎 TON", callback_data="spot_network_ton")
    )
    keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="main_menu"))
    
    return keyboard

async def show_spot_menu(message: types.Message):
    """Показывает главное меню спот-торговли."""
    keyboard = _create_spot_menu_keyboard()
    await message.answer(
        "🔄 Выберите сеть для торговли:",
        reply_markup=keyboard
    )

async def process_network_selection(callback_query: types.CallbackQuery, state: FSMContext):
    """Обрабатывает выбор сети."""
    try:
        await callback_query.answer()
        network = callback_query.data.split('_')[2]
        
        await state.update_data(network=network)
        await SpotStates.choosing_token.set()
        
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
        
        # Добавляем популярные токены
        for token_name, token_address in popular_tokens:
            keyboard.add(
                types.InlineKeyboardButton(
                    f"{token_name}", 
                    callback_data=f"spot_token_{token_address}"
                )
            )
        
        # Добавляем кнопку для ввода произвольного адреса
        keyboard.add(
            types.InlineKeyboardButton("🔍 Поиск по адресу", callback_data="spot_search")
        )
        keyboard.add(
            types.InlineKeyboardButton("◀️ Назад", callback_data="spot")
        )
        
        await callback_query.message.edit_text(
            "💱 Выберите токен для покупки или введите его адрес:",
            reply_markup=keyboard
        )
    except Exception as e:
        logging.error(f"Ошибка при выборе сети: {str(e)}")
        await callback_query.message.answer("❌ Произошла ошибка. Попробуйте позже.")

async def process_token_selection(callback_query: types.CallbackQuery, state: FSMContext):
    """Обрабатывает выбор токена."""
    try:
        await callback_query.answer()
        
        if callback_query.data == "spot_search":
            await callback_query.message.edit_text(
                "📝 Введите адрес токена:"
            )
            return
            
        token_address = callback_query.data.split('_')[2]
        await process_token_address(callback_query.message, token_address, state)
    except Exception as e:
        logging.error(f"Ошибка при выборе токена: {str(e)}")
        await callback_query.message.answer("❌ Произошла ошибка. Попробуйте позже.")

async def process_token_address(message: types.Message, token_address: str, state: FSMContext):
    """Обрабатывает введенный адрес токена."""
    try:
        state_data = await state.get_data()
        network = state_data.get('network')
        
        dex_service = DEXService()
        token_info = await dex_service.get_token_info(network, token_address)
        
        await state.update_data(
            token_address=token_address,
            token_symbol=token_info['symbol'],
            token_decimals=token_info['decimals']
        )
        
        # Получаем текущую цену токена
        price_info = await dex_service.get_best_price(
            network,
            token_address,
            'USDT' if network == 'solana' else 'ton-usdt-address',
            Decimal('1')
        )
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton("◀️ Назад", callback_data=f"spot_network_{network}"),
            types.InlineKeyboardButton("✅ Продолжить", callback_data="spot_continue")
        )
        
        await message.answer(
            f"📊 Информация о токене:\n\n"
            f"Название: {token_info['name']}\n"
            f"Символ: {token_info['symbol']}\n"
            f"Сеть: {network.upper()}\n"
            f"Текущая цена: ${price_info['output_amount']:.4f}\n\n"
            f"Введите количество {token_info['symbol']}, которое хотите купить:",
            reply_markup=keyboard
        )
        
        await SpotStates.entering_amount.set()
    except Exception as e:
        logging.error(f"Ошибка при обработке адреса токена: {str(e)}")
        await message.answer(
            "❌ Не удалось получить информацию о токене. Проверьте адрес и попробуйте снова."
        )

async def process_amount(message: types.Message, state: FSMContext):
    """Обрабатывает введенное количество токенов."""
    try:
        amount = Decimal(message.text)
        if amount <= 0:
            await message.answer("❌ Количество должно быть больше 0")
            return
            
        state_data = await state.get_data()
        network = state_data['network']
        token_address = state_data['token_address']
        token_symbol = state_data['token_symbol']
        
        dex_service = DEXService()
        wallet_service = WalletService()
        
        # Получаем лучшую цену
        price_info = await dex_service.get_best_price(
            network,
            token_address,
            'USDT' if network == 'solana' else 'ton-usdt-address',
            amount
        )
        
        # Проверяем баланс
        balance = await wallet_service.get_balance(message.from_user.id, network)
        if Decimal(price_info['input_amount']) > balance:
            await message.answer(
                f"❌ Недостаточно средств. Необходимо: {price_info['input_amount']} {network.upper()}\n"
                f"Доступно: {balance} {network.upper()}"
            )
            return
            
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton("✅ Подтвердить", callback_data="spot_confirm"),
            types.InlineKeyboardButton("❌ Отменить", callback_data="spot")
        )
        
        await state.update_data(
            amount=str(amount),
            price_info=price_info
        )
        
        await message.answer(
            f"📝 Проверьте детали свопа:\n\n"
            f"Покупка: {amount} {token_symbol}\n"
            f"Цена: ${price_info['output_amount']:.4f}\n"
            f"DEX: {price_info['dex']}\n"
            f"Сеть: {network.upper()}\n\n"
            f"Подтвердите операцию:",
            reply_markup=keyboard
        )
        
        await SpotStates.confirming_swap.set()
    except ValueError:
        await message.answer("❌ Введите корректное число")
    except Exception as e:
        logging.error(f"Ошибка при обработке количества: {str(e)}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")

async def execute_swap(callback_query: types.CallbackQuery, state: FSMContext):
    """Выполняет своп."""
    try:
        await callback_query.answer()
        
        state_data = await state.get_data()
        network = state_data['network']
        token_address = state_data['token_address']
        amount = Decimal(state_data['amount'])
        
        dex_service = DEXService()
        notification_service = NotificationService()
        
        # Выполняем своп
        swap_result = await dex_service.execute_swap(
            network,
            token_address,
            'USDT' if network == 'solana' else 'ton-usdt-address',
            amount
        )
        
        # Отправляем уведомление
        await notification_service.send_trade_notification(
            user_id=callback_query.from_user.id,
            trade_type="buy",
            amount=amount,
            token_symbol=state_data['token_symbol'],
            price=swap_result['output_amount'],
            tx_hash=swap_result['transaction_hash']
        )
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton("🔄 Новый своп", callback_data="spot"),
            types.InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")
        )
        
        await callback_query.message.edit_text(
            f"✅ Своп успешно выполнен!\n\n"
            f"Куплено: {amount} {state_data['token_symbol']}\n"
            f"Цена: ${swap_result['output_amount']:.4f}\n"
            f"DEX: {swap_result['dex_used']}\n"
            f"Хэш транзакции: {swap_result['transaction_hash']}\n\n"
            f"Ваши токены скоро появятся в кошельке.",
            reply_markup=keyboard
        )
        
        await state.finish()
    except Exception as e:
        logging.error(f"Ошибка при выполнении свопа: {str(e)}")
        await callback_query.message.edit_text(
            "❌ Произошла ошибка при выполнении свопа. Попробуйте позже."
        )
        await state.finish()

def register_spot_handlers(dp: Dispatcher):
    """Регистрирует обработчики спот-торговли."""
    dp.register_callback_query_handler(
        process_network_selection,
        lambda c: c.data.startswith('spot_network_'),
        state='*'
    )
    dp.register_callback_query_handler(
        process_token_selection,
        lambda c: c.data.startswith('spot_token_') or c.data == 'spot_search',
        state=SpotStates.choosing_token
    )
    dp.register_message_handler(
        process_amount,
        state=SpotStates.entering_amount
    )
    dp.register_callback_query_handler(
        execute_swap,
        lambda c: c.data == 'spot_confirm',
        state=SpotStates.confirming_swap
    )
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
    dp.register_message_handler(start_search_token, lambda c: c.data == "spot_search_token")
    dp.register_message_handler(search_token, state=SpotOrderStates.waiting_for_token)
    dp.register_message_handler(start_show_token_info, lambda c: c.data == "spot_token_info")
    dp.register_message_handler(show_token_info, state=SpotOrderStates.waiting_for_token)
    dp.register_message_handler(get_token_price, commands=['price']) 