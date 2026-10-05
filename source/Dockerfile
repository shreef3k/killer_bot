# Используем официальный образ Python 3.9
FROM python:3.9-slim

# Устанавливаем зависимости системы
RUN apt-get update && apt-get install -y \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /usr/src/app

# Копируем файл с зависимостями
COPY requirements.txt ./

# Устанавливаем зависимости Python
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код приложения
COPY . .

# Копируем файл .env
COPY .env .env


# Команда для запуска приложения
CMD ["python", "bot.py"]
