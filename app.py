import os
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
import io
import csv
import random
import traceback
import calendar

from datetime import datetime  # вверху файла, если ещё не импортирован
from werkzeug.utils import secure_filename

import requests
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    jsonify,
    session,
    send_file,
    flash,
)

# ==== ФИЛЬТР ДЛЯ АБЗАЦЕВ ==== 
def format_paragraphs(text: str) -> str:
    """Преобразует текст с пустыми строками в HTML-абзацы."""
    if not text:
        return ""
    parts = [p.strip() for p in text.replace("\r", "").split("\n\n")]
    html = "".join(f"<p>{p}</p>" for p in parts if p)
    return html

app = Flask(__name__)

app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 МБ

# регистрируем фильтр ПОСЛЕ того, как создан app
app.jinja_env.filters["paragraphs"] = format_paragraphs

app.secret_key = os.getenv("FLASK_SECRET_KEY")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "soul.db")

# ================== НАСТРОЙКИ ==================

#app.jinja_env.filters["paragraphs"] = format_paragraphs


# секретный ключ для сессий (логин в админку)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# Настройки Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Данные администратора
ADMIN_USER = os.getenv("ADMIN_USER")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")  # ОБЯЗАТЕЛЬНО поменяй

# Анти-спам по заявкам
ENROLL_SPAM_SECONDS = 60  # интервал между заявками с одного IP (в секундах)

UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
TEACHER_UPLOAD = os.path.join(UPLOAD_FOLDER, "teachers")
COURSE_UPLOAD  = os.path.join(UPLOAD_FOLDER, "courses")
GALLERY_UPLOAD = os.path.join(UPLOAD_FOLDER, "gallery")  # НОВОЕ
TEACHER_KEY = os.getenv("TEACHER_KEY")  # типа 'teacher_very_long_secret'


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HOMEWORK_UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads", "homework")
os.makedirs(HOMEWORK_UPLOAD_FOLDER, exist_ok=True)

ALLOWED_HW_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "doc", "docx", "ppt", "pptx", "zip", "txt"}

def hw_allowed(filename: str) -> bool:
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_HW_EXTENSIONS

for path in (UPLOAD_FOLDER, TEACHER_UPLOAD, COURSE_UPLOAD, GALLERY_UPLOAD):
    os.makedirs(path, exist_ok=True)

ALLOWED_EXT = {"png", "jpg", "jpeg", "webp"}

def save_upload(file, folder):
    if not file:
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXT:
        return None
    filename = f"{datetime.utcnow().timestamp()}.{ext}"
    filepath = os.path.join(folder, filename)
    file.save(filepath)
    return filename


def generate_student_code():
    """Генерирует уникальный 6-значный код типа 038421."""
    conn = get_db()
    while True:
        code = f"{random.randint(0, 999999):06d}"
        exists = conn.execute(
            "SELECT 1 FROM student_accounts WHERE public_code = ?",
            (code,),
        ).fetchone()
        if not exists:
            conn.close()
            return code




# ================== БАЗА ДАННЫХ ==================

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ---- REVIEWS ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            package TEXT,
            rating INTEGER,
            text TEXT,
            approved INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # ---- ENROLLS ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS enrolls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT,
            name TEXT NOT NULL,
            contact TEXT NOT NULL,
            tariff TEXT,
            level TEXT,
            comment TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)


    # ---- TEACHERS ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role TEXT,
            bio TEXT,
            photo TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # новые поля под "Основное" и ачивки
    try:
        cur.execute("ALTER TABLE teachers ADD COLUMN highlights TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE teachers ADD COLUMN badges TEXT")
    except sqlite3.OperationalError:
        pass


    # ---- COURSES ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            price INTEGER,
            lessons INTEGER,
            description TEXT,
            photo TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    try:
        cur.execute("ALTER TABLE courses ADD COLUMN hero_tags TEXT")
    except sqlite3.OperationalError:
        pass
    # ---- GALLERY ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS gallery (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            photo TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # ---- STUDENT ACCOUNTS ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS student_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            public_code TEXT NOT NULL UNIQUE,        -- 6-значный код для ученика
            name TEXT,                               -- имя ученика
            course TEXT,                             -- курс/группа
            last_payment_date TEXT,                  -- дата последней оплаты (строкой YYYY-MM-DD)
            last_payment_amount INTEGER,             -- сумма последней оплаты
            lessons_total INTEGER,                   -- всего занятий в текущем пакете
            lessons_left INTEGER,                    -- сколько осталось
            comment TEXT,                            -- любые пометки препода
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # привязка ученика к преподавателю (может уже существовать)
    try:
        cur.execute("""
            ALTER TABLE student_accounts
            ADD COLUMN teacher_id INTEGER REFERENCES teachers(id)
        """)
    except sqlite3.OperationalError:
        # колонка уже есть — просто игнорируем ошибку
        pass
    # ---- STUDENT LESSONS (расписание) ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS student_lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            start_at TEXT NOT NULL,             -- 'YYYY-MM-DD HH:MM'
            status TEXT NOT NULL DEFAULT 'planned',  -- planned / done / canceled / rescheduled
            rescheduled_to TEXT,                -- новая дата/время, если перенос
            topic TEXT,                         -- тема урока
            comment TEXT,                       -- заметка для ученика или для себя
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES student_accounts(id) ON DELETE CASCADE
        );
    """)
    # ---- STUDENT HOMEWORK ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS student_homework (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            title TEXT,
            comment TEXT,
            file_name TEXT,    -- оригинальное имя файла
            file_path TEXT,    -- путь к файлу на диске
            status TEXT DEFAULT 'new',  -- new / checked
            teacher_comment TEXT,
            teacher_file_name TEXT,         -- имя файла от препода
            teacher_file_path TEXT,         -- путь к файлу от препода
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            checked_at DATETIME,
            FOREIGN KEY(student_id) REFERENCES student_accounts(id)
        );
    """)
    try:
        cur.execute("ALTER TABLE student_homework ADD COLUMN teacher_file_name TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE student_homework ADD COLUMN teacher_file_path TEXT")
    except sqlite3.OperationalError:
        pass


    conn.commit()
    conn.close()


