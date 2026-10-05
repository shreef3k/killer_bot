import logging
import asyncio
import os
import random
import string
import time
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Получаем значения переменных
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # ID администратора для подтверждения

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Настройка доступа к Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
client = gspread.authorize(creds)

# Открытие Google таблиц
try:
    registrations_sheet = client.open('Регистрация на игру Киллер').sheet1
    logger.info("✅ Таблица 'Регистрация на игру Киллер' найдена")
except Exception as e:
    logger.error(f"❌ Таблица 'Регистрация на игру Киллер' не найдена: {e}")
    try:
        registrations_sheet = client.open('Регистрация на игру "Киллер"').sheet1
        logger.info("✅ Таблица 'Регистрация на игру \"Киллер\"' найдена")
    except:
        logger.error("❌ Таблица регистраций не найдена! Проверьте название.")
        exit(1)

try:
    players_sheet = client.open("Игра в киллера").sheet1
    logger.info("✅ Таблица 'Игра в киллера' найдена")
except Exception as e:
    logger.error(f"❌ Таблица 'Игра в киллера' не найдена: {e}")
    exit(1)

# Инициализация бота
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# --- РАБОТА С SQLite ---
DB_PATH = 'registrations.db'

def init_db():
    """Инициализация базы данных"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Проверяем, существует ли таблица
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pending_registrations'")
        table_exists = cursor.fetchone()
        
        if table_exists:
            # Проверяем структуру таблицы
            cursor.execute("PRAGMA table_info(pending_registrations)")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]
            logger.info(f"Существующие колонки в БД: {column_names}")
            
            # Если структура не совпадает, пересоздаем таблицу
            expected_columns = ['reg_id', 'full_name', 'class', 'group_name', 'username', 'uid', 'status', 'message_id', 'processed_date', 'created_at']
            if set(column_names) != set(expected_columns):
                logger.warning("Структура таблицы не совпадает. Пересоздаем...")
                cursor.execute("DROP TABLE pending_registrations")
                table_exists = None
        
        if not table_exists:
            # Создаем таблицу заново
            cursor.execute('''
                CREATE TABLE pending_registrations (
                    reg_id TEXT PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    class TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    username TEXT NOT NULL,
                    uid TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    message_id TEXT,
                    processed_date TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            logger.info("✅ Таблица создана")
        
        conn.commit()
        conn.close()
        logger.info("✅ База данных инициализирована")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка при инициализации БД: {e}")
        return False

def save_pending_to_db(reg_id, data):
    """Сохранение заявки в базу данных"""
    try:
        logger.info(f"Пытаемся сохранить заявку #{reg_id} в БД")
        logger.info(f"Данные: {data}")
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO pending_registrations (
                reg_id, full_name, class, group_name, username, uid, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            reg_id,
            data['full_name'],
            data['class'],
            data['group'],
            data['username'],
            data['uid'],
            'pending'
        ))
        
        conn.commit()
        conn.close()
        logger.info(f"✅ Заявка #{reg_id} сохранена в БД")
        return True
    except sqlite3.IntegrityError as e:
        logger.error(f"❌ Ошибка целостности БД: {e} - возможно, заявка уже существует")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка при сохранении заявки в БД: {e}")
        return False

def update_pending_status(reg_id, status, message_id=None):
    """Обновление статуса заявки"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if message_id:
            cursor.execute('''
                UPDATE pending_registrations 
                SET status = ?, message_id = ?, processed_date = ?
                WHERE reg_id = ?
            ''', (status, str(message_id), datetime.now().isoformat(), reg_id))
        else:
            cursor.execute('''
                UPDATE pending_registrations 
                SET status = ?, processed_date = ?
                WHERE reg_id = ?
            ''', (status, datetime.now().isoformat(), reg_id))
        
        conn.commit()
        conn.close()
        logger.info(f"✅ Статус заявки #{reg_id} обновлен на {status}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении статуса заявки: {e}")
        return False

