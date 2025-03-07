from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from core.database.models import SupportTicket, User
from core.database.database import Database
from services.support.support_service import (
    SupportService,
    TicketCategory,
    TicketPriority,
    TicketStatus
)
import logging

db = Database()
logger = logging.getLogger(__name__)

class SupportStates(StatesGroup):
    choosing_category = State()
    entering_subject = State()
    entering_message = State()
    viewing_ticket = State()
    replying_ticket = State()

async def show_support_menu(message: types.Message):
    """Показывает главное меню поддержки."""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(
            "📝 Создать тикет",
            callback_data="support_create"
        ),
        types.InlineKeyboardButton(
            "📋 Мои тикеты",
            callback_data="support_list"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "❓ FAQ",
            callback_data="support_faq"
        ),
        types.InlineKeyboardButton(
            "📞 Контакты",
            callback_data="support_contacts"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "◀️ Назад",
            callback_data="main_menu"
        )
    )

    await message.answer(
        "🛠 Служба поддержки NotLike3\n\n"
        "Выберите действие:",
        reply_markup=keyboard
    )

async def process_support_callback(
    callback_query: types.CallbackQuery,
    state: FSMContext,
    support_service: SupportService
):
    """Обрабатывает callback-и меню поддержки."""
    action = callback_query.data.split('_')[1]

    if action == "create":
        await start_ticket_creation(callback_query.message, state)
    elif action == "list":
        await show_ticket_list(callback_query.message, support_service)
    elif action == "faq":
        await show_faq(callback_query.message)
    elif action == "contacts":
        await show_contacts(callback_query.message)
    else:
        await callback_query.answer("Неизвестное действие")

async def start_ticket_creation(message: types.Message, state: FSMContext):
    """Начинает процесс создания тикета."""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(
            "🔧 Техническая проблема",
            callback_data=f"ticket_category_{TicketCategory.TECHNICAL}"
        ),
        types.InlineKeyboardButton(
            "💰 Финансовый вопрос",
            callback_data=f"ticket_category_{TicketCategory.FINANCIAL}"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "🔒 Безопасность",
            callback_data=f"ticket_category_{TicketCategory.SECURITY}"
        ),
        types.InlineKeyboardButton(
            "💡 Предложение",
            callback_data=f"ticket_category_{TicketCategory.FEATURE_REQUEST}"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "❓ Общий вопрос",
            callback_data=f"ticket_category_{TicketCategory.GENERAL}"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "◀️ Назад",
            callback_data="support_menu"
        )
    )

    await message.edit_text(
        "📝 Создание тикета\n\n"
        "Выберите категорию обращения:",
        reply_markup=keyboard
    )
    await SupportStates.choosing_category.set()

async def process_category_selection(
    callback_query: types.CallbackQuery,
    state: FSMContext
):
    """Обрабатывает выбор категории тикета."""
    category = callback_query.data.split('_')[2]
    await state.update_data(category=category)

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton(
            "◀️ Назад",
            callback_data="support_create"
        )
    )

    await callback_query.message.edit_text(
        "📝 Создание тикета\n\n"
        "Введите тему обращения:",
        reply_markup=keyboard
    )
    await SupportStates.entering_subject.set()

async def process_subject(message: types.Message, state: FSMContext):
    """Обрабатывает ввод темы тикета."""
    await state.update_data(subject=message.text)

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton(
            "◀️ Назад",
            callback_data="support_create"
        )
    )

    await message.answer(
        "📝 Создание тикета\n\n"
        "Опишите вашу проблему или вопрос подробно:",
        reply_markup=keyboard
    )
    await SupportStates.entering_message.set()

async def process_message(
    message: types.Message,
    state: FSMContext,
    support_service: SupportService
):
    """Обрабатывает ввод сообщения и создает тикет."""
    user_data = await state.get_data()
    
    try:
        ticket = await support_service.create_ticket(
            user_id=message.from_user.id,
            subject=user_data['subject'],
            message=message.text,
            category=user_data['category']
        )

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                "📋 Просмотреть тикет",
                callback_data=f"ticket_view_{ticket['ticket_id']}"
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "◀️ В меню поддержки",
                callback_data="support_menu"
            )
        )

        await message.answer(
            "✅ Тикет успешно создан!\n\n"
            f"Номер тикета: #{ticket['ticket_id']}\n"
            "Мы рассмотрим ваше обращение в ближайшее время.",
            reply_markup=keyboard
        )
        await state.finish()

    except Exception as e:
        logger.error(f"Ошибка при создании тикета: {str(e)}")
        await message.answer(
            "❌ Произошла ошибка при создании тикета.\n"
            "Пожалуйста, попробуйте позже."
        )
        await state.finish()

