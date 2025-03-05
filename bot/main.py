import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from bot.config import config
from core.database.database import Database
from services.wallet.wallet_service import WalletService
from bot.handlers.spot_handler import show_spot_menu, search_token, show_token_info, SpotStates, register_spot_handlers
from bot.handlers.p2p_handler import show_p2p_menu, P2PStates, show_p2p_ads, register_p2p_handlers
from bot.handlers.copytrading_handler import show_copytrading_menu, show_top_traders, CopyTradingStates
from bot.handlers.swap_handler import show_swap_menu, start_swap, process_swap_amount, SwapStates
from bot.handlers.admin_handler import show_admin_menu, show_statistics, AdminStates, broadcast_message, process_broadcast_message
from utils.notifications import NotificationManager
from bot.handlers.support_handler import show_support_menu, start_ticket_creation, process_ticket_subject, process_ticket_message, SupportStates
from bot.handlers.referral_handler import show_referral_menu, get_referral_link, show_referral_stats
from services.statistics.stats_service import StatsService
from services.fees.fee_service import FeeService
import aioschedule
from services.security.security_service import SecurityService
from services.backup.backup_service import BackupService
from services.notifications.notification_service import NotificationService, NotificationType
from services.copytrading.copytrading_service import CopyTradingService

# Инициализация бота
bot = Bot(token=config.BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
db = Database()
wallet_service = WalletService()
copytrading_service = CopyTradingService(db, NotificationService(bot))

# Инициализируем NotificationManager
notification_manager = NotificationManager(bot)

# Инициализируем сервисы
stats_service = StatsService()
fee_service = FeeService()

# Добавим сервисы
security_service = SecurityService()
backup_service = BackupService(bot, config.YANDEX_DISK_TOKEN)

# Инициализируем сервис уведомлений
notification_service = NotificationService(bot)

@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    session = db.get_session()
    
    # Проверяем, существует ли пользователь
    user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
    
    if not user:
        # Создаем нового пользователя
        new_user = User(
            telegram_id=message.from_user.id,
            username=message.from_user.username
        )
        session.add(new_user)
        session.commit()
        
        welcome_text = (
            "🚀 Добро пожаловать в Not Like Trading Bot!\n\n"
            "Здесь вы можете:\n"
            "📈 Торговать на спотовом рынке\n"
            "👥 Участвовать в P2P торговле\n"
            "💼 Управлять криптовалютными активами\n"
            "🔄 Совершать свопы между сетями\n\n"
            "Перед началом работы, пожалуйста, ознакомьтесь с условиями использования /terms"
        )
    else:
        welcome_text = f"С возвращением! Чем могу помочь?"
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("💼 Кошелек", callback_data="wallet"),
        types.InlineKeyboardButton("📊 Спот", callback_data="spot")
    )
    keyboard.add(
        types.InlineKeyboardButton("👥 P2P", callback_data="p2p"),
        types.InlineKeyboardButton("🔄 Своп", callback_data="swap")
    )
    
    await message.answer(welcome_text, reply_markup=keyboard)

@dp.callback_query_handler(lambda c: True)
async def process_callback(callback_query: types.CallbackQuery):
    if callback_query.data == "wallet":
        await show_wallet(callback_query.message)
    elif callback_query.data == "spot":
        await show_spot(callback_query.message)
    elif callback_query.data == "p2p":
        await show_p2p(callback_query.message)
    elif callback_query.data == "swap":
        await show_swap(callback_query.message)

async def show_wallet(message: types.Message):
    """Показывает информацию о кошельках пользователя"""
    try:
        balances = await wallet_service.get_balances(message.from_user.id)
        
        text = "💼 Ваши кошельки:\n\n"
        for network, balance in balances.items():
            text += f"{network}: {balance:.4f}\n"
            
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton("📥 Пополнить", callback_data="deposit"),
            types.InlineKeyboardButton("📤 Вывести", callback_data="withdraw")
        )
        keyboard.add(
            types.InlineKeyboardButton("🔄 Обновить", callback_data="refresh_balance"),
            types.InlineKeyboardButton("◀️ Назад", callback_data="main_menu")
        )
        
        await message.answer(text, reply_markup=keyboard)
    except Exception as e:
        await message.answer("❌ Произошла ошибка при получении информации о кошельках")

async def show_spot(message: types.Message):
    await show_spot_menu(message)

async def show_p2p(message: types.Message):
    await show_p2p_menu(message)

async def show_swap(message: types.Message):
    await show_swap_menu(message)

# Регистрируем обработчики состояний
dp.register_message_handler(search_token, state=SpotStates.choosing_token)
dp.register_message_handler(show_token_info, state=SpotStates.entering_amount)

