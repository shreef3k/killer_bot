import logging
import asyncio
import os
from aiogram import Bot, Dispatcher, types
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
import time

# Загружаем переменные окружения из .env файла
load_dotenv()

# Получаем значения переменных
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE")
SENTRY_DNS = os.getenv("SENTRY_DNS")

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка доступа к Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive",
         "https://www.googleapis.com/auth/spreadsheets"]
creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
client = gspread.authorize(creds)

# Открытие Google таблицы
sheet = client.open("Игра в киллера").sheet1

# Инициализация бота и диспетчера
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Словарь для хранения информации о пользователях
users = {}

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

start_router = Router()

# Функция для покраски ВСЕЙ строки до столбца Q (17 колонок)
def color_row(row_number, bg_color, text_color):
    """
    Красит ВСЮ строку до столбца Q (17 колонок) в указанный цвет фона и цвет текста
    row_number - номер строки (1-based)
    bg_color - цвет фона в формате RGB (например, (255, 0, 0) для красного)
    text_color - цвет текста в формате RGB (например, (255, 255, 255) для белого)
    """
    try:
        if row_number <= 1:  # Не трогаем первую строку
            return
        
        # Красим до столбца Q (17 колонок)
        num_columns = 17  # Q - 17-я буква алфавита
        
        logger.info(f"Строка {row_number} будет покрашена до столбца Q ({num_columns} колонок)")
        
        # Создаем запрос на обновление формата для всей строки
        requests = [{
            "repeatCell": {
                "range": {
                    "sheetId": sheet.id,
                    "startRowIndex": row_number - 1,
                    "endRowIndex": row_number,
                    "startColumnIndex": 0,  # Начинаем с первой колонки (A)
                    "endColumnIndex": num_columns  # Заканчиваем на колонке Q (17)
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {
                            "red": bg_color[0] / 255.0,
                            "green": bg_color[1] / 255.0,
                            "blue": bg_color[2] / 255.0
                        },
                        "textFormat": {
                            "foregroundColor": {
                                "red": text_color[0] / 255.0,
                                "green": text_color[1] / 255.0,
                                "blue": text_color[2] / 255.0
                            }
                        }
                    }
                },
                "fields": "userEnteredFormat.backgroundColor,userEnteredFormat.textFormat.foregroundColor"
            }
        }]
        
        # Выполняем запрос
        sheet.spreadsheet.batch_update({"requests": requests})
        logger.info(f"Строка {row_number} покрашена до колонки Q (фон: {bg_color}, текст: {text_color})")
        
    except Exception as e:
        logger.error(f"Ошибка при покраске строки {row_number}: {e}")

# Функция для покраски строки в зеленый (alive) с черным текстом
def color_alive(row_number):
    color_row(row_number, (0, 200, 0), (0, 0, 0))  # Зеленый фон, черный текст

# Функция для покраски строки в красный (dead) с белым текстом
def color_dead(row_number):
    color_row(row_number, (255, 0, 0), (255, 255, 255))  # Красный фон, белый текст

# Функция для обновления цвета всей таблицы
def update_all_colors():
    """Обновляет цвета всех строк в таблице"""
    try:
        all_data = sheet.get_all_values()
        if len(all_data) <= 1:
            return
        
        logger.info("Обновление цветов всех строк...")
        
        for i, row in enumerate(all_data[1:], start=2):
            if len(row) > 3:
                status = row[3].strip().lower() if len(row) > 3 else ""
                if status == 'alive':
                    color_row(i, (0, 200, 0), (0, 0, 0))
                elif status == 'dead':
                    color_row(i, (255, 0, 0), (255, 255, 255))
        
        logger.info("Цвета всех строк обновлены")
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении цветов: {e}")

# Вспомогательная функция для проверки, жив ли пользователь
def is_user_alive(user_id):
    if user_id in users:
        row = users[user_id]['row']
        try:
            status = sheet.cell(row, 4).value  # Column D - status
            return status == 'alive'
        except:
            return False
    return False

