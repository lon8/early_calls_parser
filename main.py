import logging
import asyncio
import re
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InputFile
from datetime import datetime, timezone
from pyrogram import Client

API_TOKEN = '7521553255:AAGdGxgMAsYSPX4XKQpwJFwzxzVp3-L8bvU'
API_ID = '29928304'  # из Telegram API
API_HASH = 'e174bc4171eeb45fb2f34a1399af90d9'  # из Telegram API

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Состояния для хранения дат, channel_id и контроля выполнения
user_data = {}
collecting_tasks = {}  # Словарь для хранения задач сбора ссылок
stop_flags = {}  # Словарь для хранения флагов остановки сбора ссылок

# Инициализация клиента Pyrogram на уровне модуля
client = Client("my_bot_session", api_id=API_ID, api_hash=API_HASH)

# Обработчик команды /start
@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    await message.answer("Укажите ID каналов для сбора ссылок через пробел.")

# Обработка введенных channel_id
@dp.message_handler(lambda message: user_data.get(message.from_user.id, {}).get("channel_ids") is None)
async def handle_channel_ids(message: types.Message):
    channel_ids = message.text.split()
    user_data[message.from_user.id] = {"channel_ids": channel_ids}
    await message.answer("Укажите от какой даты начать сбор в формате '12.08.2024 12:38'.")

# Обработка введенной начальной даты
@dp.message_handler(lambda message: user_data.get(message.from_user.id, {}).get("start_date") is None)
async def handle_start_date(message: types.Message):
    try:
        start_date = datetime.strptime(message.text, '%d.%m.%Y %H:%M').replace(tzinfo=timezone.utc)
        user_data[message.from_user.id]["start_date"] = start_date
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

        # Запуск задачи сбора ссылок
        stop_flags[message.from_user.id] = asyncio.Event()
        task = asyncio.create_task(collect_links(message.from_user.id))
        collecting_tasks[message.from_user.id] = task

    except ValueError:
        await message.answer("Некорректный формат даты. Пожалуйста, используйте формат '12.08.2024 12:38'.")

# Обработчик команды /stop для остановки сбора ссылок
@dp.message_handler(commands=['stop'])
async def stop_command(message: types.Message):
    user_id = message.from_user.id
    if user_id in stop_flags:
        stop_flags[user_id].set()  # Устанавливаем флаг остановки
        await message.answer("Процесс сбора ссылок будет остановлен.")
    else:
        await message.answer("Сбор ссылок не запущен.")

# Функция для поиска ссылок в тексте
def extract_links_from_text(text):
    url_pattern = r'https?://t\.me/[^\s]+|http://t\.me/[^\s]+'
    raw_links = re.findall(url_pattern, text)
    filtered_links = [
        url for url in raw_links
        if url.startswith(("https://t.me/", "http://t.me/")) and
        not any(x in url for x in ("https://t.me/c", "http://t.me/c", "Bot", "bot", "atlantes_community"))
    ]
    return filtered_links

# Функция для сбора ссылок
async def collect_links(user_id):
    start_date = user_data[user_id]["start_date"]
    end_date = user_data[user_id]["end_date"]
    channel_ids = user_data[user_id]["channel_ids"]

    for channel_id in channel_ids:
        links_dict = {}
        offset_id = 0  # Начальное значение смещения
        
        while not stop_flags[user_id].is_set():
            async for message in client.get_chat_history(channel_id, limit=5000, offset_id=offset_id):
                if stop_flags[user_id].is_set():
                    logging.info("Процесс сбора ссылок был остановлен.")
                    await bot.send_message(user_id, "Процесс сбора ссылок был остановлен.")
                    return

                # Приведение даты сообщения к смещенной версии
                message_date = message.date.replace(tzinfo=timezone.utc)
                logging.info(f"Обрабатывается сообщение от {message_date}")
                
                if message_date < start_date:
                    # Если дата сообщения ниже начальной, прекращаем сбор
                    break
                
                if start_date <= message_date <= end_date:
                    # Извлечение ссылок из entities
                    if message.entities:
                        for entity in message.entities:
                            url = entity.url
                            if url and url.startswith(("https://t.me/", "http://t.me/")) and \
                                    not any(x in url for x in ("https://t.me/c", "http://t.me/c", "Bot", "bot", "atlantes_community")):
                                if url.count('/') == 3:
                                    links_dict[url] = message_date
                    
                    # Извлечение ссылок из текста сообщения с фильтрацией
                    links_in_text = extract_links_from_text(message.text or "")
                    for url in links_in_text:
                        links_dict[url] = message_date
                
                # Обновляем значение offset_id для следующего вызова
                offset_id = message.id

            await bot.send_message(user_id, f"Собрали 5000 сообщений из канала {channel_id}. Последняя дата: {message_date}")
            
            if message_date < start_date:
                # Если дата сообщения ниже начальной, прекращаем сбор
                break
            
            asyncio.sleep(0.4)

        # Сортировка и сохранение ссылок для текущего канала
        if links_dict:
            sorted_links = [link for link, date in sorted(links_dict.items(), key=lambda item: item[1])]
            sorted_links = set(sorted_links)
            file_name = f"links_{channel_id}_{user_id}.txt"
            with open(file_name, 'w') as f:
                for link in sorted_links:
                    f.write(link + '\n')

            await bot.send_document(user_id, InputFile(file_name))
        else:
            await bot.send_message(user_id, f"Ссылок за указанный период для канала {channel_id} не найдено.")

    # Удаление флага и задачи после завершения сбора
    del collecting_tasks[user_id]
    del stop_flags[user_id]
    user_data[user_id].pop("channel_ids", None)
    user_data[user_id].pop("start_date", None)
    user_data[user_id].pop("end_date", None)


if __name__ == '__main__':
    async def main():
        await client.start()  # Запуск клиента в асинхронном контексте
        try:
            await dp.start_polling()  # Асинхронный запуск polling
        finally:
            await client.stop()  # Остановка клиента в асинхронном контексте

    asyncio.run(main())