import os
import hmac
import sqlite3
import secrets
import hashlib
import flask
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = flask.Flask(__name__, template_folder=os.path.join(os.getcwd(), "templates"))
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
    return '<h1>Welcome to OSKOLCTF</h1><p><a href="/board">Board</a></p>'


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

    # лидерборд
    rows = conn.execute("""
        SELECT u.username,
               COALESCE(SUM(CASE s.task_id
                   WHEN 0 THEN ?
                   WHEN 1 THEN ?
                   WHEN 2 THEN ?
                   WHEN 3 THEN ?
                   WHEN 4 THEN ?
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
    )).fetchall()
    conn.close()

    tasks = []
    for i in range(len(flags)):
        tasks.append({
            "id": i,
            "points": TASK_POINTS.get(i, 0),
            "solved": i in my_solved,
            "link": f"/task{i}",
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


# ---------- startup ----------
init_db()

if __name__ == "__main__":
    app.run("0.0.0.0", 8005, debug=False)