# **1️. Установите библиотеки**


pip install -r requirements.txt

# **2️. Настройте доступ к Google Sheets**


Перейдите в Google Cloud Console.
Создайте новый проект.
Включите API Google Sheets и Google Drive.
Перейдите в "Создание учетных данных" → выберите "Сервисный аккаунт".
Создайте JSON-файл с ключами (скачайте его).
Откройте вашу Google Таблицу → "Настройки доступа" → добавьте email из JSON-файла с правами редактирования.

# **3. Установите параметры в .env**

#### Название таблицы

TABLE_NAME=Supraten (пример)

#### Время через которое будет запускаться скрипт повторно в секундах (86400 - 24 часа)

REPEAT_IN_SECONDS=86400 (пример)

#### Выбор категорий

INDEX_TO_PARSE=[7, 5] (пример)

#### Название скачаного джейсона з даними

JSON_NAME=wired-standard-450813-f5-dc1cc2de041e.json (пример)

### Запуск через run_script.bat

**Сайты:**

1. ***https://supraten.md***
2. ***https://www.iek.md***
3. ***https://habsev.md/ro***
4. ***https://luminaled.md/index.php?route=common/home***
5. ***https://electromotor.md***
