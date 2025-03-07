from aiogram import types
from aiogram.dispatcher import FSMContext
from services.referral.referral_service import ReferralService

referral_service = ReferralService()

async def show_referral_menu(message: types.Message):
    """Показывает меню реферальной программы."""
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("🔗 Получить ссылку", callback_data="get_ref_link"),
        types.InlineKeyboardButton("📊 Статистика", callback_data="ref_stats")
    )
    keyboard.add(
        types.InlineKeyboardButton("◀️ Назад", callback_data="main_menu")
    )

    await message.answer(
        "🤝 Реферальная программа\n\n"
        "Приглашайте друзей и получайте бонусы!",
        reply_markup=keyboard
    )

async def get_referral_link(callback_query: types.CallbackQuery):
    """Отправляет реферальную ссылку."""
    link = await referral_service.get_referral_link(callback_query.from_user.id)
    await callback_query.message.answer(f"Ваша реферальная ссылка:\n{link}")
    await callback_query.answer()

async def show_referral_stats(callback_query: types.CallbackQuery):
    """Показывает статистику по рефералам."""
    stats = await referral_service.get_referral_stats(callback_query.from_user.id)

    if stats.get('error'):
        await callback_query.message.answer(f"Ошибка: {stats['error']}")
        return

    text = (
        "📊 Статистика рефералов:\n\n"
        f"👥 Всего приглашено: {stats['total_referrals']}\n"
        f"🟢 Активных: {stats['active_referrals']}\n"
        f"💰 Заработано: {stats['total_earned']:.2f}"
    )

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="referral_menu"))

    await callback_query.message.answer(text, reply_markup=keyboard)
    await callback_query.answer() 