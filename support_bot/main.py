from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from config import BOT_TOKEN, OPENROUTER_API_KEY, SUPPORT_MODEL, TEMPERATURE, SUPPORT_PROMPT
import openrouter
import asyncio
import json

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

openrouter.api_key = OPENROUTER_API_KEY

async def get_ai_response(message: str) -> str:
    try:
        response = await openrouter.ChatCompletion.create(
            model=SUPPORT_MODEL,
            messages=[
                {"role": "system", "content": SUPPORT_PROMPT},
                {"role": "user", "content": message}
            ],
            temperature=TEMPERATURE
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Извините, произошла ошибка. Пожалуйста, используйте /helpme для связи с человеком.\nОшибка: {str(e)}"

@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    await message.answer(
        "👋 Добро пожаловать в Not Like Support!\n\n"
        "По умолчанию на ваши вопросы отвечает ИИ-ассистент.\n"
        "Для связи с реальным оператором используйте /helpme\n\n"
        "❗️ Ночью ответ от операторов может занять больше времени."
    )

@dp.message_handler(commands=['helpme'])
async def helpme_handler(message: types.Message):
    # Получаем всех админов из основного бота
    admins = await get_available_admins()
    
    # Создаем тикет
    ticket_id = await create_support_ticket(message.from_user.id)
    
    # Отправляем уведомление админам
    for admin in admins:
        await bot.send_message(
            admin.telegram_id,
            f"🆘 Новый запрос в поддержку\n"
            f"От: @{message.from_user.username}\n"
            f"ID: {ticket_id}\n\n"
            f"Для принятия тикета нажмите кнопку ниже:",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("✅ Принять", callback_data=f"accept_ticket_{ticket_id}")
            )
        )
    
    await message.answer(
        "✅ Ваш запрос отправлен операторам.\n"
        "Первый освободившийся специалист ответит вам.\n"
        "Пожалуйста, ожидайте."
    )

@dp.message_handler(content_types=['text', 'photo', 'video'])
async def handle_message(message: types.Message):
    if message.text and not message.text.startswith('/'):
        response = await get_ai_response(message.text)
        await message.answer(response)
    elif message.photo or message.video:
        # Обработка медиафайлов для активных тикетов
        ticket = await get_active_ticket(message.from_user.id)
        if ticket and ticket.operator_id:
            # Пересылаем медиа оператору
            await forward_to_operator(message, ticket.operator_id)
        else:
            await message.answer(
                "📸 Я вижу, что вы отправили медиафайл.\n"
                "К сожалению, ИИ не может их обрабатывать.\n"
                "Используйте /helpme для связи с оператором."
            )

async def main():
    await dp.start_polling()

if __name__ == '__main__':
    asyncio.run(main()) 