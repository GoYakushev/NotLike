from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from services.copytrading.copytrading_service import CopyTradingService
from core.database.models import CopyTrader, CopyTraderFollower  #  CopyTrader, CopyTraderFollower

class CopyTradingStates(StatesGroup):
    entering_amount = State()

copytrading_service = CopyTradingService()

async def show_copytrading_menu(message: types.Message):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("👥 Топ трейдеров", callback_data="top_traders"),
        types.InlineKeyboardButton("📊 Мои подписки", callback_data="my_subscriptions")
    )
    keyboard.add(
        types.InlineKeyboardButton("📈 Стать трейдером", callback_data="become_trader")
    )
    
    await message.answer(
        "📊 Копитрейдинг\n\n"
        "Здесь вы можете:\n"
        "• Копировать сделки успешных трейдеров\n"
        "• Следить за их статистикой\n"
        "• Стать трейдером и получать вознаграждение",
        reply_markup=keyboard
    )

async def show_top_traders(callback_query: types.CallbackQuery):
    session = copytrading_service.db.get_session()
    traders = session.query(CopyTrader).order_by(CopyTrader.monthly_profit.desc()).limit(15).all()
    
    text = "🏆 Топ трейдеров:\n\n"
    for i, trader in enumerate(traders, 1):
        success_rate = (trader.successful_trades / trader.total_trades * 100) if trader.total_trades > 0 else 0
        text += (
            f"{i}. @{trader.user.username}\n"
            f"📈 Прибыль за месяц: {trader.monthly_profit:.2f}%\n"
            f"✅ Успешность: {success_rate:.1f}%\n"
            f"👥 Подписчиков: {trader.followers_count}\n\n"
        )
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="copytrading_menu"))
    
    await callback_query.message.answer(text, reply_markup=keyboard) 

async def become_trader(callback_query: types.CallbackQuery):
    result = await copytrading_service.register_as_trader(callback_query.from_user.id)

    if result['success']:
        await callback_query.message.answer(
            "✅ Вы успешно зарегистрированы как трейдер!\n"
            "Теперь другие пользователи могут копировать ваши сделки."
        )
    else:
        await callback_query.message.answer(
            f"❌ Ошибка при регистрации: {result['error']}"
        )

async def follow_trader_start(callback_query: types.CallbackQuery, state: FSMContext):
    await CopyTradingStates.entering_amount.set()
    await state.update_data(trader_id=int(callback_query.data.split('_')[2]))  #  ID
    await callback_query.message.answer("Введите сумму, которую вы хотите использовать для копирования:")

async def process_follow_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError

        data = await state.get_data()
        trader_id = data['trader_id']

        result = await copytrading_service.follow_trader(message.from_user.id, trader_id, amount)

        if result['success']:
            await message.answer("✅ Вы успешно подписались на трейдера!")
        else:
            await message.answer(f"❌ Ошибка: {result['error']}")

        await state.finish()

    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректную сумму (число больше нуля).")

async def my_subscriptions(callback_query: types.CallbackQuery):
    session = copytrading_service.db.get_session()
    subscriptions = session.query(CopyTraderFollower).filter_by(follower_id=callback_query.from_user.id, active=True).all()

    if not subscriptions:
        await callback_query.message.answer("У вас нет активных подписок.")
        return

    text = "📊 Ваши подписки:\n\n"
    for sub in subscriptions:
        trader = sub.trader.user  #  User
        text += (
            f"👤 Трейдер: @{trader.username}\n"
            f"💰 Сумма копирования: {sub.copy_amount:.2f}\n\n"
        )

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="copytrading_menu"))

    await callback_query.message.answer(text, reply_markup=keyboard)

async def unfollow_trader_handler(callback_query: types.CallbackQuery):
    trader_id = int(callback_query.data.split('_')[2])
    result = await copytrading_service.unfollow_trader(callback_query.from_user.id, trader_id)

    if result['success']:
        await callback_query.message.answer("✅ Вы успешно отписались от трейдера.")
    else:
        await callback_query.message.answer(f"❌ Ошибка: {result['error']}") 