import os
import hmac
import sqlite3
import secrets
import hashlib
import flask
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = flask.Flask(
    __name__,
    template_folder=os.path.join(os.getcwd(), "templates"),
    static_folder=os.path.join(os.getcwd(), "css"),
    static_url_path="/css",
)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")  # поменяй в проде

FLAGS_PATH = os.path.join(os.getcwd(), "flags.txt")
flags = open(FLAGS_PATH, "r", encoding="utf-8").readlines()

# Очки за таски (можешь менять)
TASK_POINTS = {
    0: 100,
    1: 150,
    2: 150,
    3: 200,
    4: 250,
    5: 100,
}

# Метаданные заданий — название, категория, сложность, описание
TASKS = {
    0: {
        "name": "Привет, CTF!",
        "category": "Разное",
        "difficulty": "Очень лёгкое",
        "description": "Флаг лежит прямо на сервере. Найди правильный маршрут и забери его. Иногда всё проще, чем кажется.",
    },
    1: {
        "name": "Невидимка",
        "category": "Web",
        "difficulty": "Лёгкое",
        "description": "Программист думал, что скрытые комментарии никто не увидит. Загляни в исходный код страницы — браузеры показывают его всем желающим.",
    },
    2: {
        "name": "Печенька",
        "category": "Web",
        "difficulty": "Лёгкое",
        "description": "Разработчик оставил кое-что вкусное в HTTP-ответе. Загляни в куки браузера — там может быть кое-что интересное.",
    },
    3: {
        "name": "Запрос в никуда",
        "category": "Web",
        "difficulty": "Среднее",
        "description": "Сервер принимает специальный POST-запрос. Но просто текст не подойдёт — данные нужно предварительно закодировать в base64.",
    },
    4: {
        "name": "Куки-монстр",
        "category": "Web",
        "difficulty": "Среднее",
        "description": "Хороший разработчик никогда не доверяет клиенту. Плохой — оставляет доступ в куках. Что поставил разработчик? Попробуй это изменить.",
    },
    5: {
        "name": "Секретная тропа",
        "category": "Разное",
        "difficulty": "Лёгкое",
        "description": "Иногда разработчики оставляют скрытые маршруты на сервере. Попробуй поискать нестандартные URL — что если на сервере есть ещё что-то кроме обычных страниц?",
    },
}

DB_PATH = os.path.join(os.getcwd(), "ctf.sqlite3")


# ---------- DB helpers ----------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            pass_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS solves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            task_id INTEGER NOT NULL,
            solved_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, task_id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()


def flag_hash(s: str) -> str:
    # Храним/сравниваем не сам флаг, а sha256
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# Предвычислим хэши флагов по индексу таски
FLAG_HASHES = {i: flag_hash(line.strip()) for i, line in enumerate(flags)}


# ---------- Auth helpers ----------
def current_user():
    uid = flask.session.get("uid")
    if not uid:
        return None
    conn = db()
    u = conn.execute("SELECT id, username FROM users WHERE id = ?", (uid,)).fetchone()
    conn.close()
    return u


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not flask.session.get("uid"):
            return flask.redirect(flask.url_for("login", next=flask.request.path))
        return fn(*args, **kwargs)
    return wrapper


def get_csrf():
    tok = flask.session.get("csrf")
    if not tok:
        tok = secrets.token_urlsafe(24)
        flask.session["csrf"] = tok
    return tok


def require_csrf():
    sent = flask.request.form.get("csrf", "")
    real = flask.session.get("csrf", "")
    if not real or not sent or not hmac.compare_digest(sent, real):
        flask.abort(400, description="CSRF check failed")


# ---------- Existing routes (НЕ МЕНЯЕМ пути) ----------
@app.route("/")
async def home():
    return flask.send_from_directory(os.path.join(os.getcwd(), "templates"), "spa.html")


@app.route("/flag")
async def flag():
    return "<h1>Ты нашёл секретный флаг! oskolctf{oskolctf}</h1>"


@app.route("/task0")
async def task0():
    return f"<h1>Привет! Это твой первый флаг! {flags[0].strip()}</h1>"


@app.route("/task1")
async def task1():
    return flask.render_template("task1.html", flag=flags[1].strip())


