# OSKOLCTF — Документация проекта

## 📋 Содержание

1. [О проекте](#о-проекте)
2. [Структура проекта](#структура-проекта)
3. [Принцип работы](#принцип-работы)
4. [Установка и запуск](#установка-и-запуск)
5. [Управление задачами (tasks.json)](#управление-задачами-tasksjson)
6. [Архитектура приложения](#архитектура-приложения)
7. [API Reference](#api-reference)
8. [База данных](#база-данных)
9. [Создание собственных заданий](#создание-собственных-заданий)
10. [Развёртывание в продакшене](#развёртывание-в-продакшене)

---

## 📌 О проекте

**OSKOLCTF** — это веб-платформа для проведения Capture The Flag (CTF) соревнований. Платформа позволяет участникам регистрироваться, решать задачи различных категорий (Web, Crypto, Reverse Engineering, Forensics, OSINT, Pwn) и соревноваться в таблице лидеров.

### Основные возможности

- ✅ Регистрация и аутентификация пользователей
- ✅ Система задач с категориями и уровнями сложности
- ✅ Отправка и проверка флагов
- ✅ Таблица лидеров в реальном времени
- ✅ Статистика решений по каждому заданию
- ✅ Современный SPA-интерфейс на Vue.js 3
- ✅ CSRF-защита для всех форм
- ✅ Хранение флагов в хешированном виде (SHA-256)

### Технологический стек

| Компонент | Технология |
|-----------|------------|
| Backend | Python + Flask |
| Frontend | Vue.js 3 + Vue Router |
| База данных | SQLite |
| Стилизация | CSS3 (кастомные стили) |
| Аутентификация | Сессии Flask + Werkzeug security |

---

## 📁 Структура проекта

```
oskolctf/
├── main.py              # Основной файл приложения Flask (бэкенд)
├── tasks.json           # Конфигурационный файл с заданиями (редактируется вручную)
├── requirements.txt     # Зависимости Python
├── readme.md            # Краткое описание проекта
├── doc.md               # Эта документация
├── flags.txt            # (опционально) файл с флагами для разработчиков
│
├── templates/           # HTML-шаблоны
│   ├── spa.html         # Основное SPA-приложение (Vue.js)
│   ├── task1.html       # Статическая страница задания 1
│   ├── task2.html       # Статическая страница задания 2
│   ├── task3.html       # Статическая страница задания 3
│   ├── board.html       # (не используется) резервный шаблон
│   └── spa.html         # Главный файл приложения
│
├── css/                 # Статические файлы
│   ├── ui.css           # Основные стили приложения
│   └── bg.jpg           # Фоновое изображение для страницы авторизации
│
└── ctf.sqlite3          # База данных SQLite (создаётся автоматически)
```

---

## ⚙️ Принцип работы

### Общая схема

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Браузер   │────▶│   Flask API  │────▶│   SQLite    │
│  (Vue.js)   │◀────│   (main.py)  │◀────│  (ctf.db)   │
└─────────────┘     └──────────────┘     └─────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  tasks.json  │
                    │  (конфиг)    │
                    └──────────────┘
```

### Поток данных

1. **Клиентская часть (Vue.js SPA)**:
   - Приложение загружается как единая страница (`spa.html`)
   - Vue Router управляет навигацией между страницами
   - Все данные загружаются через REST API (`/api/*`)
   - Интерфейс реактивно обновляется при изменении данных

2. **Серверная часть (Flask)**:
   - Обрабатывает HTTP-запросы к API
   - Управляет сессиями пользователей
   - Проверяет CSRF-токены
   - Взаимодействует с базой данных
   - Динамически загружает задания из `tasks.json`

3. **База данных (SQLite)**:
   - Таблица `users` — пользователи (логин, хеш пароля)
   - Таблица `solves` — решённые задания (user_id, task_id, время)

4. **Конфигурация заданий (tasks.json)**:
   - Хранит метаданные всех заданий
   - Содержит флаги (хешируются при проверке)
   - Читается при каждом запросе — изменения применяются без перезапуска сервера

---

## 🚀 Установка и запуск

### Требования

- Python 3.8 или выше
- pip (менеджер пакетов Python)

### Шаг 1: Клонирование/подготовка

```bash
cd d:\git\oskolctf
```

### Шаг 2: Создание виртуального окружения

**Windows:**
```bash
python -m venv .venv
.venv\Scripts\activate
```

**Linux/macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Шаг 3: Установка зависимостей

```bash
pip install -r requirements.txt
```

**Зависимости:**
- `flask[async]==3.1.1` — веб-фреймворк с поддержкой async

### Шаг 4: Запуск сервера

```bash
python main.py
```

Сервер запустится на адресе: **http://0.0.0.0:8005**

### Шаг 5: Открытие в браузере

Перейдите по адресу: **http://localhost:8005**

---

## 📝 Управление задачами (tasks.json)

### Формат файла `tasks.json`

Файл содержит массив объектов. Каждый объект описывает одно задание:

```json
{
  "id": 0,
  "name": "Название задания",
  "category": "Категория",
  "difficulty": "Уровень сложности",
  "description": "Описание задания",
  "points": 100,
  "flag": "oskolctf{флаг_здесь}",
  "url": "/task0",
  "active": true
}
```

### Поля задания

| Поле | Тип | Обязательное | Описание |
|------|-----|--------------|----------|
| `id` | integer | ✅ | Уникальный числовой идентификатор задания |
| `name` | string | ✅ | Название задания (отображается в интерфейсе) |
| `category` | string | ✅ | Категория: `Web`, `Разное`, `Крипто`, `Форензика`, `Реверс`, `Pwn`, `ОСИНТ` |
| `difficulty` | string | ✅ | Уровень сложности: `Очень лёгкое`, `Лёгкое`, `Среднее`, `Сложное`, `Очень сложное` |
| `description` | string | ✅ | Описание задания (инструкция для участника) |
| `points` | integer | ✅ | Количество очков за решение |
| `flag` | string | ✅ | Флаг в формате `oskolctf{...}` |
| `url` | string | ✅ | URL страницы задания (относительный путь) |
| `active` | boolean | ❌ | Статус задания (`true` — активно, `false` — скрыто). По умолчанию `true` |

### Добавление нового задания

1. Откройте файл `tasks.json` в любом текстовом редакторе
2. Добавьте новый объект в массив (через запятую после последнего элемента)
3. Сохраните файл

**Пример добавления задания:**

```json
{
  "id": 11,
  "name": "Новое задание",
  "category": "Web",
  "difficulty": "Среднее",
  "description": "Описание нового задания. Что нужно сделать участнику.",
  "points": 200,
  "flag": "oskolctf{noviy_flag_123}",
  "url": "/task11",
  "active": true
}
```

### Изменение существующего задания

1. Найдите задание по `id` или `name`
2. Измените нужные поля
3. Сохраните файл

**Изменения применяются мгновенно** — перезапуск сервера не требуется.

### Отключение задания

Установите `"active": false` — задание исчезнет из интерфейса, но останется в файле.

### Категории и иконки

| Категория | Иконка | CSS-класс |
|-----------|--------|-----------|
| Web | 🌐 | `cat-web` |
| Разное | 🎯 | `cat-разное` |
| Крипто | 🔐 | `cat-крипто` |
| Форензика | 🔬 | `cat-форензика` |
| Реверс | ⚙️ | `cat-реверс` |
| Pwn | 💥 | `cat-pwn` |
| ОСИНТ | 🕵️ | `cat-осинт` |

### Уровни сложности

| Уровень | CSS-класс |
|---------|-----------|
| Очень лёгкое | `diff-очень-лёгкое` |
| Лёгкое | `diff-лёгкое` |
| Среднее | `diff-среднее` |
| Сложное | `diff-сложное` |
| Очень сложное | `diff-очень-сложное` |

---

## 🏗 Архитектура приложения

### Backend (main.py)

#### Основные компоненты

1. **Инициализация Flask:**
```python
app = flask.Flask(
    __name__,
    template_folder=os.path.join(os.getcwd(), "templates"),
    static_folder=os.path.join(os.getcwd(), "css"),
    static_url_path="/css",
)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
```

2. **Загрузка заданий:**
```python
def get_task_list() -> list:
    """Загружает список задач из tasks.json."""
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []
```

3. **База данных:**
```python
def init_db():
    """Создаёт таблицы users и solves если их нет."""
```

4. **Проверка флагов:**
```python
def flag_hash(s: str) -> str:
    """Хеширует флаг через SHA-256."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def get_flag_hashes() -> dict:
    """Строит {task_id: sha256(flag)} из tasks.json."""
```

#### Маршруты (Routes)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/` | Главная страница (SPA) |
| GET | `/task0`–`/task4` | Страницы заданий (статические) |
| GET | `/logout` | Выход из аккаунта |
| GET | `/flag` | Секретный флаг (пасхалка) |
| GET | `/api/me` | Информация о текущем пользователе |
| GET | `/api/csrf` | Получить CSRF-токен |
| POST | `/api/auth/login` | Вход в аккаунт |
| POST | `/api/auth/register` | Регистрация нового пользователя |
| POST | `/api/auth/logout` | Выход из аккаунта |
| GET | `/api/board` | Данные для таблицы лидеров |
| POST | `/api/submit` | Отправка флага |
| GET | `/<path:path>` | Catch-all для SPA роутинга |

### Frontend (spa.html)

#### Компоненты Vue.js

1. **App** — корневой компонент
2. **HomePage** — лендинг с анимацией терминала
3. **LoginPage** — страница входа
4. **RegisterPage** — страница регистрации
5. **BoardPage** — основная страница с заданиями и лидербордом

#### Хранилище (Store)

```javascript
const store = reactive({
    user: null,      // текущий пользователь
    csrf: null,      // CSRF-токен
    toasts: [],      // уведомления
    
    async init() { ... },      // инициализация
    toast(msg, type) { ... },  // показать уведомление
    async logout() { ... },    // выход
});
```

#### Роутер

```javascript
const routes = [
    { path: '/', component: HomePage },
    { path: '/login', component: LoginPage },
    { path: '/register', component: RegisterPage },
    { path: '/board', component: BoardPage },
];
```

---

## 🔌 API Reference

### GET `/api/me`

Возвращает информацию о текущем пользователе.

**Ответ:**
```json
{"user": {"id": 1, "username": "player"}}
// или
{"user": null}
```

---

### GET `/api/csrf`

Получить CSRF-токен для защиты форм.

**Ответ:**
```json
{"csrf": "abc123xyz..."}
```

---

### POST `/api/auth/login`

Вход в аккаунт.

**Тело запроса:**
```json
{
    "username": "player",
    "password": "password123",
    "csrf": "abc123xyz..."
}
```

**Ответ:**
```json
{"ok": true, "user": {"id": 1, "username": "player"}}
// или
{"ok": false, "error": "Неверный логин или пароль"}
```

---

### POST `/api/auth/register`

Регистрация нового пользователя.

**Тело запроса:**
```json
{
    "username": "newplayer",
    "password": "password123",
    "csrf": "abc123xyz..."
}
```

**Ответ:**
```json
{"ok": true, "user": {"id": 2, "username": "newplayer"}}
// или
{"ok": false, "error": "Username ≥ 3 символа, пароль ≥ 6 символов"}
```

---

### POST `/api/auth/logout`

Выход из аккаунта.

**Ответ:**
```json
{"ok": true}
```

---

### GET `/api/board`

Получить данные для таблицы лидеров (требуется авторизация).

**Ответ:**
```json
{
    "ok": true,
    "user": {"id": 1, "username": "player"},
    "tasks": [
        {
            "id": 0,
            "name": "Привет, CTF!",
            "category": "Разное",
            "difficulty": "Очень лёгкое",
            "description": "...",
            "points": 100,
            "solved": false,
            "solved_at": null,
            "solve_count": 5,
            "link": "/task0",
            "active": true
        }
    ],
    "leaderboard": [
        {"username": "player1", "score": 500, "solved_count": 5},
        {"username": "player2", "score": 400, "solved_count": 4}
    ]
}
```

---

### POST `/api/submit`

Отправка флага (требуется авторизация).

**Тело запроса:**
```json
{
    "flag": "oskolctf{example_flag}",
    "csrf": "abc123xyz..."
}
```

**Ответ:**
```json
{"ok": true, "message": "Засчитано! Привет, CTF! (+100 pts)", "task_id": 0, "points": 100}
// или
{"ok": false, "error": "Неверный флаг", "category": "error"}
// или
{"ok": false, "error": "Task0 уже решён", "category": "info"}
```

---

## 🗄 База данных

### Схема БД

#### Таблица `users`

| Колонка | Тип | Описание |
|---------|-----|----------|
| `id` | INTEGER PRIMARY KEY | Уникальный ID пользователя |
| `username` | TEXT UNIQUE NOT NULL | Имя пользователя (уникальное) |
| `pass_hash` | TEXT NOT NULL | Хеш пароля (Werkzeug PBKDF2) |
| `created_at` | TEXT DEFAULT CURRENT_TIMESTAMP | Дата регистрации |

#### Таблица `solves`

| Колонка | Тип | Описание |
|---------|-----|----------|
| `id` | INTEGER PRIMARY KEY | Уникальный ID записи |
| `user_id` | INTEGER NOT NULL | Ссылка на пользователя |
| `task_id` | INTEGER NOT NULL | ID решённого задания |
| `solved_at` | TEXT DEFAULT CURRENT_TIMESTAMP | Время решения |
| `UNIQUE(user_id, task_id)` | — | Ограничение: одно задание решается один раз |

### Подсчёт очков

Очки считаются динамически через SQL CASE:

```sql
CASE s.task_id 
    WHEN 0 THEN ? 
    WHEN 1 THEN ? 
    ...
    ELSE 0 
END
```

Где `?` — значения `points` из `tasks.json`.

---

## 🛠 Создание собственных заданий

### Тип 1: Статическая страница

1. Создайте файл `templates/taskN.html`
2. Добавьте маршрут в `main.py`:

```python
@app.route("/task5")
async def task5():
    return flask.render_template("task5.html", flag=get_flag_by_id(5))
```

3. Добавьте задание в `tasks.json`:

```json
{
    "id": 5,
    "name": "Секретная тропа",
    "category": "Разное",
    "difficulty": "Лёгкое",
    "description": "Ищите скрытые маршруты",
    "points": 100,
    "flag": "oskolctf{secret_path_flag}",
    "url": "/task5",
    "active": true
}
```

### Тип 2: Задание с куки

```python
@app.route("/task2")
async def task2():
    response = flask.make_response(flask.render_template("task2.html"))
    response.set_cookie("flag", get_flag_by_id(2), max_age=60*60*24)
    return response
```

### Тип 3: POST-запрос с данными

```python
@app.route("/task3", methods=["GET", "POST"])
async def task3():
    if flask.request.method == "GET":
        return flask.render_template("task3.html")
    elif flask.request.method == "POST":
        data = flask.request.data.decode("utf-8")
        if data == "b3Nrb2xjdGY=":  # base64 "oskolctf"
            return get_flag_by_id(3)
        else:
            return "<h1>Wrong data, try again!</h1>"
```

### Тип 4: Проверка куки

```python
@app.route("/task4")
async def task4():
    if flask.request.cookies.get("xorg_worship_flag_for_you") == "true":
        return get_flag_by_id(4)
    response = flask.make_response("<h1>Я сам решал это 3 дня...</h1>")
    response.set_cookie("xorg_worship_flag_for_you", "false", max_age=60*60*24)
    return response
```

---

## 🚀 Развёртывание в продакшене

### 1. Настройка SECRET_KEY

**Никогда не используйте дефолтное значение!**

```bash
# Linux/macOS
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# Windows (PowerShell)
$env:SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. Отключение debug режима

В `main.py` убедитесь, что:

```python
if __name__ == "__main__":
    app.run("0.0.0.0", 8005, debug=False)  # debug=False обязательно!
```

### 3. Использование production-сервера

Для продакшена используйте **Gunicorn** или **Waitress**:

**Установка Waitress:**
```bash
pip install waitress
```

**Запуск:**
```bash
waitress-serve --host=0.0.0.0 --port=8005 main:app
```

### 4. Настройка Nginx (опционально)

```nginx
server {
    listen 80;
    server_name ctf.example.com;

    location / {
        proxy_pass http://127.0.0.1:8005;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 5. HTTPS (обязательно для продакшена)

Используйте Let's Encrypt:

```bash
sudo certbot --nginx -d ctf.example.com
```

### 6. Резервное копирование БД

```bash
cp ctf.sqlite3 ctf.sqlite3.backup
```

---

## 🔒 Безопасность

### Реализованные меры защиты

1. **CSRF-токены** — все формы защищены
2. **Хеширование паролей** — Werkzeug PBKDF2
3. **Хеширование флагов** — SHA-256 (флаги не хранятся в открытом виде)
4. **Сравнение через HMAC** — защита от timing-атак
5. **Уникальность username** — предотвращение дубликатов
6. **Ограничение повторных решений** — UNIQUE constraint в БД

### Рекомендации

- Меняйте `SECRET_KEY` для каждого развёртывания
- Используйте HTTPS в продакшене
- Регулярно делайте бэкапы БД
- Ограничьте доступ к `tasks.json` на уровне веб-сервера

---

## 📞 Поддержка

При возникновении проблем:

1. Проверьте логи Flask в консоли
2. Убедитесь, что `tasks.json` валидный JSON
3. Проверьте права доступа к `ctf.sqlite3`
4. Очистите кеш браузера при проблемах с frontend

---

**Документация создана:** 8 марта 2026 г.  
**Версия проекта:** 1.0  
**Автор документации:** AI Assistant (QWEN)