# Функция для обновления Telegram ID пользователя
def update_telegram_id(username, telegram_id):
    """Обновляет Telegram ID в таблице по юзернейму"""
    try:
        if not username:
            return False
        # Ищем пользователя по юзернейму в колонке G (7-й столбец)
        cell = sheet.find(f"@{username}", in_column=7)
        if cell:
            row = cell.row
            # Проверяем, пуст ли Telegram ID
            current_id = sheet.cell(row, 6).value  # Колонка F
            if not current_id or current_id.strip() == '':
                # Обновляем Telegram ID
                sheet.update_cell(row, 6, str(telegram_id))
                logger.info(f"Присвоен Telegram ID {telegram_id} для @{username}")
                return True
            elif str(current_id) != str(telegram_id):
                # Если ID не совпадает, обновляем
                sheet.update_cell(row, 6, str(telegram_id))
                logger.info(f"Обновлен Telegram ID с {current_id} на {telegram_id} для @{username}")
                return True
        return False
    except Exception as e:
        logger.error(f"Ошибка при обновлении Telegram ID: {e}")
        return False

# Функция поиска пользователя в таблице
def find_user(user_id, username):
    """Ищет пользователя сначала по Telegram ID, затем по юзернейму"""
    try:
        # Сначала ищем по Telegram ID в колонке F (6-й столбец)
        cell = sheet.find(str(user_id), in_column=6)
        if cell:
            row = cell.row
            status = sheet.cell(row, 4).value
            logger.info(f"Найден пользователь по Telegram ID {user_id} в строке {row}")
            return {'row': row, 'uid': sheet.cell(row, 1).value, 'status': status}
    except Exception as e:
        logger.debug(f"Пользователь с ID {user_id} не найден по Telegram ID: {e}")
    
    # Если не найден по ID, ищем по юзернейму в колонке G (7-й столбец)
    if username:
        try:
            cell = sheet.find(f"@{username}", in_column=7)
            if cell:
                row = cell.row
                logger.info(f"Найден пользователь @{username} в строке {row}")
                # Обновляем Telegram ID
                update_telegram_id(username, user_id)
                # Проверяем статус
                status = sheet.cell(row, 4).value
                return {'row': row, 'uid': sheet.cell(row, 1).value, 'status': status}
        except Exception as e:
            logger.debug(f"Пользователь @{username} не найден: {e}")
    
    return None

# Вспомогательная функция для проверки, не создает ли убийство цикл
def would_create_cycle(killer_row, target_row):
    """
    Проверяет, не создаст ли убийство цикл.
    Возвращает True, если убийство создаст цикл (когда цель является убийцей киллера)
    """
    try:
        # Получаем UID киллера и цели
        killer_uid = sheet.cell(killer_row, 1).value
        target_uid = sheet.cell(target_row, 1).value
        
        # Проверяем, не является ли цель убийцей киллера
        # Ищем, кто должен убить киллера (чей target = killer_uid)
        try:
            # Ищем строку, где цель = killer_uid
            killer_target_cell = sheet.find(killer_uid, in_column=3)
            if killer_target_cell:
                # Это строка того, кто должен убить киллера
                potential_killer_row = killer_target_cell.row
                potential_killer_uid = sheet.cell(potential_killer_row, 1).value
                
                # Проверяем, жив ли потенциальный убийца
                potential_killer_status = sheet.cell(potential_killer_row, 4).value
                
                # Если потенциальный убийца жив и это тот, кого пытаются убить
                if potential_killer_status == 'alive' and potential_killer_uid == target_uid:
                    logger.info(f"Обнаружен цикл! {target_uid} должен убить {killer_uid}")
                    return True
        except:
            pass
            
        return False
    except Exception as e:
        logger.error(f"Ошибка при проверке цикла: {e}")
        return False

# Вспомогательная функция для отправки сообщения убитому пользователю
async def notify_killed_user(killed_uid, killer_name):
    try:
        # Находим строку убитого пользователя
        killed_row = sheet.find(killed_uid, in_column=1).row
        # Проверяем, есть ли у него зарегистрированный Telegram ID
        try:
            telegram_id_cell = sheet.cell(killed_row, 6).value  # Колонка F для Telegram ID
            if telegram_id_cell and telegram_id_cell.isdigit():
                killed_user_id = int(telegram_id_cell)
                try:
                    await bot.send_message(
                        killed_user_id,
                        f"Вас убил игрок {killer_name}! Вы выбыли из игры. \n\n"
                        f"Вы можете наблюдать за игрой, но больше не можете участвовать.\n"
                        f"Доступные команды: /info"
                    )
                except Exception as e:
                    logger.error(f"Не удалось отправить сообщение убитому пользователю {killed_user_id}: {e}")
        except:
            pass  # Если нет колонки F или она пуста, просто пропускаем
    except Exception as e:
        logger.error(f"Ошибка при уведомлении убитого пользователя: {e}")