# Добавим обработчики P2P callback'ов
@dp.callback_query_handler(lambda c: c.data.startswith('p2p_'))
async def process_p2p_callback(callback_query: types.CallbackQuery):
    action = callback_query.data.split('_')[1]
    if action == 'buy':
        await show_p2p_ads(callback_query, 'SELL')
    elif action == 'sell':
        await show_p2p_ads(callback_query, 'BUY')
    elif action == 'menu':
        await show_p2p_menu(callback_query.message)

# Добавим новые обработчики
dp.register_callback_query_handler(
    lambda c: c.data.startswith('swap_'),
    lambda c: not c.data == 'swap_history',
    state=None
)
dp.register_message_handler(process_swap_amount, state=SwapStates.entering_amount)

# Копитрейдинг
dp.register_callback_query_handler(show_top_traders, lambda c: c.data == 'top_traders')

# Добавим команду для админки
@dp.message_handler(commands=['admin'])
async def admin_command(message: types.Message):
    await show_admin_menu(message)

# Добавим обработчики админки
dp.register_callback_query_handler(show_statistics, lambda c: c.data == "admin_stats")
dp.register_callback_query_handler(show_admin_menu, lambda c: c.data == "admin_menu")
dp.register_callback_query_handler(broadcast_message, lambda c: c.data == "admin_broadcast")
dp.register_message_handler(process_broadcast_message, state=AdminStates.waiting_for_message)

# Добавим команду для поддержки
@dp.message_handler(commands=['support'])
async def support_command(message: types.Message):
    await show_support_menu(message)

# Регистрируем обработчики поддержки
dp.register_callback_query_handler(start_ticket_creation, lambda c: c.data == "create_ticket")
dp.register_message_handler(process_ticket_subject, state=SupportStates.waiting_for_subject)
dp.register_message_handler(process_ticket_message, state=SupportStates.waiting_for_message)

# Добавим команду для реферальной программы
@dp.message_handler(commands=['referral'])
async def referral_command(message: types.Message):
    await show_referral_menu(message)

# Регистрируем обработчики реферальной программы
dp.register_callback_query_handler(get_referral_link, lambda c: c.data == "get_ref_link")
dp.register_callback_query_handler(show_referral_stats, lambda c: c.data == "ref_stats")

# Добавим команду для просмотра статистики
@dp.message_handler(commands=['stats'])
async def show_global_stats(message: types.Message):
    stats = await stats_service.get_global_stats()
    
    if not stats:
        await message.answer("❌ Ошибка при получении статистики")
        return
        
    text = (
        "📊 Статистика за 24 часа:\n\n"
        f"💰 Общий объем: ${stats['total_volume_24h']:,.2f}\n"
        f"📈 Транзакций: {stats['transactions_24h']}\n"
        f"👥 Активных пользователей: {stats['active_users_24h']}\n\n"
        "🔸 Детали:\n"
        f"• Спот: ${stats['details']['spot']['volume']:,.2f} ({stats['details']['spot']['count']} сделок)\n"
        f"• P2P: ${stats['details']['p2p']['volume']:,.2f} ({stats['details']['p2p']['count']} сделок)\n"
        f"• Свопы: ${stats['details']['swap']['volume']:,.2f} ({stats['details']['swap']['count']} сделок)"
    )
    
    await message.answer(text)

# Добавим проверку дня недели для комиссий
async def check_fees():
    message = fee_service.get_fee_message()
    if message:
        # Отправляем всем пользователям
        users = await get_all_users()
        for user in users:
            try:
                await bot.send_message(user.telegram_id, message)
                await asyncio.sleep(0.1)  # Избегаем флуда
            except Exception as e:
                print(f"Error sending fee message to {user.telegram_id}: {e}")

# Запускаем проверку каждый день в полночь
aioschedule.every().day.at("00:00").do(check_fees)

async def scheduler():
    while True:
        await aioschedule.run_pending()
        await asyncio.sleep(1)

# Добавим middleware для безопасности
@dp.middleware_handler()
async def security_middleware(handler, event, data):
    # Проверяем rate limit
    if not security_service.check_rate_limit(
        event.from_user.id,
        event.text if hasattr(event, 'text') else 'action'
    ):
        await event.answer("⚠️ Слишком много запросов. Пожалуйста, подождите.")
        return
        
    # Очищаем пользовательский ввод
    if hasattr(event, 'text'):
        event.text = security_service.sanitize_input(event.text)
        
    return await handler(event, data)

# Обновляем main()
async def main():
    # Запускаем сервис уведомлений
    await notification_service.start()
    
    # Запускаем планировщик резервного копирования
    asyncio.create_task(backup_service.start_backup_scheduler())
    asyncio.create_task(scheduler())
    register_p2p_handlers(dp) # Регистрируем p2p хендлеры
    register_spot_handlers(dp) # Регистрируем spot хендлеры
    await dp.start_polling()

if __name__ == '__main__':
    asyncio.run(main()) 