async def show_ticket_list(
    message: types.Message,
    support_service: SupportService
):
    """Показывает список тикетов пользователя."""
    try:
        tickets = await support_service.get_user_tickets(
            message.from_user.id
        )

        if not tickets:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(
                types.InlineKeyboardButton(
                    "📝 Создать тикет",
                    callback_data="support_create"
                ),
                types.InlineKeyboardButton(
                    "◀️ Назад",
                    callback_data="support_menu"
                )
            )

            await message.edit_text(
                "У вас пока нет тикетов.",
                reply_markup=keyboard
            )
            return

        keyboard = types.InlineKeyboardMarkup()
        for ticket in tickets[:10]:  # Показываем только 10 последних
            status_emoji = {
                TicketStatus.NEW: "🆕",
                TicketStatus.IN_PROGRESS: "⏳",
                TicketStatus.WAITING_USER: "👤",
                TicketStatus.WAITING_ADMIN: "👨‍💼",
                TicketStatus.RESOLVED: "✅",
                TicketStatus.CLOSED: "🔒"
            }.get(ticket['status'], "❓")

            keyboard.add(
                types.InlineKeyboardButton(
                    f"{status_emoji} #{ticket['id']} - {ticket['subject'][:30]}...",
                    callback_data=f"ticket_view_{ticket['id']}"
                )
            )

        keyboard.add(
            types.InlineKeyboardButton(
                "📝 Создать тикет",
                callback_data="support_create"
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "◀️ Назад",
                callback_data="support_menu"
            )
        )

        await message.edit_text(
            "📋 Ваши тикеты:\n\n"
            "Выберите тикет для просмотра:",
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка при получении списка тикетов: {str(e)}")
        await message.edit_text(
            "❌ Произошла ошибка при получении списка тикетов.\n"
            "Пожалуйста, попробуйте позже."
        )

async def show_ticket(
    message: types.Message,
    ticket_id: int,
    support_service: SupportService
):
    """Показывает информацию о тикете."""
    try:
        ticket = await support_service.get_ticket(ticket_id)

        status_text = {
            TicketStatus.NEW: "🆕 Новый",
            TicketStatus.IN_PROGRESS: "⏳ В обработке",
            TicketStatus.WAITING_USER: "👤 Ожидает ответа пользователя",
            TicketStatus.WAITING_ADMIN: "👨‍💼 Ожидает ответа поддержки",
            TicketStatus.RESOLVED: "✅ Решен",
            TicketStatus.CLOSED: "🔒 Закрыт"
        }.get(ticket['status'], "❓ Неизвестно")

        text = (
            f"📋 Тикет #{ticket['id']}\n"
            f"Тема: {ticket['subject']}\n"
            f"Статус: {status_text}\n"
            f"Создан: {ticket['created_at']}\n\n"
            "💬 Сообщения:\n\n"
        )

        for msg in ticket['messages']:
            sender = "👤 Вы" if msg['is_from_user'] else "👨‍💼 Поддержка"
            if msg['is_auto_response']:
                sender = "🤖 Бот"
            text += f"{sender} ({msg['created_at']}):\n{msg['message']}\n\n"

        keyboard = types.InlineKeyboardMarkup()
        if ticket['status'] not in [TicketStatus.RESOLVED, TicketStatus.CLOSED]:
            keyboard.add(
                types.InlineKeyboardButton(
                    "💬 Ответить",
                    callback_data=f"ticket_reply_{ticket['id']}"
                )
            )
            if ticket['status'] == TicketStatus.WAITING_USER:
                keyboard.add(
                    types.InlineKeyboardButton(
                        "✅ Подтвердить решение",
                        callback_data=f"ticket_resolve_{ticket['id']}"
                    )
                )
        keyboard.add(
            types.InlineKeyboardButton(
                "🔒 Закрыть тикет",
                callback_data=f"ticket_close_{ticket['id']}"
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "◀️ К списку тикетов",
                callback_data="support_list"
            )
        )

        await message.edit_text(
            text,
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка при получении тикета: {str(e)}")
        await message.edit_text(
            "❌ Произошла ошибка при получении тикета.\n"
            "Пожалуйста, попробуйте позже."
        )

async def start_ticket_reply(
    callback_query: types.CallbackQuery,
    state: FSMContext
):
    """Начинает процесс ответа на тикет."""
    ticket_id = int(callback_query.data.split('_')[2])
    await state.update_data(ticket_id=ticket_id)

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton(
            "◀️ Назад к тикету",
            callback_data=f"ticket_view_{ticket_id}"
        )
    )

    await callback_query.message.edit_text(
        "💬 Введите ваш ответ:",
        reply_markup=keyboard
    )
    await SupportStates.replying_ticket.set()

async def process_ticket_reply(
    message: types.Message,
    state: FSMContext,
    support_service: SupportService
):
    """Обрабатывает ответ на тикет."""
    user_data = await state.get_data()
    ticket_id = user_data['ticket_id']

    try:
        await support_service.add_message(
            ticket_id=ticket_id,
            user_id=message.from_user.id,
            message=message.text
        )

        await state.finish()
        await show_ticket(message, ticket_id, support_service)

    except Exception as e:
        logger.error(f"Ошибка при ответе на тикет: {str(e)}")
        await message.answer(
            "❌ Произошла ошибка при отправке ответа.\n"
            "Пожалуйста, попробуйте позже."
        )
        await state.finish()

async def show_faq(message: types.Message):
    """Показывает FAQ."""
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton(
            "🔐 Безопасность и доступ",
            callback_data="faq_security"
        ),
        types.InlineKeyboardButton(
            "💰 Депозиты и выводы",
            callback_data="faq_finance"
        ),
        types.InlineKeyboardButton(
            "📊 Торговля",
            callback_data="faq_trading"
        ),
        types.InlineKeyboardButton(
            "⚙️ Технические вопросы",
            callback_data="faq_technical"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "◀️ Назад",
            callback_data="support_menu"
        )
    )

    await message.edit_text(
        "❓ Часто задаваемые вопросы\n\n"
        "Выберите категорию:",
        reply_markup=keyboard
    )

