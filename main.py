import logging
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InputFile
from datetime import datetime, timezone
from pyrogram import Client

API_TOKEN = '6428396637:AAGRQRaNFtIqPaguXQ85QtvbDyshPGW9Hmk'
API_ID = '29928304'  # из Telegram API
API_HASH = 'e174bc4171eeb45fb2f34a1399af90d9'  # из Telegram API
CHANNEL_ID = '@early_calls'  # ID канала откуда будем собирать ссылки

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Состояния для хранения дат
user_data = {}

# Обработчик команды /start
@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    await message.answer("Укажите от какой даты начать сбор в формате '12.08.2024 12:38'.")

# Обработка введенной начальной даты
@dp.message_handler(lambda message: user_data.get(message.from_user.id, {}).get("start_date") is None)
async def handle_start_date(message: types.Message):
    try:
        start_date = datetime.strptime(message.text, '%d.%m.%Y %H:%M').replace(tzinfo=timezone.utc)
        user_data[message.from_user.id] = {"start_date": start_date}
        await message.answer("Укажите по какую дату собирать?")
    except ValueError:
        await message.answer("Некорректный формат даты. Пожалуйста, используйте формат '12.08.2024 12:38'.")

# Обработка введенной конечной даты
@dp.message_handler(lambda message: user_data.get(message.from_user.id, {}).get("end_date") is None)
async def handle_end_date(message: types.Message):
    try:
        end_date = datetime.strptime(message.text, '%d.%m.%Y %H:%M').replace(tzinfo=timezone.utc)
        user_data[message.from_user.id]["end_date"] = end_date
        await message.answer("Начинаю сбор ссылок...")

        await collect_links(message.from_user.id)
    except ValueError:
        await message.answer("Некорректный формат даты. Пожалуйста, используйте формат '12.08.2024 12:38'.")

# Функция для сбора ссылок
async def collect_links(user_id):
    start_date = user_data[user_id]["start_date"]
    end_date = user_data[user_id]["end_date"]

    links = []

    async with Client("my_bot_session", api_id=API_ID, api_hash=API_HASH) as client:
        async for message in client.get_chat_history(CHANNEL_ID, limit=100):
            # Приведение даты сообщения к смещенной версии
            message_date = message.date.replace(tzinfo=timezone.utc)

            if message_date < start_date:
                break
            if start_date <= message_date <= end_date:
                for entity in message.entities or []:
                    url = entity.url
                    if url != '' and url is not None:
                        if url.startswith("https://t.me/") and not ("https://t.me/c" in url or "Bot" in url or "bot" in url):
                            links.append(url)

    if links:
        links = set(links)
        file_name = f"links_{user_id}.txt"
        with open(file_name, 'w') as f:
            for link in links:
                f.write(link + '\n')

        await bot.send_document(user_id, InputFile(file_name))
    else:
        await bot.send_message(user_id, "Ссылок за указанный период не найдено.")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)