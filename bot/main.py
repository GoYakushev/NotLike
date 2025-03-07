import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from bot.config import config
from core.database.database import Database
from core.database.models import User
from services.wallet.wallet_service import WalletService
from bot.handlers.spot_handler import show_spot_menu, search_token, show_token_info, SpotStates, register_spot_handlers, get_token_price
from bot.handlers.p2p_handler import show_p2p_menu, P2PStates, show_p2p_ads, register_p2p_handlers, check_expired_orders, initialize_p2p_service
from bot.handlers.copytrading_handler import show_copytrading_menu, show_top_traders, CopyTradingStates
from bot.handlers.swap_handler import show_swap_menu, start_swap, process_swap_amount, SwapStates
from bot.handlers.admin_handler import show_admin_menu, show_statistics, AdminStates, broadcast_message, process_broadcast_message
from services.notifications.notification_service import NotificationService, NotificationType
from bot.handlers.support_handler import show_support_menu, start_ticket_creation, process_ticket_subject, process_ticket_message, SupportStates
from bot.handlers.referral_handler import show_referral_menu, get_referral_link, show_referral_stats
from services.statistics.stats_service import StatsService
from services.fees.fee_service import FeeService
import aioschedule
from services.security.security_service import SecurityService
from services.backup.backup_service import BackupService
from services.copytrading.copytrading_service import CopyTradingService
from services.p2p.p2p_service import P2PService
from datetime import datetime
from typing import Optional, List
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from dotenv import load_dotenv #  Импорт load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Функция для загрузки конфигурации из .env файла
def load_config():
    load_dotenv() #  Загрузка переменных из .env файла
    config = {}
    config['bot_token'] = os.environ.get('BOT_TOKEN')
    config['api_key'] = os.environ.get('API_KEY')
    config['api_secret'] = os.environ.get('API_SECRET')
    config['yandex_disk_token'] = os.environ.get('YANDEX_DISK_TOKEN')
    config['encryption_key'] = os.environ.get('ENCRYPTION_KEY') #  Добавлено для ключа шифрования
    # ... другие параметры ...
    if not config['bot_token'] or not config['api_key'] or not config['api_secret']:
        raise ValueError("Bot token, API key and secret must be set in .env file.") #  Изменено сообщение об ошибке
    return config