init_db()


# ================== ХЕЛПЕРЫ ==================

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapper

# Преподаватель = тот же админ, отдельная авторизация не нужна
teacher_login_required = login_required


# ================== TELEGRAM ==================

def send_enroll_to_telegram(payload: dict):
    """
    Отправляет уведомление о новой записи на занятие в Telegram (админу).
    payload: name, contact, tariff, level, comment
    """
    print("DEBUG: send_enroll_to_telegram called with:", payload)

    if (not TELEGRAM_BOT_TOKEN
            or not TELEGRAM_CHAT_ID
            or "YOUR_TELEGRAM_BOT_TOKEN_HERE" in TELEGRAM_BOT_TOKEN):
        print("DEBUG: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing or placeholder")
        return

    text_lines = [
        "📝 *Новая заявка на занятия*",
        "",
        f"👤 Имя: {payload.get('name') or '-'}",
        f"📨 Контакт: {payload.get('contact') or '-'}",
        f"📦 Пакет: {payload.get('tariff') or 'не выбран'}",
        f"📊 Уровень: {payload.get('level') or '-'}",
    ]

    comment = payload.get("comment")
    if comment:
        text_lines.append("")
        text_lines.append(f"💬 Комментарий:\n{comment}")

    text = "\n".join(text_lines)
    print("DEBUG: Telegram text:\n", text)

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    try:
        resp = requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        print("DEBUG: telegram response:", resp.status_code, resp.text)
    except requests.RequestException as e:
        print("ERROR: telegram request failed:", e)


def send_review_to_telegram(review: dict):
    """
    При желании — уведомление о новом отзыве (в очередь модерации).
    Пока заглушка.
    """
    print("DEBUG: send_review_to_telegram called (заглушка). Review:", review)
    return


def send_enroll_email_to_user(payload: dict):
    """
    Заготовка под отправку email пользователю (сейчас не делает ничего).
    """
    print("DEBUG: send_enroll_email_to_user called (stub). Payload:", payload)
    return

#Раздлеление тегов в описании курса
def split_tags(s: str):
    if not s:
        return []
    return [t.strip() for t in s.split(",") if t.strip()]


# ================== ПУБЛИЧНАЯ ЧАСТЬ ==================

@app.route("/")
def index():
    conn = get_db()

    reviews = conn.execute("""
        SELECT name, package, rating, text, created_at
        FROM reviews
        WHERE approved = 1
        ORDER BY created_at DESC
        LIMIT 9;
    """).fetchall()

    teachers = conn.execute("""
        SELECT * FROM teachers
        ORDER BY created_at DESC
    """).fetchall()

    courses = conn.execute("""
        SELECT * FROM courses
        ORDER BY created_at ASC
    """).fetchall()

    gallery = conn.execute("SELECT * FROM gallery ORDER BY created_at DESC LIMIT 12").fetchall()

    conn.close()
    return render_template("index.html", reviews=reviews,
                           teachers=teachers, courses=courses,
                           gallery=gallery)




@app.post("/add-review")
def add_review():
    name = request.form.get("name", "").strip()
    package = request.form.get("package", "").strip()
    rating_raw = request.form.get("rating", "5").strip()
    text = request.form.get("text", "").strip()

    if not name or not text:
        return redirect(url_for("index"))

    try:
        rating = int(rating_raw)
        if rating < 1 or rating > 5:
            rating = 5
    except ValueError:
        rating = 5

    conn = get_db()
    conn.execute(
        "INSERT INTO reviews (name, package, rating, text, approved) VALUES (?, ?, ?, ?, 0)",
        (name, package or None, rating, text),
    )
    conn.commit()
    conn.close()

    review = {"name": name, "package": package, "rating": rating, "text": text}
    send_review_to_telegram(review)

    # отзыв ушёл в очередь модерации
    return redirect(url_for("index"))


