import gspread
from oauth2client.service_account import ServiceAccountCredentials
import random
import logging
from dotenv import load_dotenv
import os

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Настройка доступа к Google Sheets
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE")
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def shuffle_and_assign_targets():
    """Перемешивает живых игроков и назначает цели"""
    try:
        # Авторизация
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        
        # Открываем таблицу
        sheet = client.open("Игра в киллера").sheet1
        
        # Получаем все данные
        all_data = sheet.get_all_values()
        
        if len(all_data) <= 1:
            logger.warning("Таблица пуста или содержит только заголовки")
            return False
        
        # Заголовки (первая строка)
        headers = all_data[0]
        logger.info(f"Заголовки: {headers}")
        
        # Собираем живых игроков
        alive_players = []
        for i, row in enumerate(all_data[1:], start=2):  # start=2 потому что строки в Google Sheets начинаются с 1
            if len(row) > 3 and row[3].strip().lower() == 'alive':  # Колонка D - статус
                uid = row[0].strip() if len(row) > 0 else ""
                name = row[1].strip() if len(row) > 1 else ""
                if uid and name:
                    alive_players.append({
                        'row': i,
                        'uid': uid,
                        'name': name
                    })
        
        if len(alive_players) < 2:
            logger.warning(f"Недостаточно живых игроков для назначения целей. Найдено: {len(alive_players)}")
            return False
        
        logger.info(f"Найдено живых игроков: {len(alive_players)}")
        for p in alive_players:
            logger.info(f"  - {p['name']} (UID: {p['uid']})")
        
        # Перемешиваем игроков
        shuffled = alive_players.copy()
        random.shuffle(shuffled)
        
        logger.info("Игроки перемешаны:")
        for i, p in enumerate(shuffled):
            logger.info(f"  {i+1}. {p['name']} (UID: {p['uid']})")
        
        # Назначаем цели
        assignments = []
        for i in range(len(shuffled)):
            current = shuffled[i]
            # Цель - следующий игрок, или первый если это последний
            target = shuffled[(i + 1) % len(shuffled)]
            
            assignments.append({
                'uid': current['uid'],
                'row': current['row'],
                'target_uid': target['uid'],
                'target_name': target['name']
            })
        
        # Обновляем таблицу
        logger.info("Назначение целей:")
        for assignment in assignments:
            sheet.update_cell(assignment['row'], 3, assignment['target_uid'])  # Колонка C - цель
            logger.info(f"  {assignment['uid']} -> {assignment['target_uid']} ({assignment['target_name']})")
        
        logger.info(f"Успешно назначены цели для {len(assignments)} игроков")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return False

def clear_all_targets():
    """Очищает все цели в таблице"""
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open("Игра в киллера").sheet1
        
        all_data = sheet.get_all_values()
        if len(all_data) <= 1:
            logger.warning("Таблица пуста")
            return False
        
        # Очищаем колонку C для всех строк (кроме заголовка)
        for i in range(2, len(all_data) + 1):
            sheet.update_cell(i, 3, "")
        
        logger.info("Все цели очищены")
        return True
    except Exception as e:
        logger.error(f"Ошибка при очистке целей: {e}")
        return False

def show_current_targets():
    """Показывает текущие цели игроков"""
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open("Игра в киллера").sheet1
        
        all_data = sheet.get_all_values()
        if len(all_data) <= 1:
            logger.warning("Таблица пуста")
            return
        
        logger.info("Текущие цели игроков:")
        logger.info("-" * 50)
        for i, row in enumerate(all_data[1:], start=2):
            if len(row) > 3:
                uid = row[0].strip() if len(row) > 0 else "-"
                name = row[1].strip() if len(row) > 1 else "-"
                target_uid = row[2].strip() if len(row) > 2 else "-"
                status = row[3].strip() if len(row) > 3 else "-"
                
                if status.lower() == 'alive':
                    target_name = "-"
                    if target_uid != "-" and target_uid:
                        # Ищем имя цели
                        for r in all_data[1:]:
                            if len(r) > 0 and r[0].strip() == target_uid:
                                target_name = r[1].strip() if len(r) > 1 else target_uid
                                break
                    logger.info(f"{name} (UID: {uid}) -> {target_name} (UID: {target_uid})")
        
        logger.info("-" * 50)
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")

def main():
    print("\n" + "="*50)
    print("ПРОГРАММА ДЛЯ НАЗНАЧЕНИЯ ЦЕЛЕЙ")
    print("="*50)
    print("\nВыберите действие:")
    print("1. Перемешать игроков и назначить цели")
    print("2. Показать текущие цели")
    print("3. Очистить все цели")
    print("4. Выйти")
    
    while True:
        choice = input("\nВаш выбор (1-4): ").strip()
        
        if choice == '1':
            confirm = input("Вы уверены, что хотите перемешать игроков и переназначить цели? (да/нет): ").strip().lower()
            if confirm in ['да', 'yes', 'y', 'д']:
                print("\nНачинаю перемешивание...")
                shuffle_and_assign_targets()
                print("\nГотово! Проверьте таблицу.")
            else:
                print("Операция отменена.")
        
        elif choice == '2':
            print("\nТекущие цели:")
            show_current_targets()
        
        elif choice == '3':
            confirm = input("Вы уверены, что хотите очистить все цели? (да/нет): ").strip().lower()
            if confirm in ['да', 'yes', 'y', 'д']:
                print("\nОчищаю цели...")
                clear_all_targets()
                print("Готово! Все цели очищены.")
            else:
                print("Операция отменена.")
        
        elif choice == '4':
            print("До свидания!")
            break
        
        else:
            print("Неверный выбор. Попробуйте снова.")

if __name__ == "__main__":
    main()