@start_router.message(Command('start'))
async def start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    logger.info(f"Команда /start от пользователя {user_id} (@{username})")
    
    # Проверяем, не зарегистрирован ли уже пользователь в памяти бота
    if user_id in users:
        logger.info(f"Пользователь {user_id} уже в памяти бота")
        await message.reply("Вы уже зарегистрированы в игре!")
        return
    
    # Ищем пользователя в таблице (сначала по ID, потом по юзернейму)
    user_data = find_user(user_id, username)
    
    if user_data:
        # Пользователь найден
        users[user_id] = {'uid': user_data['uid'], 'row': user_data['row']}
        
        # Обновляем никнейм в колонке G, если он изменился
        try:
            first_row = sheet.row_values(1)
            if len(first_row) >= 7 and username:
                current_username = sheet.cell(user_data['row'], 7).value
                if current_username != f"@{username}":
                    sheet.update_cell(user_data['row'], 7, f"@{username}")
                    logger.info(f"Обновлен никнейм для пользователя {user_id}: @{username}")
        except Exception as e:
            logger.error(f"Ошибка при обновлении никнейма: {e}")
        
        if user_data['status'] == 'alive':
            await message.reply(
                f"Добро пожаловать, {first_name}! Вы успешно авторизованы.\n\n"
                "Вот доступные команды:\n"
                "/target - показать текущую цель\n"
                "/kill <uid> - подтвердить убийство цели\n"
                "/myid - показать ваш UID\n"
                "/info - правила игры"
            )
        else:
            await message.reply(
                f"Вы успешно авторизованы, но {first_name}, вы уже мертвы!\n"
                "Доступные команды: /info"
            )
        return
    
    # Если пользователь не найден, предлагаем войти по UID
    logger.info(f"Пользователь {user_id} не найден в таблице, предлагаем ввести UID")
    await message.reply(
        "Добро пожаловать в игру 'Киллер'!\n\n"
        "Вы не найдены в базе игроков. "
        "Если вы уже зарегистрированы, введите ваш уникальный идентификатор (UID).\n\n"
        "Если вы еще не зарегистрированы, обратитесь к администратору."
    )
    users[user_id] = {'status': 'waiting_for_id'}

@start_router.message(Command('target'))
async def target(message: types.Message):
    user_id = message.from_user.id
    
    # Проверяем, зарегистрирован ли пользователь
    if user_id not in users:
        await message.reply("Вы не вошли в игру. Пожалуйста, используйте /start для входа.")
        return
    
    # Проверяем, жив ли пользователь
    if not is_user_alive(user_id):
        await message.reply("Вы мертвы и не можете получить цель. Доступные команды: /info")
        return
    
    try:
        target_uid = sheet.cell(users[user_id]['row'], 3).value  # Колонка C - цель
        if not target_uid:
            await message.reply("У вас пока нет цели. Ожидайте назначения.")
            return
            
        target_row = sheet.find(target_uid, in_column=1).row
        target_name = sheet.cell(target_row, 2).value  # Колонка B - имя
        await message.reply(f"Ваша текущая цель: {target_name}")
    except Exception as e:
        logger.error(f"Ошибка в /target: {e}")
        await message.reply("Произошла ошибка при получении цели. Попробуйте позже.")