@app.post("/api/telegram/review")
def api_telegram_review():
    """
    Пример endpoint-а для Telegram-бота, чтобы создавать отзывы.
    Все такие отзывы тоже не опубликованы до модерации (approved=0).
    """
    data = request.get_json(force=True, silent=True) or {}

    secret = data.get("secret")
    if secret != os.getenv("TELEGRAM_API_SECRET", "change_me"):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    name = (data.get("name") or "").strip()
    package = (data.get("package") or "").strip()
    rating = data.get("rating") or 5
    text = (data.get("text") or "").strip()

    if not name or not text:
        return jsonify({"ok": False, "error": "name and text required"}), 400

    try:
        rating = int(rating)
        if rating < 1 or rating > 5:
            rating = 5
    except (TypeError, ValueError):
        rating = 5

    conn = get_db()
    conn.execute(
        "INSERT INTO reviews (name, package, rating, text, approved) VALUES (?, ?, ?, ?, 0)",
        (name, package or None, rating, text),
    )
    conn.commit()
    conn.close()

    review = {"name": name, "package": package, "rating": rating, "text": text}
    send_review_to_telegram(review)

    return jsonify({"ok": True})


@app.post("/enroll")
def enroll():
    """
    Обработка формы записи на занятие.
    """
    name = (request.form.get("name") or "").strip()
    contact = (request.form.get("contact") or "").strip()
    tariff = (request.form.get("tariff") or "").strip()
    level = (request.form.get("level") or "").strip()
    comment = (request.form.get("comment") or "").strip()

    print("DEBUG: enroll() called, form data:", {
        "name": name,
        "contact": contact,
        "tariff": tariff,
        "level": level,
        "comment": comment,
    })

    if not name or not contact:
        return redirect(url_for("index"))

    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    now = datetime.utcnow()

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT created_at FROM enrolls WHERE ip = ? ORDER BY created_at DESC LIMIT 1",
        (ip,),
    )
    row = cur.fetchone()
    if row and row["created_at"]:
        try:
            last_dt = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
            diff = now - last_dt
            if diff < timedelta(seconds=ENROLL_SPAM_SECONDS):
                print(f"DEBUG: spam protection triggered for IP {ip}, diff={diff}")
                conn.close()
                return redirect(url_for("thank_you"))
        except ValueError:
            pass

    cur.execute(
        """
        INSERT INTO enrolls (ip, name, contact, tariff, level, comment)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (ip, name, contact, tariff or None, level or None, comment or None),
    )
    conn.commit()
    conn.close()

    payload = {
        "name": name,
        "contact": contact,
        "tariff": tariff,
        "level": level,
        "comment": comment,
    }
    send_enroll_to_telegram(payload)
    send_enroll_email_to_user(payload)

    return redirect(url_for("thank_you"))


@app.get("/thanks")
def thank_you():
    return render_template("thank_you.html")


# ================== АДМИНКА: ЛОГИН / ЛОГАУТ ==================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    next_url = request.args.get("next") or url_for("admin_enrolls")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if username == ADMIN_USER and password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(next_url)
        else:
            error = "Неверный логин или пароль"

    return render_template("admin_login.html", error=error)


@app.get("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))


@app.get("/admin")
@login_required
def admin_index():
    return redirect(url_for("admin_enrolls"))


# ================== АДМИНКА: ЗАЯВКИ ==================

@app.get("/admin/enrolls")
@login_required
def admin_enrolls():
    conn = get_db()
    enrolls = conn.execute(
        """
        SELECT id, created_at, ip, name, contact, tariff, level, comment
        FROM enrolls
        ORDER BY created_at DESC
        LIMIT 500
        """
    ).fetchall()
    conn.close()
    return render_template("admin_enrolls.html", enrolls=enrolls)


@app.get("/admin/enrolls/export")
@login_required
def admin_enrolls_export():
    """
    Экспорт заявок в CSV.
    """
    conn = get_db()
    rows = conn.execute(
        """
        SELECT id, created_at, ip, name, contact, tariff, level, comment
        FROM enrolls
        ORDER BY created_at DESC
        """
    ).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["id", "created_at", "ip", "name", "contact", "tariff", "level", "comment"])
    for row in rows:
        writer.writerow([
            row["id"],
            row["created_at"],
            row["ip"],
            row["name"],
            row["contact"],
            row["tariff"] or "",
            row["level"] or "",
            row["comment"] or "",
        ])

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        mimetype="text/csv; charset=utf-8",
        as_attachment=True,
        download_name="enrolls.csv",
    )


# ================== АДМИНКА: ОТЗЫВЫ ==================

@app.get("/admin/reviews")
@login_required
def admin_reviews():
    conn = get_db()
    reviews = conn.execute(
        """
        SELECT id, created_at, name, package, rating, text, approved
        FROM reviews
        ORDER BY created_at DESC
        LIMIT 500
        """
    ).fetchall()
    conn.close()
    return render_template("admin_reviews.html", reviews=reviews)


@app.post("/admin/reviews/<int:review_id>/approve")
@login_required
def admin_review_approve(review_id: int):
    conn = get_db()
    conn.execute(
        "UPDATE reviews SET approved = 1 WHERE id = ?",
        (review_id,),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("admin_reviews"))


@app.post("/admin/reviews/<int:review_id>/hide")
@login_required
def admin_review_hide(review_id: int):
    conn = get_db()
    conn.execute(
        "UPDATE reviews SET approved = 0 WHERE id = ?",
        (review_id,),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("admin_reviews"))

@app.post("/admin/reviews/<int:review_id>/delete")
@login_required
def admin_review_delete(review_id: int):
    conn = get_db()
    conn.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_reviews"))


# ----- СПИСОК ПРЕПОДАВАТЕЛЕЙ -----
@app.get("/admin/teachers")
@login_required
def admin_teachers():
    conn = get_db()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM teachers ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return render_template("admin_teachers.html", teachers=rows)


# ----- ДОБАВЛЕНИЕ ПРЕПОДАВАТЕЛЯ -----
@app.post("/admin/teachers/add")
@login_required
def admin_teachers_add():
    name = request.form["name"]
    role = request.form.get("role", "")
    bio = request.form.get("bio", "")
    highlights = request.form.get("highlights", "")  # новые буллеты
    badges = request.form.get("badges", "")          # ачивки

    photo = None
    file = request.files.get("photo")
    if file and file.filename:
        photo = save_upload(file, TEACHER_UPLOAD)

    conn = get_db()
    conn.execute(
        """
        INSERT INTO teachers (name, role, bio, photo, highlights, badges)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (name, role, bio, photo, highlights, badges),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("admin_teachers"))