def get_pending_registrations():
    """Получение всех ожидающих заявок"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM pending_registrations 
            WHERE status = 'pending' 
            ORDER BY created_at ASC
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        pending_list = []
        for row in rows:
            pending_list.append({
                'reg_id': row[0],
                'full_name': row[1],
                'class': row[2],
                'group': row[3],
                'username': row[4],
                'uid': row[5],
                'status': row[6],
                'message_id': row[7] if len(row) > 7 else None,
                'processed_date': row[8] if len(row) > 8 else None,
                'created_at': row[9] if len(row) > 9 else None
            })
        
        return pending_list
    except Exception as e:
        logger.error(f"❌ Ошибка при получении заявок из БД: {e}")
        return []

def get_pending_by_id(reg_id):
    """Получение заявки по ID"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM pending_registrations 
            WHERE reg_id = ?
        ''', (reg_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'reg_id': row[0],
                'full_name': row[1],
                'class': row[2],
                'group': row[3],
                'username': row[4],
                'uid': row[5],
                'status': row[6],
                'message_id': row[7] if len(row) > 7 else None,
                'processed_date': row[8] if len(row) > 8 else None,
                'created_at': row[9] if len(row) > 9 else None
            }
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка при получении заявки из БД: {e}")
        return None

def is_pending_exists(username):
    """Проверка существования заявки для пользователя"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) FROM pending_registrations 
            WHERE username = ? AND status = 'pending'
        ''', (username,))
        
        count = cursor.fetchone()[0]
        conn.close()
        
        return count > 0
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке заявки в БД: {e}")
        return False