async def show_contacts(message: types.Message):
    """Показывает контактную информацию."""
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton(
            "📱 Telegram",
            url="https://t.me/notlike3_support"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "✉️ Email",
            url="mailto:support@notlike3.bot"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "◀️ Назад",
            callback_data="support_menu"
        )
    )

    await message.edit_text(
        "📞 Контакты\n\n"
        "Служба поддержки NotLike3 доступна:\n"
        "- Telegram: @notlike3_support\n"
        "- Email: support@notlike3.bot\n\n"
        "Время работы: 24/7\n"
        "Среднее время ответа: до 1 часа",
        reply_markup=keyboard
    )

def register_support_handlers(dp: Dispatcher, support_service: SupportService):
    """Регистрирует обработчики поддержки."""
    dp.register_message_handler(
        show_support_menu,
        commands=['support']
    )
    dp.register_callback_query_handler(
        lambda c: process_support_callback(c, dp.current_state(), support_service),
        lambda c: c.data.startswith('support_')
    )
    dp.register_callback_query_handler(
        lambda c: process_category_selection(c, dp.current_state()),
        lambda c: c.data.startswith('ticket_category_'),
        state=SupportStates.choosing_category
    )
    dp.register_message_handler(
        process_subject,
        state=SupportStates.entering_subject
    )
    dp.register_message_handler(
        lambda m: process_message(m, dp.current_state(), support_service),
        state=SupportStates.entering_message
    )
    dp.register_callback_query_handler(
        lambda c: start_ticket_reply(c, dp.current_state()),
        lambda c: c.data.startswith('ticket_reply_')
    )
    dp.register_message_handler(
        lambda m: process_ticket_reply(m, dp.current_state(), support_service),
        state=SupportStates.replying_ticket
    ) 