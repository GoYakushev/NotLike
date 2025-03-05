from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from core.database.models import User
from core.database.database import Database

db = Database()

class AdminStates(StatesGroup):
    waiting_for_message = State()

async def show_admin_menu(message: types.Message):
    """Показывает меню администратора."""
    session = db.get_session()
    user = session.query(User).filter_by(telegram_id=message.from_user.id).first()

    if user and user.is_admin:
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
            types.InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")
        )
        keyboard.add(
            types.InlineKeyboardButton("◀️ Назад", callback_data="main_menu")
        )
        await message.answer("Админ-панель", reply_markup=keyboard)
    else:
        await message.answer("У вас нет прав доступа.")

async def show_statistics(callback_query: types.CallbackQuery):
    """Показывает статистику."""
    #  реальную логику получения статистики
    stats = {
        'total_users': 1000,
        'active_users_24h': 500,
        'total_transactions_24h': 2000,
        'total_volume_24h': 100000,
    }

    text = (
        "📊 Статистика:\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"🟢 Активных за 24 часа: {stats['active_users_24h']}\n"
        f"🔄 Транзакций за 24 часа: {stats['total_transactions_24h']}\n"
        f"💰 Объем за 24 часа: ${stats['total_volume_24h']:,.2f}"
    )

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_menu"))

    await callback_query.message.answer(text, reply_markup=keyboard)
    await callback_query.answer()

async def broadcast_message(callback_query: types.CallbackQuery):
    """Начинает процесс рассылки."""
    await AdminStates.waiting_for_message.set()
    await callback_query.message.answer("Введите текст сообщения для рассылки:")
    await callback_query.answer()

async def process_broadcast_message(message: types.Message, state: FSMContext):
    """Рассылает сообщение всем пользователям."""
    session = db.get_session()
    users = session.query(User).all()
    session.close()

    for user in users:
        try:
            await message.copy_to(user.telegram_id)
        except Exception as e:
            print(f"Error sending message to {user.telegram_id}: {e}")

    await message.answer("Рассылка завершена.")
    await state.finish() 