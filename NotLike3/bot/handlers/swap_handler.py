from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from services.swap.swap_service import SwapService

class SwapStates(StatesGroup):
    choosing_from = State()
    choosing_to = State()
    entering_amount = State()

swap_service = SwapService()

async def show_swap_menu(message: types.Message):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("SOL ↔️ TON", callback_data="swap_sol_ton"),
        types.InlineKeyboardButton("TON ↔️ SOL", callback_data="swap_ton_sol")
    )
    keyboard.add(
        types.InlineKeyboardButton("📊 История свопов", callback_data="swap_history")
    )
    
    await message.answer(
        "🔄 Свопы\n\n"
        "Здесь вы можете обменивать криптовалюты через SimpleSwap.\n"
        "Выберите направление обмена:",
        reply_markup=keyboard
    )

async def start_swap(callback_query: types.CallbackQuery, state: FSMContext):
    currencies = callback_query.data.split('_')[1:]
    await state.update_data(from_currency=currencies[0], to_currency=currencies[1])
    
    await callback_query.message.answer(
        f"Введите сумму {currencies[0]} для обмена:"
    )
    await SwapStates.entering_amount.set()

async def process_swap_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        data = await state.get_data()
        
        # Получаем курс обмена
        rate = await swap_service.get_rate(
            data['from_currency'],
            data['to_currency'],
            amount
        )
        
        if not rate['success']:
            await message.answer("❌ Не удалось получить курс обмена")
            return
            
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_swap_{amount}"),
            types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_swap")
        )
        
        await message.answer(
            f"📊 Детали обмена:\n\n"
            f"От: {amount} {data['from_currency']}\n"
            f"К: {rate['estimated']} {data['to_currency']}\n"
            f"Курс: 1 {data['from_currency']} = {rate['rate']} {data['to_currency']}\n\n"
            f"Подтвердите обмен:",
            reply_markup=keyboard
        )
        
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное число") 