@app.route("/task2")
async def task2():
    response = flask.make_response(flask.render_template("task2.html"))
    response.set_cookie("flag", flags[2].strip(), max_age=60 * 60 * 24)
    return response


@app.route("/task3", methods=["GET", "POST"])
async def task3():
    if flask.request.method == "GET":
        return flask.render_template("task3.html")
    elif flask.request.method == "POST":
        data = flask.request.data.decode("utf-8")
        if data == "b3Nrb2xjdGY=":
            return flags[3].strip()
        else:
            return "<h1>Wrong data, try again!</h1>"


@app.route("/task4")
async def task4():
    if flask.request.cookies.get("xorg_worship_flag_for_you") == "true":
        return flags[4].strip()
    response = flask.make_response("<h1>Я сам решал это 3 дня...</h1>")
    response.set_cookie("xorg_worship_flag_for_you", "false", max_age=60 * 60 * 24)
    return response


# ---------- New routes: register/login/logout/board/submit ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if flask.request.method == "GET":
        return flask.render_template("register.html", user=current_user(), csrf=get_csrf())

    require_csrf()
    username = (flask.request.form.get("username") or "").strip()
    password = flask.request.form.get("password") or ""

    if len(username) < 3 or len(password) < 6:
        return flask.render_template(
            "register.html",
            user=current_user(),
            csrf=get_csrf(),
            error="Username >= 3 chars, password >= 6 chars"
        )

    conn = db()
    try:
        conn.execute(
            "INSERT INTO users(username, pass_hash) VALUES(?, ?)",
            (username, generate_password_hash(password))
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return flask.render_template(
            "register.html",
            user=current_user(),
            csrf=get_csrf(),
            error="Username already taken"
        )
    conn.close()

    return flask.redirect(flask.url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if flask.request.method == "GET":
        return flask.render_template("login.html", user=current_user(), csrf=get_csrf())

    require_csrf()
    username = (flask.request.form.get("username") or "").strip()
    password = flask.request.form.get("password") or ""

    conn = db()
    u = conn.execute(
        "SELECT id, username, pass_hash FROM users WHERE username = ?",
        (username,)
    ).fetchone()
    conn.close()

    if not u or not check_password_hash(u["pass_hash"], password):
        return flask.render_template("login.html", user=current_user(), csrf=get_csrf(), error="Wrong credentials")

    flask.session["uid"] = u["id"]
    next_url = flask.request.args.get("next") or flask.url_for("board")
    return flask.redirect(next_url)


@app.route("/logout")
def logout():
    flask.session.pop("uid", None)
    return flask.redirect(flask.url_for("home"))


@app.route("/board")
@login_required
def board():
    user = current_user()

    conn = db()
    # мои солвы
    my_solves = conn.execute(
        "SELECT task_id, solved_at FROM solves WHERE user_id = ?",
        (user["id"],)
    ).fetchall()
    my_solved = {r["task_id"] for r in my_solves}

    # сколько всего решили каждый таск
    sc_rows = conn.execute(
        "SELECT task_id, COUNT(*) as cnt FROM solves GROUP BY task_id"
    ).fetchall()
    solve_counts = {r["task_id"]: r["cnt"] for r in sc_rows}

    # лидерборд
    rows = conn.execute("""
        SELECT u.username,
               COALESCE(SUM(CASE s.task_id
                   WHEN 0 THEN ?
                   WHEN 1 THEN ?
                   WHEN 2 THEN ?
                   WHEN 3 THEN ?
                   WHEN 4 THEN ?
                   WHEN 5 THEN ?
                   ELSE 0
               END), 0) AS score,
               COUNT(s.id) AS solved_count
        FROM users u
        LEFT JOIN solves s ON s.user_id = u.id
        GROUP BY u.id
        ORDER BY score DESC, solved_count DESC, u.username ASC
        LIMIT 50
    """, (
        TASK_POINTS.get(0, 0),
        TASK_POINTS.get(1, 0),
        TASK_POINTS.get(2, 0),
        TASK_POINTS.get(3, 0),
        TASK_POINTS.get(4, 0),
        TASK_POINTS.get(5, 0),
    )).fetchall()
    conn.close()

    tasks = []
    for i in range(len(flags)):
        meta = TASKS.get(i, {})
        tasks.append({
            "id": i,
            "name": meta.get("name", f"Task {i}"),
            "category": meta.get("category", "Разное"),
            "difficulty": meta.get("difficulty", "?"),
            "description": meta.get("description", ""),
            "points": TASK_POINTS.get(i, 0),
            "solved": i in my_solved,
            "link": f"/task{i}",
            "solve_count": solve_counts.get(i, 0),
        })

    return flask.render_template(
        "board.html",
        user=user,
        csrf=get_csrf(),
        tasks=tasks,
        leaderboard=rows
    )


@app.route("/submit", methods=["POST"])
@login_required
def submit():
    require_csrf()
    user = current_user()

    raw_flag = (flask.request.form.get("flag") or "").strip()
    if not raw_flag:
        flask.flash("Пустой флаг :(", "error")
        return flask.redirect(flask.url_for("board"))

    submitted_hash = flag_hash(raw_flag)

    # находим какой это таск (если вообще валидный)
    task_id = None
    for tid, fh in FLAG_HASHES.items():
        if hmac.compare_digest(fh, submitted_hash):
            task_id = tid
            break

    if task_id is None:
        flask.flash("Неверный флаг", "error")
        return flask.redirect(flask.url_for("board"))

    conn = db()
    try:
        conn.execute(
            "INSERT INTO solves(user_id, task_id) VALUES(?, ?)",
            (user["id"], task_id)
        )
        conn.commit()
        flask.flash(f"Засчитано! Task{task_id} (+{TASK_POINTS.get(task_id,0)})", "ok")
    except sqlite3.IntegrityError:
        flask.flash(f"Ты уже сдавал Task{task_id}", "info")
    finally:
        conn.close()

    return flask.redirect(flask.url_for("board"))


# ========== JSON API для Vue SPA ==========

@app.route("/api/me")
def api_me():
    u = current_user()
    if u:
        return flask.jsonify({"user": {"id": u["id"], "username": u["username"]}})
    return flask.jsonify({"user": None})


@app.route("/api/csrf")
def api_csrf():
    return flask.jsonify({"csrf": get_csrf()})


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = flask.request.get_json(force=True) or {}
    sent = data.get("csrf", "")
    real = flask.session.get("csrf", "")
    if not real or not sent or not hmac.compare_digest(sent, real):
        return flask.jsonify({"ok": False, "error": "CSRF check failed"}), 400
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    conn = db()
    u = conn.execute(
        "SELECT id, username, pass_hash FROM users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()
    if not u or not check_password_hash(u["pass_hash"], password):
        return flask.jsonify({"ok": False, "error": "Неверный логин или пароль"})
    flask.session["uid"] = u["id"]
    return flask.jsonify({"ok": True, "user": {"id": u["id"], "username": u["username"]}})


@app.route("/api/auth/register", methods=["POST"])
def api_register():
    data = flask.request.get_json(force=True) or {}
    sent = data.get("csrf", "")
    real = flask.session.get("csrf", "")
    if not real or not sent or not hmac.compare_digest(sent, real):
        return flask.jsonify({"ok": False, "error": "CSRF check failed"}), 400
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if len(username) < 3 or len(password) < 6:
        return flask.jsonify({"ok": False, "error": "Username ≥ 3 символа, пароль ≥ 6 символов"})
    conn = db()
    try:
        conn.execute(
            "INSERT INTO users(username, pass_hash) VALUES(?, ?)",
            (username, generate_password_hash(password))
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return flask.jsonify({"ok": False, "error": "Имя уже занято"})
    u = conn.execute("SELECT id, username FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    flask.session["uid"] = u["id"]
    return flask.jsonify({"ok": True, "user": {"id": u["id"], "username": u["username"]}})


@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    flask.session.pop("uid", None)
    return flask.jsonify({"ok": True})


@app.route("/api/board")
def api_board():
    user = current_user()
    if not user:
        return flask.jsonify({"ok": False, "error": "Not authenticated"}), 401
    conn = db()
    my_solves = conn.execute(
        "SELECT task_id, solved_at FROM solves WHERE user_id = ?", (user["id"],)
    ).fetchall()
    my_solved = {r["task_id"]: r["solved_at"] for r in my_solves}

    sc_rows = conn.execute(
        "SELECT task_id, COUNT(*) as cnt FROM solves GROUP BY task_id"
    ).fetchall()
    solve_counts = {r["task_id"]: r["cnt"] for r in sc_rows}

    n = len(flags)
    case_sql = " ".join(f"WHEN {i} THEN ?" for i in range(n))
    rows = conn.execute(f"""
        SELECT u.username,
               COALESCE(SUM(CASE s.task_id {case_sql} ELSE 0 END), 0) AS score,
               COUNT(s.id) AS solved_count
        FROM users u
        LEFT JOIN solves s ON s.user_id = u.id
        GROUP BY u.id
        ORDER BY score DESC, solved_count DESC, u.username ASC
        LIMIT 50
    """, tuple(TASK_POINTS.get(i, 0) for i in range(n))).fetchall()
    conn.close()

    tasks = []
    for i in range(n):
        meta = TASKS.get(i, {})
        tasks.append({
            "id": i,
            "name": meta.get("name", f"Task {i}"),
            "category": meta.get("category", "Разное"),
            "difficulty": meta.get("difficulty", "?"),
            "description": meta.get("description", ""),
            "points": TASK_POINTS.get(i, 0),
            "solved": i in my_solved,
            "solved_at": my_solved.get(i),
            "solve_count": solve_counts.get(i, 0),
            "link": f"/task{i}",
        })
    leaderboard = [
        {"username": r["username"], "score": r["score"], "solved_count": r["solved_count"]}
        for r in rows
    ]
    return flask.jsonify({
        "ok": True,
        "user": {"id": user["id"], "username": user["username"]},
        "tasks": tasks,
        "leaderboard": leaderboard,
    })


@app.route("/api/submit", methods=["POST"])
def api_submit():
    user = current_user()
    if not user:
        return flask.jsonify({"ok": False, "error": "Not authenticated"}), 401
    data = flask.request.get_json(force=True) or {}
    sent = data.get("csrf", "")
    real = flask.session.get("csrf", "")
    if not real or not sent or not hmac.compare_digest(sent, real):
        return flask.jsonify({"ok": False, "error": "CSRF check failed"}), 400
    raw_flag = (data.get("flag") or "").strip()
    if not raw_flag:
        return flask.jsonify({"ok": False, "error": "Пустой флаг", "category": "error"})
    submitted_hash = flag_hash(raw_flag)
    task_id = None
    for tid, fh in FLAG_HASHES.items():
        if hmac.compare_digest(fh, submitted_hash):
            task_id = tid
            break
    if task_id is None:
        return flask.jsonify({"ok": False, "error": "Неверный флаг", "category": "error"})
    conn = db()
    try:
        conn.execute("INSERT INTO solves(user_id, task_id) VALUES(?, ?)", (user["id"], task_id))
        conn.commit()
        conn.close()
        return flask.jsonify({
            "ok": True,
            "message": f"Засчитано! Task{task_id} (+{TASK_POINTS.get(task_id, 0)} pts)",
            "task_id": task_id,
            "points": TASK_POINTS.get(task_id, 0),
        })
    except sqlite3.IntegrityError:
        conn.close()
        return flask.jsonify({"ok": False, "error": f"Task{task_id} уже решён", "category": "info"})


# ========== SPA catch-all (должен быть последним маршрутом) ==========
# Отдаём spa.html для всех путей, которые не являются API/task/auth маршрутами
_SPA_SKIP = {"login", "register", "logout", "board", "submit", "flag"}

@app.route("/<path:path>")
def spa_catchall(path):
    # пропускаем API, таски и функциональные маршруты
    top = path.split("/")[0]
    if top.startswith("api") or top.startswith("task") or top in _SPA_SKIP:
        flask.abort(404)
    return flask.send_from_directory(
        os.path.join(os.getcwd(), "templates"), "spa.html"
    )


# ========== startup ==========
init_db()

if __name__ == "__main__":
    app.run("0.0.0.0", 8005, debug=False)