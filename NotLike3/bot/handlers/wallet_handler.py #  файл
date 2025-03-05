async def show_wallet(message: types.Message):
    """Показывает информацию о кошельках пользователя"""
    try:
        balances = await wallet_service.get_balances(message.from_user.id)

        text = "💼 Ваши кошельки:\n\n"
        for token_symbol, balance in balances.items():
            text += f"{token_symbol}: {balance:.4f}\n"

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
        await message.answer(f"❌ Произошла ошибка при получении информации о кошельках: {e}") 