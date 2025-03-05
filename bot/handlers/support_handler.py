from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from core.database.models import SupportTicket, User
from core.database.database import Database

db = Database()

class SupportStates(StatesGroup):
    waiting_for_subject = State()
    waiting_for_message = State()

async def show_support_menu(message: types.Message):
    """Показывает меню поддержки."""
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("📝 Создать тикет", callback_data="create_ticket")
    )
    keyboard.add(
        types.InlineKeyboardButton("◀️ Назад", callback_data="main_menu")
    )

    await message.answer(
        "🆘 Поддержка\n\n"
        "Если у вас возникли вопросы или проблемы, создайте тикет.",
        reply_markup=keyboard
    )

async def start_ticket_creation(callback_query: types.CallbackQuery):
    """Начинает процесс создания тикета."""
    await SupportStates.waiting_for_subject.set()
    await callback_query.message.answer("Введите тему обращения:")
    await callback_query.answer()

async def process_ticket_subject(message: types.Message, state: FSMContext):
    """Обрабатывает тему обращения."""
    await state.update_data(subject=message.text)
    await SupportStates.waiting_for_message.set()
    await message.answer("Опишите вашу проблему:")

async def process_ticket_message(message: types.Message, state: FSMContext):
    """Обрабатывает сообщение тикета и сохраняет тикет."""
    data = await state.get_data()
    subject = data['subject']
    ticket_message = message.text

    session = db.get_session()
    user = session.query(User).filter_by(telegram_id=message.from_user.id).first()

    if not user:
        await message.answer("❌ Ошибка: пользователь не найден.")
        await state.finish()
        return

    try:
        ticket = SupportTicket(
            user_id=user.id,
            subject=subject,
            message=ticket_message,
            status='OPEN'
        )
        session.add(ticket)
        session.commit()

        await message.answer("✅ Ваш тикет создан и отправлен в поддержку.")

    except Exception as e:
        session.rollback()
        await message.answer(f"❌ Ошибка при создании тикета: {str(e)}")

    finally:
        session.close()
        await state.finish() 