async def main():
    try:
        config = load_config()
        logging.info("Configuration loaded successfully.")

        # Инициализация бота
        bot = Bot(token=config['bot_token'])
        storage = MemoryStorage()
        dp = Dispatcher(bot, storage=storage)
        db = Database()
        wallet_service = WalletService()
        copytrading_service = CopyTradingService(db, NotificationService(bot))

        # Инициализируем NotificationManager
        notification_service = NotificationService(bot)

        # Инициализируем сервисы
        stats_service = StatsService()
        fee_service = FeeService()

        # Добавим сервисы
        security_service = SecurityService()
        backup_service = BackupService(bot, config['yandex_disk_token'])

        # Инициализируем P2P сервис
        p2p_service = P2PService(db, notification_service)

        class WithdrawStates(StatesGroup):
            waiting_for_address = State()
            waiting_for_amount = State()
            waiting_for_confirmation = State()

        @dp.message_handler(commands=['start'])
        async def start_handler(message: types.Message):
            """Обработчик команды /start"""
            session = db.get_session()
            try:
                # Проверяем, существует ли пользователь
                user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
                
                if not user:
                    # Создаем нового пользователя
                    new_user = User(
                        telegram_id=message.from_user.id,
                        username=message.from_user.username,
                        full_name=message.from_user.full_name,
                        language_code=message.from_user.language_code,
                        registration_date=datetime.utcnow(),
                        last_login_date=datetime.utcnow()
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
                    logger.info(f"New user registered: {message.from_user.id}")
                else:
                    user.last_login_date = datetime.utcnow()
                    session.commit()
                    welcome_text = f"С возвращением! Чем могу помочь?"
                    logger.info(f"User logged in: {message.from_user.id}")
                
                keyboard = types.InlineKeyboardMarkup(row_width=2)
                keyboard.add(
                    types.InlineKeyboardButton("💼 Кошелек", callback_data="wallet"),
                    types.InlineKeyboardButton("📊 Спот", callback_data="spot"),
                    types.InlineKeyboardButton("👥 P2P", callback_data="p2p"),
                    types.InlineKeyboardButton("🔄 Своп", callback_data="swap")
                )
                
                await message.answer(welcome_text, reply_markup=keyboard)
            except Exception as e:
                logger.error(f"Error in start_handler for user {message.from_user.id}: {str(e)}", exc_info=True)
                await message.answer("❌ Произошла ошибка при обработке команды. Пожалуйста, попробуйте позже.")
                session.rollback()
            finally:
                session.close()

        @dp.callback_query_handler(lambda c: c.data in ["wallet", "spot", "p2p", "swap", "main_menu"])
        async def process_main_menu_callback(callback_query: types.CallbackQuery):
            """Обработчик основных callback-ов главного меню"""
            try:
                # Сначала отвечаем на callback чтобы убрать часики
                await callback_query.answer()
                
                if callback_query.data == "main_menu":
                    # Возврат в главное меню
                    keyboard = types.InlineKeyboardMarkup(row_width=2)
                    keyboard.add(
                        types.InlineKeyboardButton("💼 Кошелек", callback_data="wallet"),
                        types.InlineKeyboardButton("📊 Спот", callback_data="spot"),
                        types.InlineKeyboardButton("👥 P2P", callback_data="p2p"),
                        types.InlineKeyboardButton("🔄 Своп", callback_data="swap")
                    )
                    await callback_query.message.edit_text(
                        "Выберите раздел:",
                        reply_markup=keyboard
                    )
                    return

                # Маппинг callback_data к функциям
                handlers = {
                    "wallet": show_wallet,
                    "spot": show_spot,
                    "p2p": show_p2p,
                    "swap": show_swap
                }
                
                handler = handlers.get(callback_query.data)
                if handler:
                    await handler(callback_query.message)
                
            except Exception as e:
                logger.error(
                    f"Error in process_main_menu_callback for user {callback_query.from_user.id}, "
                    f"callback: {callback_query.data}, error: {str(e)}", 
                    exc_info=True
                )
                await callback_query.message.answer(
                    "❌ Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже."
                )

        @dp.callback_query_handler(lambda c: c.data in ["deposit", "withdraw", "refresh_balance"])
        async def process_wallet_callback(callback_query: types.CallbackQuery):
            """Обработчик callback-ов кошелька"""
            try:
                await callback_query.answer()
                
                if callback_query.data == "refresh_balance":
                    await show_wallet(callback_query.message)
                elif callback_query.data == "deposit":
                    # Показываем инструкции по депозиту
                    await show_deposit_instructions(callback_query.message)
                elif callback_query.data == "withdraw":
                    # Показываем форму вывода
                    await show_withdrawal_form(callback_query.message)
                    
            except Exception as e:
                logger.error(
                    f"Error in process_wallet_callback for user {callback_query.from_user.id}, "
                    f"callback: {callback_query.data}, error: {str(e)}", 
                    exc_info=True
                )
                await callback_query.message.answer(
                    "❌ Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже."
                )

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
                logger.error(f"Error in show_wallet for user {message.from_user.id}: {str(e)}", exc_info=True)
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

        async def get_all_users():
            """Получает список всех пользователей из базы данных"""
            session = db.get_session()
            try:
                users = session.query(User).all()
                return users
            except Exception as e:
                logger.error(f"Error getting all users: {str(e)}", exc_info=True)
                return []
            finally:
                session.close()

        # Добавим проверку дня недели для комиссий
        async def check_fees():
            try:
                message = fee_service.get_fee_message()
                if message:
                    users = await get_all_users()
                    for user in users:
                        try:
                            await bot.send_message(user.telegram_id, message)
                            await asyncio.sleep(0.1)  # Избегаем флуда
                        except Exception as e:
                            logger.error(f"Error sending fee message to {user.telegram_id}: {str(e)}")
            except Exception as e:
                logger.error(f"Error in check_fees: {str(e)}", exc_info=True)

        async def scheduler():
            """Планировщик задач"""
            try:
                # Проверка истекших P2P ордеров
                aioschedule.every(1).minutes.do(check_expired_orders)
                
                # Проверка комиссий каждый день в полночь
                aioschedule.every().day.at("00:00").do(check_fees)
                
                # Резервное копирование каждые 6 часов
                aioschedule.every(6).hours.do(backup_service.create_backup)
                
                while True:
                    try:
                        await aioschedule.run_pending()
                        await asyncio.sleep(1)
                    except Exception as e:
                        logger.error(f"Error in scheduler iteration: {str(e)}", exc_info=True)
                        await asyncio.sleep(5)  # Пауза перед следующей попыткой
            except Exception as e:
                logger.error(f"Critical error in scheduler: {str(e)}", exc_info=True)

        async def shutdown(dispatcher: Dispatcher):
            """Корректное завершение работы бота"""
            try:
                # Отменяем все задачи
                aioschedule.clear()
                
                # Закрываем соединения с БД
                session = db.get_session()
                session.close()
                
                # Уведомляем админов
                admins = await get_admin_users()
                for admin in admins:
                    try:
                        await bot.send_message(
                            admin.telegram_id,
                            "⚠️ Бот остановлен для технического обслуживания"
                        )
                    except Exception as e:
                        logger.error(f"Failed to notify admin {admin.telegram_id}: {str(e)}")
                
                # Закрываем хранилище состояний
                await dispatcher.storage.close()
                await dispatcher.storage.wait_closed()
                
                logger.info("Bot shutdown completed successfully")
            except Exception as e:
                logger.error(f"Error during shutdown: {str(e)}", exc_info=True)

        async def get_admin_users() -> List[User]:
            """Получает список администраторов"""
            session = db.get_session()
            try:
                return session.query(User).filter_by(is_admin=True).all()
            except Exception as e:
                logger.error(f"Error getting admin users: {str(e)}", exc_info=True)
                return []
            finally:
                session.close()

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

        async def show_deposit_instructions(message: types.Message):
            """Показывает инструкции по депозиту"""
            try:
                session = db.get_session()
                user = await get_user_from_message(message, session)
                if not user:
                    await message.answer("❌ Пользователь не найден. Пожалуйста, используйте /start")
                    return

                # Получаем или создаем кошельки пользователя для каждой сети
                wallets = await wallet_service.get_or_create_wallets(user.id)
                
                text = "📥 Инструкции по пополнению:\n\n"
                for network, wallet in wallets.items():
                    text += f"🔸 {network}:\n"
                    text += f"Адрес: `{wallet['address']}`\n\n"
                
                text += "⚠️ Важно:\n"
                text += "• Отправляйте только поддерживаемые токены\n"
                text += "• Минимальная сумма депозита: 1 USDT\n"
                text += "• Средства поступят после 10 подтверждений в сети\n"
                
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(
                    types.InlineKeyboardButton("🔄 Обновить", callback_data="refresh_balance"),
                    types.InlineKeyboardButton("◀️ Назад", callback_data="wallet")
                )
                
                await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
                
            except Exception as e:
                logger.error(f"Error in show_deposit_instructions for user {message.from_user.id}: {str(e)}", exc_info=True)
                await message.answer("❌ Произошла ошибка при получении инструкций. Пожалуйста, попробуйте позже.")
            finally:
                if 'session' in locals():
                    session.close()

        async def show_withdrawal_form(message: types.Message):
            """Показывает форму для вывода средств"""
            try:
                session = db.get_session()
                user = await get_user_from_message(message, session)
                if not user:
                    await message.answer("❌ Пользователь не найден. Пожалуйста, используйте /start")
                    return

                balances = await wallet_service.get_balances(user.id)
                if not balances or all(balance == 0 for balance in balances.values()):
                    await message.answer("❌ У вас нет доступных средств для вывода")
                    return

                text = "📤 Вывод средств\n\n"
                text += "Доступные балансы:\n"
                for network, balance in balances.items():
                    text += f"{network}: {balance:.4f}\n"
                
                text += "\nМинимальная сумма вывода: 10 USDT\n"
                text += "Комиссия за вывод: 1 USDT\n\n"
                text += "Выберите сеть для вывода:"

                keyboard = types.InlineKeyboardMarkup(row_width=2)
                for network in balances.keys():
                    if balances[network] > 0:
                        keyboard.add(types.InlineKeyboardButton(
                            f"📤 {network}", 
                            callback_data=f"withdraw_{network}"
                        ))
                
                keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="wallet"))
                
                await message.answer(text, reply_markup=keyboard)
                
            except Exception as e:
                logger.error(f"Error in show_withdrawal_form for user {message.from_user.id}: {str(e)}", exc_info=True)
                await message.answer("❌ Произошла ошибка при подготовке формы вывода. Пожалуйста, попробуйте позже.")
            finally:
                if 'session' in locals():
                    session.close()

        async def get_user_from_message(message: types.Message, session) -> Optional[User]:
            """Получает пользователя из базы данных по сообщению"""
            try:
                return session.query(User).filter_by(telegram_id=message.from_user.id).first()
            except Exception as e:
                logger.error(f"Error getting user from message: {str(e)}", exc_info=True)
                return None

        # Добавляем обработчики для вывода средств
        @dp.callback_query_handler(lambda c: c.data.startswith('withdraw_'))
        async def process_withdraw_network(callback_query: types.CallbackQuery, state: FSMContext):
            """Обработчик выбора сети для вывода"""
            try:
                await callback_query.answer()
                network = callback_query.data.split('_')[1]
                
                # Сохраняем выбранную сеть в состояние
                async with state.proxy() as data:
                    data['network'] = network
                
                await WithdrawStates.waiting_for_address.set()
                
                text = f"Введите адрес кошелька в сети {network} для вывода средств:"
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("◀️ Отмена", callback_data="cancel_withdraw"))
                
                await callback_query.message.answer(text, reply_markup=keyboard)
                
            except Exception as e:
                logger.error(f"Error in process_withdraw_network: {str(e)}", exc_info=True)
                await callback_query.message.answer("❌ Произошла ошибка. Пожалуйста, попробуйте позже.")

        @dp.message_handler(state=WithdrawStates.waiting_for_address)
        async def process_withdraw_address(message: types.Message, state: FSMContext):
            """Обработчик ввода адреса для вывода"""
            try:
                address = message.text.strip()
                
                # Проверяем корректность адреса
                async with state.proxy() as data:
                    network = data['network']
                    if not wallet_service.validate_address(address, network):
                        await message.answer(
                            f"❌ Некорректный адрес для сети {network}. Пожалуйста, проверьте адрес и попробуйте снова."
                        )
                        return
                    
                    data['address'] = address
                
                # Получаем баланс пользователя
                balance = await wallet_service.get_network_balance(message.from_user.id, network)
                
                await WithdrawStates.waiting_for_amount.set()
                
                text = (
                    f"💰 Доступно для вывода: {balance:.4f} {network}\n"
                    f"Минимальная сумма: 10 USDT\n"
                    f"Комиссия: 1 USDT\n\n"
                    f"Введите сумму для вывода:"
                )
                
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(
                    types.InlineKeyboardButton(f"Вывести всё ({balance:.4f})", 
                                             callback_data=f"withdraw_all_{balance}")
                )
                keyboard.add(types.InlineKeyboardButton("◀️ Отмена", callback_data="cancel_withdraw"))
                
                await message.answer(text, reply_markup=keyboard)
                
            except Exception as e:
                logger.error(f"Error in process_withdraw_address: {str(e)}", exc_info=True)
                await message.answer("❌ Произошла ошибка. Пожалуйста, попробуйте позже.")
                await state.finish()

        @dp.message_handler(state=WithdrawStates.waiting_for_amount)
        async def process_withdraw_amount(message: types.Message, state: FSMContext):
            """Обработчик ввода суммы для вывода"""
            try:
                amount = float(message.text.strip())
                
                async with state.proxy() as data:
                    network = data['network']
                    address = data['address']
                    
                    # Проверяем достаточность средств
                    balance = await wallet_service.get_network_balance(message.from_user.id, network)
                    
                    if amount < 10:
                        await message.answer("❌ Минимальная сумма вывода: 10 USDT")
                        return
                        
                    if amount + 1 > balance:  # +1 для комиссии
                        await message.answer("❌ Недостаточно средств с учетом комиссии")
                        return
                    
                    data['amount'] = amount
                    
                await WithdrawStates.waiting_for_confirmation.set()
                
                text = (
                    f"📤 Подтвердите вывод средств:\n\n"
                    f"Сеть: {network}\n"
                    f"Адрес: `{address}`\n"
                    f"Сумма: {amount:.4f} USDT\n"
                    f"Комиссия: 1 USDT\n"
                    f"Итого к получению: {(amount - 1):.4f} USDT\n\n"
                    f"Пожалуйста, внимательно проверьте все данные!"
                )
                
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(
                    types.InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_withdraw"),
                    types.InlineKeyboardButton("❌ Отменить", callback_data="cancel_withdraw")
                )
                
                await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
                
            except ValueError:
                await message.answer("❌ Пожалуйста, введите корректное число")
            except Exception as e:
                logger.error(f"Error in process_withdraw_amount: {str(e)}", exc_info=True)
                await message.answer("❌ Произошла ошибка. Пожалуйста, попробуйте позже.")
                await state.finish()

        @dp.callback_query_handler(lambda c: c.data == "confirm_withdraw", state=WithdrawStates.waiting_for_confirmation)
        async def process_withdraw_confirmation(callback_query: types.CallbackQuery, state: FSMContext):
            """Обработчик подтверждения вывода"""
            try:
                async with state.proxy() as data:
                    network = data['network']
                    address = data['address']
                    amount = data['amount']
                    
                    # Создаем транзакцию вывода
                    transaction = await wallet_service.create_withdrawal(
                        user_id=callback_query.from_user.id,
                        network=network,
                        address=address,
                        amount=amount
                    )
                    
                    if transaction:
                        text = (
                            f"✅ Заявка на вывод создана успешно!\n\n"
                            f"ID транзакции: `{transaction.transaction_hash}`\n"
                            f"Статус: {transaction.status}\n\n"
                            f"Вы получите уведомление после обработки вывода."
                        )
                        await callback_query.message.answer(text, parse_mode="Markdown")
                    else:
                        await callback_query.message.answer("❌ Не удалось создать заявку на вывод")
                        
            except Exception as e:
                logger.error(f"Error in process_withdraw_confirmation: {str(e)}", exc_info=True)
                await callback_query.message.answer("❌ Произошла ошибка при создании вывода")
            finally:
                await state.finish()

        @dp.callback_query_handler(lambda c: c.data == "cancel_withdraw", state="*")
        async def cancel_withdraw(callback_query: types.CallbackQuery, state: FSMContext):
            """Отмена процесса вывода средств"""
            await state.finish()
            await callback_query.answer("Вывод средств отменен")
            await show_wallet(callback_query.message)

        # Запускаем сервис уведомлений
        await notification_service.start()
        
        # Запускаем планировщики
        scheduler_task = asyncio.create_task(scheduler())
        backup_task = asyncio.create_task(backup_service.start_backup_scheduler())
        
        # Регистрируем обработчики
        register_p2p_handlers(dp)
        register_spot_handlers(dp)
        
        # Добавляем новый обработчик для команды /price
        dp.register_message_handler(get_token_price, commands=['price'])
        
        # Запускаем бота
        logger.info("Bot started successfully")
        
        try:
            await dp.start_polling()
        finally:
            await shutdown(dp)
            scheduler_task.cancel()
            backup_task.cancel()
            
    except ValueError as ve:
        logging.error(f"Configuration error: {ve}")
    except Exception as e:
        logger.exception("An unexpected error occurred:")
        raise

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {str(e)}", exc_info=True)
    finally:
        # Если есть активная сессия, закрываем её
        if 'session' in locals():
            session.close()
        logger.info("Bot shutdown completed") 