@start_router.message(Command('kill'))
async def kill(message: types.Message):
    user_id = message.from_user.id
    
    # Проверяем, зарегистрирован ли пользователь
    if user_id not in users:
        await message.reply("Вы не вошли в игру. Пожалуйста, используйте /start для входа.")
        return
    
    # Проверяем, жив ли пользователь
    if not is_user_alive(user_id):
        await message.reply("Вы мертвы и не можете совершать убийства. Доступные команды: /info")
        return
    
    try:
        # Разбираем команду /kill <uid>
        parts = message.text.split()
        if len(parts) < 2:
            await message.reply("Пожалуйста, введите UID цели. Пример: /kill <uid>")
            return
            
        target_uid = parts[1]
        
        # Проверяем, что цель существует и жива
        try:
            target_row = sheet.find(target_uid, in_column=1).row
            target_status = sheet.cell(target_row, 4).value
            if target_status != 'alive':
                await message.reply("Эта цель уже мертва или неактивна.")
                return
        except gspread.exceptions.CellNotFound:
            await message.reply("Указанный UID не найден. Пожалуйста, попробуйте снова.")
            return
        
        # Проверяем, что это действительно цель пользователя
        killer_row = users[user_id]['row']
        current_target_uid = sheet.cell(killer_row, 3).value
        if target_uid != current_target_uid:
            await message.reply("UID не соответствует вашей текущей цели. Попробуйте снова.")
            return
        
        # ПРОВЕРКА НА СОЗДАНИЕ ЦИКЛА
        if would_create_cycle(killer_row, target_row):
            logger.warning(f"Попытка создать цикл! Пользователь {user_id} пытается убить {target_uid}")
            await message.reply(
                "Вы не можете убить этого игрока, так как он должен убить вас!"
            )
            return
        
        # Получаем имя убийцы для уведомления
        killer_name = sheet.cell(killer_row, 2).value  # Колонка B - имя
        
        # Сохраняем UID следующей цели убитого перед его удалением
        next_target_uid = sheet.cell(target_row, 3).value
        
        # Обновляем статус убитого на "dead"
        sheet.update_cell(target_row, 4, "dead")
        
        # Красим ВСЮ строку убитого до столбца Q в красный с белым текстом
        color_dead(target_row)
        
        # Очищаем цель у убитого
        sheet.update_cell(target_row, 3, "")
        
        # Увеличиваем счетчик убийств убийцы
        kill_count_cell = sheet.cell(killer_row, 5)  # Колонка E - количество убийств
        kill_count = int(kill_count_cell.value) if kill_count_cell.value else 0
        sheet.update_cell(killer_row, 5, kill_count + 1)
        
        # Назначаем убийце новую цель (следующую цель убитого)
        if next_target_uid:
            # Проверяем, жива ли новая цель
            try:
                next_target_row = sheet.find(next_target_uid, in_column=1).row
                next_target_status = sheet.cell(next_target_row, 4).value
                if next_target_status == 'alive':
                    sheet.update_cell(killer_row, 3, next_target_uid)
                    await message.reply(
                        f"Убийство подтверждено! Ваша новая цель: {sheet.cell(next_target_row, 2).value}"
                    )
                else:
                    # Если следующая цель мертва, очищаем цель
                    sheet.update_cell(killer_row, 3, "")
                    await message.reply(
                        "Убийство подтверждено! Но ваша следующая цель мертва. "
                        "Ожидайте, пока администратор назначит новую цель."
                    )
            except gspread.exceptions.CellNotFound:
                sheet.update_cell(killer_row, 3, "")
                await message.reply(
                    "Убийство подтверждено! Но следующая цель не найдена. "
                    "Ожидайте, пока администратор назначит новую цель."
                )
        else:
            # Если у убитого не было цели, очищаем цель убийцы
            sheet.update_cell(killer_row, 3, "")
            await message.reply(
                "Убийство подтверждено! Цепочка убийств завершена. "
                "Ожидайте, пока администратор назначит новую цель."
            )
        
        # Отправляем уведомление убитому пользователю
        await notify_killed_user(target_uid, killer_name)
        
    except IndexError:
        await message.reply("Пожалуйста, введите UID цели. Пример: /kill <uid>")
    except Exception as e:
        logger.error(f"Ошибка в /kill: {e}")
        await message.reply("UID не соответствует вашей текущей цели. Попробуйте снова.")

@start_router.message(Command('myid'))
async def myid(message: types.Message):
    user_id = message.from_user.id
    
    # Проверяем, зарегистрирован ли пользователь
    if user_id not in users:
        await message.reply("Вы не вошли в игру. Пожалуйста, используйте /start для входа.")
        return
    
    try:
        # Получаем только UID пользователя
        row = users[user_id]['row']
        uid = sheet.cell(row, 1).value  # Колонка A - UID
        
        # Отправляем только UID
        await message.reply(f"Ваш UID: {uid}")
        
    except Exception as e:
        logger.error(f"Ошибка в /myid: {e}")
        await message.reply("Произошла ошибка при получении вашего UID. Попробуйте позже.")