def get_pending_count():
    """Получение количества ожидающих заявок"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) FROM pending_registrations 
            WHERE status = 'pending'
        ''')
        
        count = cursor.fetchone()[0]
        conn.close()
        
        return count
    except Exception as e:
        logger.error(f"❌ Ошибка при подсчете заявок в БД: {e}")
        return 0

# --- ОСНОВНЫЕ ФУНКЦИИ БОТА ---

# Функция генерации случайного UID
def generate_uid():
    """Генерирует случайный уникальный UID из 8 символов"""
    characters = string.ascii_uppercase + string.digits
    uid = ''.join(random.choices(characters, k=8))
    return uid

# Функция проверки уникальности UID
def is_uid_unique(uid):
    try:
        # Проверяем, существует ли уже такой UID в таблице игроков
        cell = players_sheet.find(uid, in_column=1)
        return cell is None
    except Exception as e:
        logger.error(f"Ошибка при проверке уникальности UID: {e}")
        return True

# Функция получения уникального UID
def get_unique_uid():
    max_attempts = 10
    for _ in range(max_attempts):
        uid = generate_uid()
        if is_uid_unique(uid):
            return uid
    # Если не удалось сгенерировать уникальный UID, используем время + случайное число
    return f"UID{int(time.time())}{random.randint(100, 999)}"

# Функция проверки, зарегистрирован ли уже пользователь
def is_user_registered(username):
    try:
        if not username:
            return False
        cell = players_sheet.find(f"@{username}", in_column=7)
        return cell is not None
    except Exception as e:
        logger.error(f"Ошибка при проверке регистрации пользователя: {e}")
        return False

# Функция сохранения игрока в таблицу
def save_player_to_sheet(uid, full_name, username=None):
    try:
        # Находим последнюю заполненную строку
        all_values = players_sheet.get_all_values()
        next_row = len(all_values) + 1
        
        # Подготавливаем данные
        row_data = [
            uid,                    # Колонка A: UID
            full_name,              # Колонка B: ФИО
            "",                     # Колонка C: Цель (пока пусто)
            "alive",                # Колонка D: Статус
            0,                      # Колонка E: Убийств
            "",                     # Колонка F: Telegram ID (пока пусто)
            f"@{username}" if username else ""  # Колонка G: Никнейм
        ]
        
        # Обновляем строку
        players_sheet.update(f'A{next_row}:G{next_row}', [row_data])
        logger.info(f"✅ Игрок {full_name} (UID: {uid}, @{username}) сохранен в таблицу")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка при сохранении игрока в таблицу: {e}")
        return False

# --- КОМАНДЫ БОТА ---

@dp.message(Command('start'))
async def start(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        pending_count = get_pending_count()
        
        await message.reply(
            f"👋 Привет, администратор!\n\n"
            f"Я бот-регистратор для игры 'Киллер'.\n"
            f"Новые заявки будут приходить сюда на подтверждение.\n\n"
            f"📊 Текущий статус:\n"
            f"⏳ Ожидает подтверждения: {pending_count}\n\n"
            f"Команды:\n"
            f"/pending - показать все ожидающие заявки\n"
            f"/stats - статистика игроков\n"
            f"/resend - переотправить все ожидающие заявки\n"
            f"/test - создать тестовую заявку"
        )
    else:
        await message.reply(
            "👋 Привет! Этот бот предназначен для администраторов игры 'Киллер'.\n"
            "Если вы хотите зарегистрироваться, перейдите по ссылке: [ссылка на Google Form]"
        )

@dp.message(Command('pending'))
async def show_pending(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ У вас нет прав для этой команды.")
        return
    
    pending = get_pending_registrations()
    
    if not pending:
        await message.reply("📭 Нет ожидающих заявок.")
        return
    
    text = "📋 **Ожидающие заявки:**\n\n"
    for data in pending:
        text += f"🔹 **Заявка #{data['reg_id']}**\n"
        text += f"👤 {data['full_name']}\n"
        text += f"🏫 {data['class']} класс, {data['group']} отряд\n"
        text += f"📱 @{data['username']}\n"
        text += f"🆔 UID: `{data['uid']}`\n"
        text += f"📅 Создана: {data['created_at']}\n\n"
    
    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            await message.reply(part, parse_mode='Markdown')
    else:
        await message.reply(text, parse_mode='Markdown')

@dp.message(Command('resend'))
async def resend_pending(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ У вас нет прав для этой команды.")
        return
    
    pending = get_pending_registrations()
    
    if not pending:
        await message.reply("📭 Нет ожидающих заявок для переотправки.")
        return
    
    sent_count = 0
    for data in pending:
        try:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"approve_{data['reg_id']}"),
                    InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{data['reg_id']}")
                ]
            ])
            
            # Экранируем специальные символы для Markdown
            username_escaped = data['username'].replace('_', '\\_')
            
            msg = await bot.send_message(
                ADMIN_ID,
                f"📝 **Заявка на регистрацию #{data['reg_id']}**\n\n"
                f"👤 ФИО: {data['full_name']}\n"
                f"🏫 Класс: {data['class']}\n"
                f"👥 Отряд: {data['group']}\n"
                f"📱 Юзернейм: @{username_escaped}\n"
                f"🔑 UID: `{data['uid']}`\n"
                f"📅 Создана: {data['created_at']}\n\n"
                f"Пожалуйста, подтвердите или отклоните заявку:",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            
            update_pending_status(data['reg_id'], 'pending', msg.message_id)
            sent_count += 1
            
        except Exception as e:
            logger.error(f"Ошибка при переотправке заявки {data['reg_id']}: {e}")
    
    await message.reply(f"✅ Переотправлено {sent_count} заявок.")

@dp.message(Command('stats'))
async def show_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ У вас нет прав для этой команды.")
        return
    
    try:
        all_values = players_sheet.get_all_values()
        total_players = len(all_values) - 1
        
        alive_players = 0
        for row in all_values[1:]:
            if len(row) > 3 and row[3] == 'alive':
                alive_players += 1
        
        pending_count = get_pending_count()
        
        await message.reply(
            f"📊 **Статистика игры:**\n\n"
            f"👥 Всего игроков: {total_players}\n"
            f"🟢 Живых: {alive_players}\n"
            f"🔴 Мертвых: {total_players - alive_players}\n"
            f"⏳ Ожидает подтверждения: {pending_count}"
        )
    except Exception as e:
        logger.error(f"Ошибка в stats: {e}")
        await message.reply("❌ Ошибка при получении статистики.")

# --- ОБРАБОТЧИКИ КНОПОК ---

@dp.callback_query(lambda c: c.data.startswith('approve_'))
async def approve_registration(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("❌ У вас нет прав для этого действия.", show_alert=True)
        return
    
    reg_id = callback_query.data.replace('approve_', '')
    logger.info(f"✅ Подтверждение заявки #{reg_id}")
    
    # Получаем заявку из БД
    data = get_pending_by_id(reg_id)
    
    if not data:
        await callback_query.answer("❌ Заявка не найдена в БД.", show_alert=True)
        logger.error(f"❌ Заявка #{reg_id} не найдена в БД")
        return
    
    if data['status'] != 'pending':
        await callback_query.answer("❌ Заявка уже обработана.", show_alert=True)
        return
    
    # Сохраняем игрока в таблицу
    logger.info(f"Сохраняем игрока {data['full_name']} в таблицу")
    success = save_player_to_sheet(
        data['uid'],
        data['full_name'],
        data['username']
    )
    
    if success:
        # Обновляем статус заявки в БД
        update_pending_status(reg_id, 'approved')
        
        # Обновляем сообщение с заявкой
        try:
            # Экранируем спецсимволы
            username_escaped = data['username'].replace('_', '\\_')
            
            await callback_query.message.edit_text(
                f"✅ **Заявка #{reg_id} одобрена!**\n\n"
                f"👤 {data['full_name']}\n"
                f"🏫 {data['class']} класс, {data['group']} отряд\n"
                f"📱 @{username_escaped}\n"
                f"🆔 UID: `{data['uid']}`\n\n"
                f"Статус: ✅ ЗАРЕГИСТРИРОВАН",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Не удалось обновить сообщение: {e}")
        
        await callback_query.answer("✅ Заявка одобрена!")
    else:
        await callback_query.answer("❌ Ошибка при сохранении. Проверьте таблицу.", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith('reject_'))
async def reject_registration(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("❌ У вас нет прав для этого действия.", show_alert=True)
        return
    
    reg_id = callback_query.data.replace('reject_', '')
    logger.info(f"❌ Отклонение заявки #{reg_id}")
    
    data = get_pending_by_id(reg_id)
    
    if not data:
        await callback_query.answer("❌ Заявка не найдена в БД.", show_alert=True)
        return
    
    if data['status'] != 'pending':
        await callback_query.answer("❌ Заявка уже обработана.", show_alert=True)
        return
    
    update_pending_status(reg_id, 'rejected')
    
    try:
        username_escaped = data['username'].replace('_', '\\_')
        
        await callback_query.message.edit_text(
            f"❌ **Заявка #{reg_id} отклонена!**\n\n"
            f"👤 {data['full_name']}\n"
            f"🏫 {data['class']} класс, {data['group']} отряд\n"
            f"📱 @{username_escaped}\n\n"
            f"Статус: ❌ ОТКЛОНЕНА",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Не удалось обновить сообщение: {e}")
    
    await callback_query.answer("❌ Заявка отклонена!")

# --- МОНИТОРИНГ НОВЫХ ЗАЯВОК ---

async def check_new_registrations():
    """Проверяет новые записи в Google Sheets и отправляет на подтверждение"""
    last_checked_row = 1
    
    while True:
        try:
            all_values = registrations_sheet.get_all_values()
            
            if not all_values or len(all_values) <= 1:
                await asyncio.sleep(10)
                continue
            
            for i in range(last_checked_row, len(all_values)):
                row = all_values[i]
                
                if i == 0:
                    continue
                
                if len(row) < 5:
                    continue
                
                full_name = row[1].strip() if len(row) > 1 else ""
                class_num = row[2].strip() if len(row) > 2 else ""
                group = row[3].strip() if len(row) > 3 else ""
                username = row[4].strip().replace('@', '') if len(row) > 4 else ""
                
                if not full_name or not username:
                    logger.warning(f"Неполные данные в строке {i+1}: {row}")
                    continue
                
                try:
                    # Проверяем регистрацию
                    if is_user_registered(username):
                        logger.info(f"Пользователь @{username} уже зарегистрирован")
                        continue
                    
                    if is_pending_exists(username):
                        logger.info(f"У пользователя @{username} уже есть заявка")
                        continue
                    
                    uid = get_unique_uid()
                    reg_id = f"REG{int(time.time())}{random.randint(100, 999)}"
                    
                    data = {
                        'full_name': full_name,
                        'class': class_num,
                        'group': group,
                        'username': username,
                        'uid': uid
                    }
                    
                    # Сохраняем в БД
                    if save_pending_to_db(reg_id, data):
                        logger.info(f"✅ Заявка #{reg_id} сохранена")
                        
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[
                            [
                                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"approve_{reg_id}"),
                                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{reg_id}")
                            ]
                        ])
                        
                        # Экранируем спецсимволы для Markdown
                        username_escaped = username.replace('_', '\\_')
                        full_name_escaped = full_name.replace('_', '\\_')
                        class_num_escaped = class_num.replace('_', '\\_')
                        group_escaped = group.replace('_', '\\_')
                        
                        msg = await bot.send_message(
                            ADMIN_ID,
                            f"📝 **Новая заявка на регистрацию!**\n\n"
                            f"📋 ID заявки: `{reg_id}`\n"
                            f"👤 ФИО: {full_name_escaped}\n"
                            f"🏫 Класс: {class_num_escaped}\n"
                            f"👥 Отряд: {group_escaped}\n"
                            f"📱 Юзернейм: @{username_escaped}\n"
                            f"🔑 UID: `{uid}`\n\n"
                            f"Пожалуйста, подтвердите или отклоните заявку:",
                            reply_markup=keyboard,
                            parse_mode='Markdown'
                        )
                        
                        update_pending_status(reg_id, 'pending', msg.message_id)
                    else:
                        logger.error(f"❌ Не удалось сохранить заявку #{reg_id}")
                    
                except Exception as e:
                    logger.error(f"Ошибка при обработке заявки в строке {i+1}: {e}")
            
            if len(all_values) > last_checked_row:
                last_checked_row = len(all_values)
            
        except Exception as e:
            logger.error(f"Ошибка в check_new_registrations: {e}")
        
        await asyncio.sleep(10)

@dp.message(Command('test'))
async def test_registration(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ У вас нет прав для этой команды.")
        return
    
    reg_id = f"TEST{int(time.time())}"
    
    data = {
        'full_name': 'Тестовый Пользователь',
        'class': '6',
        'group': '1',
        'username': 'testuser',
        'uid': get_unique_uid()
    }
    
    if save_pending_to_db(reg_id, data):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"approve_{reg_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{reg_id}")
            ]
        ])
        
        msg = await message.reply(
            f"📝 **Тестовая заявка на регистрацию!**\n\n"
            f"📋 ID заявки: `{reg_id}`\n"
            f"👤 ФИО: Тестовый Пользователь\n"
            f"🏫 Класс: 6\n"
            f"👥 Отряд: 1\n"
            f"📱 Юзернейм: @testuser\n"
            f"🔑 UID: `{data['uid']}`\n\n"
            f"Пожалуйста, подтвердите или отклоните заявку:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        
        update_pending_status(reg_id, 'pending', msg.message_id)
    else:
        await message.reply("❌ Ошибка при создании тестовой заявки")

async def main():
    # Инициализируем базу данных
    if init_db():
        logger.info("✅ БД готова к работе")
    else:
        logger.error("❌ Ошибка инициализации БД")
        return
    
    # Запускаем проверку новых заявок
    asyncio.create_task(check_new_registrations())
    
    # Запускаем бота
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())