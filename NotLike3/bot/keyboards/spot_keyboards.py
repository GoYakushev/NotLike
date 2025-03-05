from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Главное меню spot
spot_menu_keyboard = InlineKeyboardMarkup()
spot_menu_keyboard.add(InlineKeyboardButton("➕ Создать ордер", callback_data="create_spot_order"))
spot_menu_keyboard.add(InlineKeyboardButton("❌ Отменить ордер", callback_data="cancel_spot_order"))
spot_menu_keyboard.add(InlineKeyboardButton("📜 Мои ордера", callback_data="my_spot_orders"))
spot_menu_keyboard.add(InlineKeyboardButton("📖 История ордеров", callback_data="spot_order_history"))

# Выбор типа ордера
order_type_keyboard = InlineKeyboardMarkup()
order_type_keyboard.add(InlineKeyboardButton("📈 LIMIT", callback_data="order_type_limit"))
order_type_keyboard.add(InlineKeyboardButton("📉 MARKET", callback_data="order_type_market"))

# Выбор стороны (BUY/SELL)
buy_sell_keyboard = InlineKeyboardMarkup()
buy_sell_keyboard.add(InlineKeyboardButton("🛒 BUY", callback_data="side_buy"))
buy_sell_keyboard.add(InlineKeyboardButton("💰 SELL", callback_data="side_sell")) 