@start_router.message(Command('info'))
async def info(message: types.Message):
    await message.reply(
        """
Всем привет! Хотите почувствовать себя секретным агентом или хладнокровным (но очень вежливым!) киллером? Тогда слушайте внимательно! С понедельника стартует легендарная лагерная игра "КИЛЛЕР"!

Суть игры проста до невозможности:

   Твоя цель: Стать последним выжившим! Для этого тебе нужно "устранить" свою цель.

Как играем:

   Каждый игрок получает свою первую "жертву" (это будет тайный код, а не имя!).
   Твоя задача – найти её и... "ликвидировать".

Что такое "УБИЙСТВО"? Всё очень цивилизованно! Чтобы "убить" цель, ты должен:

1.  Легко коснуться её ПЛЕЧА.
2.  Четко сказать: "Ты убит(а)!".
3.  ВАЖНОЕ ДОПОЛНЕНИЕ! "Убийство" должно быть СЕКРЕТНЫМ!
       Если вы в помещении (комната, холл и т.д.): В этом помещении, кроме вас двоих, НИКОГО НЕ ДОЛЖНО БЫТЬ!
       Если вы на улице: В обозримой близости (примерно 30 метров вокруг) НЕ ДОЛЖНО БЫТЬ ДРУГИХ ИГРОКОВ (свидетелей). Следите за окружением!
       Ш-ш-ш! Операция секретная!

Что делать ПОСЛЕ "убийства"? Это ключевой момент!

1.  "Убитая" жертва ОБЯЗАНА назвать тебе СВОЙ УНИКАЛЬНЫЙ КОД.
2.  Ты заходишь в нашего специального Telegram-бота.
3.  Вводишь этот код – и бот мгновенно выдает тебе новую цель! Цепочка продолжается!

Кто побеждает?

   Тот, кто останется последним неубитым агентом!
   А ТОП-5 самых результативных киллеров получат КРУТЫЕ ПРИЗЫ! (Если финалистов меньше – призы станут еще лучше!).

Внимание! БЕЗОПАСНОСТЬ и ПРАВИЛА – ЭТО СВЯТОЕ! Нарушил – вылетел!

ГДЕ НЕЛЬЗЯ "убивать" (ЗАПРЕТНЫЕ ЗОНЫ):

   Внутри Ресторана (столовой) – кушаем спокойно!
   В воде (бассейн, море, озеро) – безопасность на воде прежде всего!
   В туалетах – личное пространство!

КОГДА НЕЛЬЗЯ "убивать" (ЗАПРЕТНОЕ ВРЕМЯ):

   После отбоя и до подъема (ночью и рано утром) – спим!
   Во время любых учебных занятий – учимся!
   Во время еды – едим без спешки!

СТРОГИЕ ЗАПРЕТЫ:

   Никакой грубости, толкания, драк, хватаний за одежду/руки/волосы! Только легкое касание плеча!
   Нельзя кричать или ругаться! Сказал четко "Ты убит(а)" – и всё.
   Нельзя мешать занятиям, мероприятиям!
   НЕЛЬЗЯ забывать общие правила поведения в лагере из-за игры! Игра – не оправдание!
   Нельзя "убивать" на лестницах или в других потенциально опасных местах!

Что делать "УБИТОМУ"?

1.  Немедленно остановись! Ты выбываешь из активной охоты.
2.  ОБЯЗАТЕЛЬНО назови свой код тому, кто тебя "убил"! Без кода он не получит новую цель.
3.  Дальше можешь просто наблюдать или болеть, но охотиться – нельзя!

Важные детали и фишки:

   Регистрация: Игра добровольная и только для тех, кто закончил 6 класс и старше!
   Как записаться? Подходишь к QR-коду, который висит перед Рестораном! Отсканируешь – попадешь в Google Форму. Заполняешь – и ты в игре! Регистрация открыта СЕЙЧАС!
   Старт игры: Все зарегистрированные игроки получат доступ к Telegram-боту и свои первые цели в ПОНЕДЕЛЬНИК! Старт – по сигналу!
   Конец игры: Игра продлится до начала Зачета (конкретную дату/время объявим позже). Победитель и ТОП-5 будут объявлены в конце смены!
   Объединяться? Да, можно! Договаривайся, создавай альянсы, строй коварные планы – это часть стратегии! Но помни: в итоге победить может только один!
   Что если цель уехала/уходит? Автоматическое "убийство"! Твоя новая цель появится в боте.
   Хочешь выйти из игры? Можно! Подойди или напиши в Telegram (@varohooka) Ковалёву Алексею.
   Спорная ситуация? Нарушение правил? Окончательное решение – за Ковалёвым Алексеем (@varohooka)! Его слово – закон. Все "убийства" и передачи целей фиксируются ботом, это главный свидетель.

Итог:

Это игра на внимательность, хитрость и скорость! Но помни: безопасность и честность – на первом месте! Регистрируйся по QR-коду у Ресторана, готовься к старту в понедельник и... пусть победит самый осторожный и удачливый агент! Вперед!
    """)

