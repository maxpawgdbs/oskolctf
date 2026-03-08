import os
import hmac
import sqlite3
import secrets
import hashlib
import json
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

# Путь к JSON-файлу с описанием задач (редактируй tasks.json для добавления/изменения тасков)
TASKS_FILE = os.path.join(os.getcwd(), "tasks.json")


def get_task_list() -> list:
    """Загружает список задач из tasks.json. Читается при каждом запросе — изменения применяются без перезапуска."""
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def build_score_sql(task_list: list):
    """Строит динамический CASE SQL и кортеж параметров для подсчёта очков по таблице лидеров."""
    active = [t for t in task_list if t.get("active", True)]
    if not active:
        return "0", ()
    parts = " ".join(f"WHEN {int(t['id'])} THEN ?" for t in active)
    return f"CASE s.task_id {parts} ELSE 0 END", tuple(t["points"] for t in active)

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


def get_flag_hashes() -> dict:
    """Строит {task_id: sha256(flag)} из tasks.json при каждом вызове."""
    result = {}
    for t in get_task_list():
        raw = (t.get("flag") or "").strip()
        if raw:
            result[t["id"]] = flag_hash(raw)
    return result


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
            return flask.redirect("/")
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


def get_flag_by_id(task_id: int) -> str:
    """Возвращает флаг задачи из tasks.json по id."""
    for t in get_task_list():
        if t["id"] == task_id:
            return (t.get("flag") or "").strip()
    return ""


# ---------- Existing routes ----------
@app.route("/")
async def home():
    return flask.send_from_directory(os.path.join(os.getcwd(), "templates"), "spa.html")


@app.route("/logout")
def logout():
    flask.session.pop("uid", None)
    return flask.redirect("/")


@app.route("/flag")
async def flag():
    return "<h1>Ты нашёл секретный флаг! oskolctf{oskolctf}</h1>"


@app.route("/task0")
async def task0():
    return f"<h1>Привет! Это твой первый флаг! {get_flag_by_id(0)}</h1>"


@app.route("/task1")
async def task1():
    return flask.render_template("task1.html", flag=get_flag_by_id(1))


@app.route("/task2")
async def task2():
    response = flask.make_response(flask.render_template("task2.html"))
    response.set_cookie("flag", get_flag_by_id(2), max_age=60 * 60 * 24)
    return response


@app.route("/task3", methods=["GET", "POST"])
async def task3():
    if flask.request.method == "GET":
        return flask.render_template("task3.html")
    elif flask.request.method == "POST":
        data = flask.request.data.decode("utf-8")
        if data == "b3Nrb2xjdGY=":
            return get_flag_by_id(3)
        else:
            return "<h1>Wrong data, try again!</h1>"


@app.route("/task4")
async def task4():
    if flask.request.cookies.get("xorg_worship_flag_for_you") == "true":
        return get_flag_by_id(4)
    response = flask.make_response("<h1>Я сам решал это 3 дня...</h1>")
    response.set_cookie("xorg_worship_flag_for_you", "false", max_age=60 * 60 * 24)
    return response


# ---------- New routes: register/login/logout/board/submit ----------

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

    task_list = get_task_list()
    score_sql, score_params = build_score_sql(task_list)
    rows = conn.execute(f"""
        SELECT u.username,
               COALESCE(SUM({score_sql}), 0) AS score,
               COUNT(s.id) AS solved_count
        FROM users u
        LEFT JOIN solves s ON s.user_id = u.id
        GROUP BY u.id
        ORDER BY score DESC, solved_count DESC, u.username ASC
        LIMIT 50
    """, score_params).fetchall()
    conn.close()

    tasks = []
    for t in task_list:
        tid = t["id"]
        tasks.append({
            "id": tid,
            "name": t["name"],
            "category": t["category"],
            "difficulty": t["difficulty"],
            "description": t.get("description", ""),
            "points": t["points"],
            "solved": tid in my_solved,
            "solved_at": my_solved.get(tid),
            "solve_count": solve_counts.get(tid, 0),
            "link": t.get("url", f"/task{tid}"),
            "active": t.get("active", True),
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
    for tid, fh in get_flag_hashes().items():
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
        task_list = get_task_list()
        task_meta = next((t for t in task_list if t["id"] == task_id), None)
        task_points = task_meta["points"] if task_meta else 0
        task_name = task_meta["name"] if task_meta else f"Task {task_id}"
        return flask.jsonify({
            "ok": True,
            "message": f"Засчитано! {task_name} (+{task_points} pts)",
            "task_id": task_id,
            "points": task_points,
        })
    except sqlite3.IntegrityError:
        conn.close()
        return flask.jsonify({"ok": False, "error": f"Task{task_id} уже решён", "category": "info"})


# ========== SPA catch-all (последний маршрут) ==========
_SPA_SKIP = set()  # API/task-маршруты заданы явно и имеют приоритет

@app.route("/<path:path>")
def spa_catchall(path):
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