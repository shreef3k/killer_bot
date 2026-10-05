import asyncio
from pyrogram import Client
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
import os

# Загружаем переменные окружения
load_dotenv()

# Настройка доступа к Google Sheets
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE")

# Настройка юзербота #TODO
API_ID = int('api id')
API_HASH = "api hash"
PHONE = 'phone'

# Создаем клиент Pyrogram
app = Client(
    "user_session",
    api_id=API_ID,
    api_hash=API_HASH
)

async def send_mass_message_by_usernames():
    """Отправляет сообщение всем пользователям по их юзернеймам"""
    try:
        # Получаем список игроков из Google Sheets
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open("Игра в киллера").sheet1
        
        all_data = sheet.get_all_values()
        
        if len(all_data) <= 1:
            print("Таблица пуста")
            return
        
        # Собираем юзернеймы игроков
        players = []
        for row in all_data[1:]:
            if len(row) >= 7:
                username = row[6].strip().replace('@', '') if len(row) > 6 else ""
                name = row[1].strip() if len(row) > 1 else ""
                if username:
                    players.append({
                        'name': name,
                        'username': username
                    })
        
        if not players:
            print("Нет игроков с юзернеймами для рассылки")
            return
        
        print(f"Найдено игроков с юзернеймами: {len(players)}")
        for p in players:
            print(f"  - {p['name']} (@{p['username']})")
        
        # Текст сообщения
        message_text = """
ОБЪЯВЛЕНИЕ!

Игра "Киллер" началась!

Что делать дальше?
1. Зайдите в бота @mathcool_killer_game_bot
2. Ознакомьтесь с правилами с помощью команды /info
3. Проверьте свои цели в боте с помощью команды /target
4. Начинайте играть!

Удачи!
        """
        
        # Или можно ввести сообщение вручную
        # message_text = input("Введите текст сообщения: ")
        
        # Отправляем сообщения
        sent = 0
        failed = 0
        
        print("\nНачинаю рассылку...")
        
        for player in players:
            try:
                # Получаем entity пользователя по юзернейму
                entity = await app.get_users(f"@{player['username']}")
                
                # Отправляем сообщение
                await app.send_message(entity.id, message_text)
                
                sent += 1
                print(f"✅ Отправлено {player['name']} (@{player['username']})")
                
                # Задержка между сообщениями (чтобы не заблокировали)
                await asyncio.sleep(1)
                
            except Exception as e:
                failed += 1
                print(f"❌ Не удалось отправить {player['name']} (@{player['username']}): {e}")
        
        print(f"\nРассылка завершена!")
        print(f"Отправлено: {sent}")
        print(f"Не удалось: {failed}")
        
    except Exception as e:
        print(f"Ошибка: {e}")

async def main():
    print("Запуск Pyrogram...")
    
    async with app:
        print("✅ Pyrogram запущен")
        print("Ваш аккаунт:", (await app.get_me()).username)

                # Текст сообщения
        message_text = """
ОБЪЯВЛЕНИЕ!

Игра "Киллер" завершена.

Приходите на сегодняшнюю линейку в 18:50. Победителям "Киллера" будут выданы призы!

Спасибо за участие!

Создатель игры: @shreef3k
        """
        
        if not message_text.strip():
            print("Сообщение пустое. Отмена.")
            return
        
        # Получаем список игроков из таблицы
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open("Игра в киллера").sheet1
        
        all_data = sheet.get_all_values()
        players = []
        for row in all_data[1:]:
            if len(row) >= 7:
                username = row[6].strip().replace('@', '') if len(row) > 6 else ""
                name = row[1].strip() if len(row) > 1 else ""
                if username:
                    players.append({
                        'name': name,
                        'username': username
                    })
        
        if not players:
            print("Нет игроков с юзернеймами для рассылки")
            return
        
        print(f"\nНайдено игроков: {len(players)}")
        print("Список получателей:")
        for p in players:
            print(f"  - {p['name']} (@{p['username']})")
        
        confirm = input(f"\nОтправить сообщение {len(players)} получателям? (да/нет): ").strip().lower()
        
        if confirm not in ['да', 'yes', 'y', 'д']:
            print("Отмена.")
            return
        
        # Отправляем сообщения
        sent = 0
        failed = 0
        
        print("\nНачинаю рассылку...")
        
        for player in players:
            try:
                entity = await app.get_users(f"@{player['username']}")
                await app.send_message(entity.id, message_text)
                sent += 1
                print(f"✅ Отправлено {player['name']} (@{player['username']})")
                await asyncio.sleep(1)
            except Exception as e:
                failed += 1
                print(f"❌ Не удалось отправить {player['name']} (@{player['username']}): {e}")
        
        print(f"\nРассылка завершена!")
        print(f"Отправлено: {sent}")
        print(f"Не удалось: {failed}")

if __name__ == "__main__":
    asyncio.run(main())