@start_router.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text
    
    logger.info(f"Получено сообщение от {user_id}: {text}")

    # Проверяем, ожидает ли пользователь ввод UID
    if users.get(user_id, {}).get('status') == 'waiting_for_id':
        logger.info(f"Пользователь {user_id} ожидает ввод UID")
        try:
            # Ищем UID в первом столбце
            cell = sheet.find(text, in_column=1)
            if cell is None:
                await message.reply("Указанный UID не найден. Пожалуйста, попробуйте снова.")
                return
            
            row = cell.row
            logger.info(f"Найден UID {text} в строке {row}")
            
            # Проверяем, не привязан ли уже этот аккаунт к другому Telegram ID
            try:
                telegram_id_cell = sheet.cell(row, 6).value  # Колонка F для Telegram ID
                if telegram_id_cell and telegram_id_cell.isdigit():
                    existing_user_id = int(telegram_id_cell)
                    logger.info(f"UID {text} уже привязан к Telegram ID {existing_user_id}")
                    # Проверяем, не зарегистрирован ли уже этот пользователь в боте
                    if existing_user_id in users:
                        await message.reply(
                            "Этот UID уже зарегистрирован в боте. "
                            "Пожалуйста, используйте /start с того аккаунта, который вы зарегистрировали."
                        )
                        return
            except Exception as e:
                logger.error(f"Ошибка при проверке Telegram ID: {e}")
            
            # Проверяем статус игрока
            status = sheet.cell(row, 4).value
            
            # Сохраняем данные пользователя в память
            users[user_id] = {'uid': text, 'row': row}
            
            # Получаем первую строку для проверки количества колонок
            first_row = sheet.row_values(1)
            logger.info(f"Количество колонок в таблице: {len(first_row)}")
            
            # Сохраняем Telegram ID в таблицу (колонка F)
            try:
                if len(first_row) >= 6:
                    sheet.update_cell(row, 6, str(user_id))
                    logger.info(f"Сохранен Telegram ID {user_id} для UID {text} в колонку F (строка {row})")
                else:
                    logger.warning(f"В таблице меньше 6 колонок! Сейчас: {len(first_row)}")
            except Exception as e:
                logger.error(f"Ошибка при сохранении Telegram ID: {e}")
            
            # Сохраняем никнейм пользователя (с @) в колонку G, если есть
            try:
                username = message.from_user.username
                if username and len(first_row) >= 7:
                    sheet.update_cell(row, 7, f"@{username}")
                    logger.info(f"Сохранен никнейм @{username} для UID {text} в колонку G (строка {row})")
                elif username and len(first_row) < 7:
                    logger.warning(f"В таблице меньше 7 колонок! Сейчас: {len(first_row)}")
            except Exception as e:
                logger.error(f"Ошибка при сохранении никнейма: {e}")
            
            # Красим ВСЮ строку до столбца Q в зеленый с черным текстом, если игрок жив
            if status == 'alive':
                color_alive(row)
            
            if status == 'alive':
                await message.reply(
                    "Вы успешно вошли! Вот доступные команды:\n"
                    "/target - показать текущую цель\n"
                    "/kill <uid> - подтвердить убийство цели\n"
                    "/myid - показать ваш UID\n"
                    "/info - правила игры"
                )
            else:
                await message.reply(
                    "Вы успешно вошли, но вы уже мертвы!\n"
                    "Доступные команды: /info"
                )
                
        except gspread.exceptions.CellNotFound:
            await message.reply("Указанный UID не найден. Пожалуйста, попробуйте снова.")
        except Exception as e:
            logger.error(f"Ошибка в handle_message: {e}")
            await message.reply("Произошла ошибка. Попробуйте позже.")
    else:
        # Если пользователь уже зарегистрирован, но отправляет обычное сообщение
        if user_id in users:
            await message.reply(
                "Пожалуйста, используйте команды для взаимодействия с ботом:\n"
                "/target - показать текущую цель\n"
                "/kill <uid> - подтвердить убийство цели\n"
                "/myid - показать ваш UID\n"
                "/info - правила игры"
            )
        else:
            await message.reply(
                "Пожалуйста, начните с команды /start для входа в игру."
            )

# Запуск процесса поллинга новых апдейтов
async def main():
    dp.include_router(start_router)
    
    # Обновляем цвета всех строк при запуске бота
    logger.info("Обновление цветов строк...")
    update_all_colors()
    logger.info("Бот запущен!")
    
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())