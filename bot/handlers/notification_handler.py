from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from core.database.models import NotificationSettings
from services.notifications.notification_service import NotificationType

class NotificationStates(StatesGroup):
    choosing_type = State()
    choosing_channels = State()

async def show_notification_settings(message: types.Message):
    """Показывает меню настроек уведомлений"""
    keyboard = types.InlineKeyboardMarkup()
    
    # Добавляем кнопки для всех типов уведомлений
    for notification_type in vars(NotificationType).items():
        if not notification_type[0].startswith('_'):
            keyboard.add(types.InlineKeyboardButton(
                f"⚙️ {notification_type[0].replace('_', ' ').title()}",
                callback_data=f"notif_settings_{notification_type[1]}"
            ))
            
    await message.answer(
        "🔔 Настройки уведомлений\n\n"
        "Выберите тип уведомлений для настройки:",
        reply_markup=keyboard
    )

async def show_type_settings(callback_query: types.CallbackQuery, state: FSMContext):
    """Показывает настройки конкретного типа уведомлений"""
    notification_type = callback_query.data.split('_')[2]
    
    session = db.get_session()
    settings = session.query(NotificationSettings)\
        .filter_by(user_id=callback_query.from_user.id).first()
        
    if not settings:
        settings = NotificationSettings(
            user_id=callback_query.from_user.id,
            settings='{}'
        )
        session.add(settings)
        session.commit()
        
    enabled = settings.is_enabled(notification_type)
    channels = settings.get_channels(notification_type)
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton(
            "✅ Включено" if enabled else "❌ Выключено",
            callback_data=f"notif_toggle_{notification_type}"
        )
    )
    
    # Кнопки для каналов
    for channel in ['telegram', 'email']:
        status = "✅" if channel in channels else "❌"
        keyboard.add(types.InlineKeyboardButton(
            f"{status} {channel.title()}",
            callback_data=f"notif_channel_{notification_type}_{channel}"
        ))
        
    keyboard.add(types.InlineKeyboardButton(
        "🔙 Назад",
        callback_data="notif_back"
    ))
    
    await callback_query.message.edit_text(
        f"⚙️ Настройки уведомлений: {notification_type.replace('_', ' ').title()}\n\n"
        f"Статус: {'Включено' if enabled else 'Выключено'}\n"
        f"Каналы доставки: {', '.join(channels)}",
        reply_markup=keyboard
    ) 