# ----- РЕДАКТИРОВАНИЕ ПРЕПОДАВАТЕЛЯ -----
@app.route("/admin/teachers/<int:tid>/edit", methods=["GET", "POST"])
@login_required
def admin_teachers_edit(tid):
    conn = get_db()
    conn.row_factory = sqlite3.Row

    teacher = conn.execute(
        "SELECT * FROM teachers WHERE id = ?",
        (tid,),
    ).fetchone()

    if not teacher:
        conn.close()
        return redirect(url_for("admin_teachers"))

    if request.method == "POST":
        name = request.form["name"]
        role = request.form.get("role", "")
        bio = request.form.get("bio", "")
        highlights = request.form.get("highlights", "")
        badges = request.form.get("badges", "")

        file = request.files.get("photo")
        new_photo = save_upload(file, TEACHER_UPLOAD) if file and file.filename else None

        if new_photo:
            conn.execute(
                """
                UPDATE teachers
                SET name = ?, role = ?, bio = ?, photo = ?, highlights = ?, badges = ?
                WHERE id = ?
                """,
                (name, role, bio, new_photo, highlights, badges, tid),
            )
        else:
            conn.execute(
                """
                UPDATE teachers
                SET name = ?, role = ?, bio = ?, highlights = ?, badges = ?
                WHERE id = ?
                """,
                (name, role, bio, highlights, badges, tid),
            )

        conn.commit()
        conn.close()
        return redirect(url_for("admin_teachers"))

    # GET-запрос — просто показать форму
    conn.close()
    return render_template("admin_teacher_edit.html", teacher=teacher)




