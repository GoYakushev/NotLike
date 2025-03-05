from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from services.demo.demo_service import DemoService

class DemoStates(StatesGroup):
    choosing_token = State()
    entering_amount = State()
    confirming_order = State()

demo_service = DemoService()

async def show_demo_menu(message: types.Message):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("🔄 Переключить режим", callback_data="toggle_demo"),
        types.InlineKeyboardButton("💰 Демо-баланс", callback_data="demo_balance")
    )
    keyboard.add(
        types.InlineKeyboardButton("📊 Мои демо-ордера", callback_data="demo_orders"),
        types.InlineKeyboardButton("📈 Торговать", callback_data="demo_trade")
    )
    
    await message.answer(
        "🎮 Демо-торговля\n\n"
        "Здесь вы можете:\n"
        "• Торговать на виртуальные токены\n"
        "• Тестировать стратегии\n"
        "• Учиться без риска",
        reply_markup=keyboard
    )

async def toggle_demo_mode(callback_query: types.CallbackQuery):
    result = await demo_service.toggle_demo_mode(callback_query.from_user.id)
    
    if result['success']:
        mode = "включен ✅" if result['demo_mode'] else "выключен ❌"
        await callback_query.message.answer(
            f"🔄 Демо-режим {mode}\n"
            f"💰 Баланс: ${result['balance']:,.2f}"
        )
    else:
        await callback_query.message.answer(
            f"❌ Ошибка: {result['error']}"
        ) 