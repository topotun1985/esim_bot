import os
import asyncio
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# Загружаем переменные окружения
load_dotenv()

# Настраиваем логирование
logging.basicConfig(level=logging.INFO)

# Инициализируем бота
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения")

# Инициализируем бота с новыми настройками
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

@dp.message(Command("get_chat_id"))
async def send_chat_id(message: Message):
    """
    Отправляет ID текущего чата.
    """
    chat_id = message.chat.id
    await message.reply(f"ID чата: <code>{chat_id}</code>")

async def main():
    try:
        # Удаляем веб-хук перед запуском polling
        await bot.delete_webhook(drop_pending_updates=True)

        # Запускаем polling
        await dp.start_polling(bot, allowed_updates=["message"])
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nБот остановлен")
    except Exception as e:
        print(f"\nПроизошла ошибка: {e}")