# ----- УДАЛЕНИЕ ПРЕПОДАВАТЕЛЯ -----
@app.post("/admin/teachers/delete/<int:tid>")
@login_required
def admin_teachers_delete(tid):
    conn = get_db()
    conn.execute("DELETE FROM teachers WHERE id = ?", (tid,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_teachers"))



@app.get("/admin/courses")
@login_required
def admin_courses():
    conn = get_db()
    #conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM courses ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template("admin_courses.html", courses=rows)



@app.post("/admin/courses/add")
@login_required
def admin_courses_add():
    title = request.form["title"]
    price = request.form["price"]
    lessons = request.form["lessons"]
    description = request.form["description"]
    photo = save_upload(request.files.get("photo"), COURSE_UPLOAD)

    conn = get_db()
    conn.execute("""
        INSERT INTO courses (title, price, lessons, description, photo)
        VALUES (?, ?, ?, ?, ?)
    """, (title, price, lessons, description, photo))

    conn.commit()
    conn.close()

    return redirect(url_for("admin_courses"))

@app.post("/admin/courses/delete/<int:cid>")
@login_required
def admin_courses_delete(cid):
    conn = get_db()
    conn.execute("DELETE FROM courses WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_courses"))

@app.route("/admin/courses/<int:cid>/edit", methods=["GET", "POST"])
@login_required
def admin_courses_edit(cid):
    conn = get_db()
    conn.row_factory = sqlite3.Row

    course = conn.execute(
        "SELECT * FROM courses WHERE id = ?",
        (cid,),
    ).fetchone()

    if not course:
        conn.close()
        return redirect(url_for("admin_courses"))

    if request.method == "POST":
        title = request.form["title"]
        price = request.form["price"]
        lessons = request.form["lessons"]
        description = request.form["description"]
        hero_tags = (request.form.get("hero_tags") or "").strip()
        
        file = request.files.get("photo")
        new_photo = save_upload(file, COURSE_UPLOAD) if file and file.filename else None

        if new_photo:
            conn.execute("""
                UPDATE courses
                SET title=?, price=?, lessons=?, description=?, photo=?, hero_tags = ?
                WHERE id=?
            """, (title, price, lessons, description, new_photo, hero_tags, cid))
        else:
            conn.execute("""
                UPDATE courses
                SET title=?, price=?, lessons=?, description=?, hero_tags = ?
                WHERE id=?
            """, (title, price, lessons, description, hero_tags, cid))

        conn.commit()
        conn.close()
        return redirect(url_for("admin_courses"))

    conn.close()
    return render_template("admin_course_edit.html", course=course)

@app.get("/admin/gallery")
@login_required
def admin_gallery():
    try:
        conn = get_db()
        conn.row_factory = sqlite3.Row
        images = conn.execute(
            "SELECT * FROM gallery ORDER BY created_at DESC"
        ).fetchall()
        conn.close()
        return render_template("admin_gallery.html", images=images)
    except Exception as e:
        import traceback
        print("ERROR in /admin/gallery:", e)
        traceback.print_exc()  # полный стэк в консоль
        return f"Ошибка в галерее: {e}", 500




@app.post("/admin/gallery/add")
@login_required
def admin_gallery_add():
    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip()
    photo = save_upload(request.files.get("photo"), GALLERY_UPLOAD)

    # без фото ничего добавлять не будем
    if not photo:
        return redirect(url_for("admin_gallery"))

    conn = get_db()
    conn.execute(
        "INSERT INTO gallery (title, description, photo) VALUES (?, ?, ?)",
        (title or None, description or None, photo),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("admin_gallery"))


@app.post("/admin/gallery/delete/<int:gid>")
@login_required
def admin_gallery_delete(gid):
    conn = get_db()
    conn.execute("DELETE FROM gallery WHERE id=?", (gid,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_gallery"))


# ================== TEACHER DASHBOARD ==================

@app.get("/teacher/login")
def teacher_login():
    error = request.args.get("error")
    return render_template("teacher_login.html", error=error)


@app.post("/teacher/login")
def teacher_login_post():
    code = (request.form.get("code") or "").strip()
    if TEACHER_KEY and code == TEACHER_KEY:
        session["teacher_logged_in"] = True
        next_url = request.args.get("next") or url_for("teacher_students")
        return redirect(next_url)
    error = "Неверный ID преподавателя"
    return render_template("teacher_login.html", error=error)


@app.get("/teacher/logout")
def teacher_logout():
    session.pop("teacher_logged_in", None)
    return redirect(url_for("teacher_login"))


@app.get("/teacher/students")
@teacher_login_required
def teacher_students():
    conn = get_db()
    conn.row_factory = sqlite3.Row

    students = conn.execute("""
        SELECT
            s.*,
            t.name AS teacher_name
        FROM student_accounts AS s
        LEFT JOIN teachers AS t ON t.id = s.teacher_id
        ORDER BY s.name COLLATE NOCASE
    """).fetchall()

    conn.close()
    return render_template("teacher_students.html", students=students)


@app.route("/teacher/homework/<int:hw_id>", methods=["GET", "POST"])
@teacher_login_required
def teacher_homework_review(hw_id):
    conn = get_db()
    conn.row_factory = sqlite3.Row

    hw = conn.execute("""
        SELECT
            h.*,
            s.name AS student_name,
            s.public_code AS student_code,
            s.course AS student_course
        FROM student_homework h
        JOIN student_accounts s ON s.id = h.student_id
        WHERE h.id = ?
    """, (hw_id,)).fetchone()

    if not hw:
        conn.close()
        flash("Домашнее задание не найдено", "error")
        return redirect(url_for("teacher_homework_list"))

    if request.method == "POST":
        status = request.form.get("status") or "checked"
        teacher_comment = (request.form.get("teacher_comment") or "").strip()
        file = request.files.get("teacher_file")

        teacher_file_name = hw["teacher_file_name"]
        teacher_file_path = hw["teacher_file_path"]

        if file and file.filename and hw_allowed(file.filename):
            orig_name = secure_filename(file.filename)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            new_name = f"hw{hw['id']}_reply_{ts}_{orig_name}"
            abs_path = os.path.join(HOMEWORK_UPLOAD_FOLDER, new_name)
            file.save(abs_path)

            teacher_file_name = orig_name
            teacher_file_path = f"uploads/homework/{new_name}"

        conn.execute("""
            UPDATE student_homework
            SET
                status = ?,
                teacher_comment = ?,
                teacher_file_name = ?,
                teacher_file_path = ?,
                checked_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            status,
            teacher_comment or None,
            teacher_file_name,
            teacher_file_path,
            hw_id,
        ))
        conn.commit()
        conn.close()

        flash("Домашнее задание обновлено", "success")
        return redirect(url_for("teacher_homework_list"))

    conn.close()
    return render_template("teacher_homework_review.html", hw=hw)



@app.route("/teacher/students/add", methods=["GET", "POST"])
@teacher_login_required
def teacher_students_add():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        course = (request.form.get("course") or "").strip()
        last_payment_date = (request.form.get("last_payment_date") or "").strip()
        last_payment_amount = request.form.get("last_payment_amount") or None
        lessons_total = request.form.get("lessons_total") or None
        lessons_left = request.form.get("lessons_left") or None
        comment = (request.form.get("comment") or "").strip()
        teacher_id = request.form.get("teacher_id") or None

        code = generate_student_code()

        conn = get_db()
        conn.execute(
            """
            INSERT INTO student_accounts (
                public_code,
                name,
                course,
                last_payment_date,
                last_payment_amount,
                lessons_total,
                lessons_left,
                comment,
                teacher_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                name or None,
                course or None,
                last_payment_date or None,
                int(last_payment_amount) if last_payment_amount else None,
                int(lessons_total) if lessons_total else None,
                int(lessons_left) if lessons_left else None,
                comment or None,
                int(teacher_id) if teacher_id else None,
            ),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("teacher_students"))

    # сюда ещё хорошо бы прокинуть список teachers, когда форму допилим
    # получаем всех преподавателей для селекта
    conn = get_db()
    teachers = conn.execute("SELECT id, name FROM teachers ORDER BY name").fetchall()
    conn.close()

    return render_template(
        "teacher_student_form.html",
        student=None,
        teachers=teachers
    )




@app.route("/teacher/students/<int:sid>/edit", methods=["GET", "POST"])
@teacher_login_required
def teacher_students_edit(sid):
    conn = get_db()
    conn.row_factory = sqlite3.Row
    student = conn.execute(
        "SELECT * FROM student_accounts WHERE id = ?",
        (sid,),
    ).fetchone()

    if not student:
        conn.close()
        return redirect(url_for("teacher_students"))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        course = (request.form.get("course") or "").strip()
        last_payment_date = (request.form.get("last_payment_date") or "").strip()
        last_payment_amount = request.form.get("last_payment_amount") or None
        lessons_total = request.form.get("lessons_total") or None
        lessons_left = request.form.get("lessons_left") or None
        comment = (request.form.get("comment") or "").strip()
        teacher_id = request.form.get("teacher_id") or None

        conn.execute(
            """
            UPDATE student_accounts
            SET
                name = ?,
                course = ?,
                last_payment_date = ?,
                last_payment_amount = ?,
                lessons_total = ?,
                lessons_left = ?,
                comment = ?,
                teacher_id = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                name or None,
                course or None,
                last_payment_date or None,
                int(last_payment_amount) if last_payment_amount else None,
                int(lessons_total) if lessons_total else None,
                int(lessons_left) if lessons_left else None,
                comment or None,
                int(teacher_id) if teacher_id else None,
                sid,
            ),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("teacher_students"))


    conn.close()
    # подтягиваем список преподавателей
    conn = get_db()
    teachers = conn.execute("SELECT id, name FROM teachers ORDER BY name").fetchall()
    conn.close()

    return render_template(
        "teacher_student_form.html",
        student=student,
        teachers=teachers
    )



@app.post("/teacher/students/<int:sid>/delete")
@teacher_login_required
def teacher_students_delete(sid):
    conn = get_db()
    conn.execute("DELETE FROM student_accounts WHERE id = ?", (sid,))
    conn.commit()
    conn.close()
    return redirect(url_for("teacher_students"))


@app.route("/student", methods=["GET", "POST"])
def student_dashboard():
    code = None
    student = None
    not_found = False

    # сразу заводим списки, чтобы шаблон всегда их видел
    lessons_planned = []
    lessons_rescheduled = []
    lessons_done = []
    lessons_canceled = []
    homework_list = []

    # --- 1. Определяем, какой это POST: ввод кода или загрузка ДЗ ---
    if request.method == "POST" and request.form.get("action") != "upload_homework":
        # это обычный ввод 6-значного ID
        code = (request.form.get("code") or "").strip()
    else:
        # GET или upload_homework — берём code из query/формы
        code = (request.values.get("code") or "").strip()

    conn = get_db()
    conn.row_factory = sqlite3.Row

    # --- 2. Ищем ученика по public_code ---
    if code:
        student = conn.execute(
            "SELECT * FROM student_accounts WHERE public_code = ?",
            (code,),
        ).fetchone()
        if not student:
            not_found = True

    # --- 3. Если ученик найден — подтягиваем его расписание ---
    if student:
        rows = conn.execute(
            """
            SELECT *
            FROM student_lessons
            WHERE student_id = ?
            ORDER BY start_at
            """,
            (student["id"],),
        ).fetchall()

        for r in rows:
            status = (r["status"] or "").lower() if "status" in r.keys() else ""
            # если вдруг нет статуса — считаем по умолчанию "planned"
            if not status:
                status = "planned"

            if status == "planned":
                lessons_planned.append(r)
            elif status == "rescheduled":
                lessons_rescheduled.append(r)
            elif status == "done":
                lessons_done.append(r)
            elif status == "canceled":
                lessons_canceled.append(r)
            else:
                # неизвестный статус — можно тоже считать запланированным
                lessons_planned.append(r)

    # --- 4. Обработка загрузки домашнего задания ---
    if student and request.method == "POST" and request.form.get("action") == "upload_homework":
        file = request.files.get("hw_file")
        title = (request.form.get("hw_title") or "").strip()
        comment = (request.form.get("hw_comment") or "").strip()

        if file and file.filename and hw_allowed(file.filename):
            filename = secure_filename(file.filename)
            # чтобы не было коллизий имён — добавим дату и ID
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            new_name = f"stu{student['id']}_{ts}_{filename}"
            abs_path = os.path.join(HOMEWORK_UPLOAD_FOLDER, new_name)
            file.save(abs_path)

            rel_path = f"uploads/homework/{new_name}"

            conn.execute(
                """
                INSERT INTO student_homework (
                    student_id, title, comment,
                    file_name, file_path, status
                ) VALUES (?, ?, ?, ?, ?, 'new')
                """,
                (
                    student["id"],
                    title or None,
                    comment or None,
                    filename,
                    rel_path,
                ),
            )
            conn.commit()

        # после загрузки — обновим список ДЗ
        homework_list = conn.execute(
            """
            SELECT *
            FROM student_homework
            WHERE student_id = ?
            ORDER BY created_at DESC
            """,
            (student["id"],),
        ).fetchall()

    elif student:
        # просто просмотр — подтягиваем список домашних
        homework_list = conn.execute(
            """
            SELECT *
            FROM student_homework
            WHERE student_id = ?
            ORDER BY created_at DESC
            """,
            (student["id"],),
        ).fetchall()

    conn.close()

    return render_template(
        "student_dashboard.html",
        code=code,
        student=student,
        not_found=not_found,
        homework_list=homework_list,
        lessons_planned=lessons_planned,
        lessons_rescheduled=lessons_rescheduled,
        lessons_done=lessons_done,
        lessons_canceled=lessons_canceled,
    )


@app.route("/teacher/homework")
@teacher_login_required  # или login_required, как тебе надо
def teacher_homework_list():
    conn = get_db()
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT h.*, s.name AS student_name, s.public_code
        FROM student_homework h
        JOIN student_accounts s ON s.id = h.student_id
        ORDER BY h.created_at DESC
        LIMIT 200
    """).fetchall()

    conn.close()
    return render_template("teacher_homework_list.html", homework=rows)





@app.errorhandler(500)
def internal_error_handler(error):
    print("\n" + "="*60)
    print("🔥 INTERNAL SERVER ERROR")
    print("-"*60)
    traceback.print_exc()
    print("="*60 + "\n")
    return "Произошла внутренняя ошибка сервера. Ошибка записана в лог.", 500

@app.get("/teacher/students/<int:sid>/lessons")
@teacher_login_required
def teacher_student_lessons(sid):
    conn = get_db()
    conn.row_factory = sqlite3.Row

    student = conn.execute(
        "SELECT * FROM student_accounts WHERE id = ?",
        (sid,),
    ).fetchone()
    if not student:
        conn.close()
        return redirect(url_for("teacher_students"))

    lessons = conn.execute(
        """
        SELECT * FROM student_lessons
        WHERE student_id = ?
        ORDER BY start_at
        """,
        (sid,),
    ).fetchall()
    conn.close()

    return render_template(
        "teacher_lessons.html",
        student=student,
        lessons=lessons,
    )

@app.route("/teacher/students/<int:sid>/lessons/add", methods=["GET", "POST"])
@teacher_login_required
def teacher_student_lesson_add(sid):
    conn = get_db()
    conn.row_factory = sqlite3.Row
    student = conn.execute(
        "SELECT * FROM student_accounts WHERE id = ?",
        (sid,),
    ).fetchone()
    if not student:
        conn.close()
        return redirect(url_for("teacher_students"))

    if request.method == "POST":
        start_at = (request.form.get("start_at") or "").strip()
        status = (request.form.get("status") or "planned").strip()
        rescheduled_to = (request.form.get("rescheduled_to") or "").strip()
        topic = (request.form.get("topic") or "").strip()
        comment = (request.form.get("comment") or "").strip()

        conn.execute(
            """
            INSERT INTO student_lessons (student_id, start_at, status, rescheduled_to, topic, comment)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                sid,
                start_at,
                status,
                rescheduled_to or None,
                topic or None,
                comment or None,
            ),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("teacher_student_lessons", sid=sid))

    conn.close()
    return render_template("teacher_lesson_form.html", student=student, lesson=None)

@app.route("/teacher/lessons/<int:lid>/edit", methods=["GET", "POST"])
@teacher_login_required
def teacher_lesson_edit(lid):
    conn = get_db()
    conn.row_factory = sqlite3.Row
    lesson = conn.execute(
        "SELECT * FROM student_lessons WHERE id = ?",
        (lid,),
    ).fetchone()

    if not lesson:
        conn.close()
        return redirect(url_for("teacher_students"))

    student = conn.execute(
        "SELECT * FROM student_accounts WHERE id = ?",
        (lesson["student_id"],),
    ).fetchone()

    if request.method == "POST":
        start_at = (request.form.get("start_at") or "").strip()
        status = (request.form.get("status") or "planned").strip()
        rescheduled_to = (request.form.get("rescheduled_to") or "").strip()
        topic = (request.form.get("topic") or "").strip()
        comment = (request.form.get("comment") or "").strip()

        conn.execute(
            """
            UPDATE student_lessons
            SET start_at = ?, status = ?, rescheduled_to = ?, topic = ?, comment = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                start_at,
                status,
                rescheduled_to or None,
                topic or None,
                comment or None,
                lid,
            ),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("teacher_student_lessons", sid=lesson["student_id"]))

    conn.close()
    return render_template("teacher_lesson_form.html", student=student, lesson=lesson)

@app.route("/teacher/schedule")
@teacher_login_required
def teacher_schedule():
    conn = get_db()
    conn.row_factory = sqlite3.Row

    # все преподаватели для селекта
    teachers = conn.execute(
        "SELECT id, name FROM teachers ORDER BY name COLLATE NOCASE"
    ).fetchall()

    # выбранный препод и месяц
    teacher_id = request.args.get("teacher_id") or ""
    month_str = request.args.get("month")  # формат YYYY-MM

    today = datetime.today()
    if month_str:
        try:
            year, month = map(int, month_str.split("-"))
        except ValueError:
            year, month = today.year, today.month
    else:
        year, month = today.year, today.month

    teacher = None
    lessons_by_day = {}

    if teacher_id:
        # сам препод
        teacher = conn.execute(
            "SELECT * FROM teachers WHERE id = ?",
            (teacher_id,),
        ).fetchone()

        # диапазон дат: [1 число месяца; 1 число следующего месяца)
        if month == 12:
            month_start = datetime(year, 12, 1)
            month_end = datetime(year + 1, 1, 1)
        else:
            month_start = datetime(year, month, 1)
            month_end = datetime(year, month + 1, 1)

        # ВАЖНО: тут нужна колонка teacher_id в student_accounts
        # и связь с student_lessons
        rows = conn.execute(
            """
            SELECT sl.*, sa.name AS student_name
            FROM student_lessons sl
            JOIN student_accounts sa ON sa.id = sl.student_id
            WHERE sa.teacher_id = ?
              AND sl.start_at >= ?
              AND sl.start_at < ?
            ORDER BY sl.start_at
            """,
            (
                teacher_id,
                month_start.strftime("%Y-%m-%d %H:%M"),
                month_end.strftime("%Y-%m-%d %H:%M"),
            ),
        ).fetchall()

        for r in rows:
            day_key = r["start_at"][:10]  # 'YYYY-MM-DD'
            lessons_by_day.setdefault(day_key, []).append(r)

    conn.close()

    # строим календарную сетку
    cal = calendar.Calendar(firstweekday=0)  # 0 = понедельник
    weeks = []
    for week in cal.monthdatescalendar(year, month):
        week_cells = []
        for d in week:
            date_str = d.strftime("%Y-%m-%d")
            in_month = (d.month == month)
            week_cells.append(
                {
                    "date": d,
                    "in_month": in_month,
                    "lessons": lessons_by_day.get(date_str, []),
                }
            )
        weeks.append(week_cells)

    month_name = calendar.month_name[month]  # можно будет русифицировать в шаблоне

    return render_template(
        "teacher_schedule.html",
        teachers=teachers,
        teacher_id=teacher_id,
        teacher=teacher,
        year=year,
        month=month,
        month_str=f"{year:04d}-{month:02d}",
        month_name=month_name,
        weeks=weeks,
    )

@app.get("/teacher/students/export")
@teacher_login_required
def teacher_students_export():
    conn = get_db()
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT
            s.*,
            t.name AS teacher_name
        FROM student_accounts AS s
        LEFT JOIN teachers AS t ON t.id = s.teacher_id
        ORDER BY s.name COLLATE NOCASE
    """).fetchall()

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")

    writer.writerow([
        "ID",
        "Публичный код",
        "Имя",
        "Курс",
        "Преподаватель",
        "Всего занятий",
        "Осталось занятий",
        "Последняя оплата (дата)",
        "Последняя оплата (₽)",
        "Комментарий",
    ])

    for r in rows:
        writer.writerow([
            r["id"],
            r["public_code"] or "",
            r["name"] or "",
            r["course"] or "",
            r["teacher_name"] or "",
            r["lessons_total"] or "",
            r["lessons_left"] or "",
            r["last_payment_date"] or "",
            r["last_payment_amount"] or "",
            r["comment"] or "",
        ])

    data = output.getvalue().encode("utf-8-sig")  # BOM, чтобы Excel нормально понял UTF-8
    buf = io.BytesIO(data)
    buf.seek(0)

    return send_file(
        buf,
        mimetype="text/csv; charset=utf-8",
        as_attachment=True,
        download_name=f"students_{datetime.now().date()}.csv",
    )


@app.post("/teacher/lessons/<int:lid>/delete")
@teacher_login_required
def teacher_lesson_delete(lid):
    conn = get_db()
    row = conn.execute(
        "SELECT student_id FROM student_lessons WHERE id = ?",
        (lid,),
    ).fetchone()
    if not row:
        conn.close()
        return redirect(url_for("teacher_students"))
    sid = row["student_id"]

    conn.execute("DELETE FROM student_lessons WHERE id = ?", (lid,))
    conn.commit()
    conn.close()
    return redirect(url_for("teacher_student_lessons", sid=sid))


# ================== DEV-запуск ==================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
