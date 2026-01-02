import sqlite3
from flask import Flask, g, current_app

def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(current_app.config["DB_PATH"])
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db

def close_db(e=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()

def init_db(app: Flask) -> None:
    """Create tables and run lightweight migrations."""
    app.teardown_appcontext(close_db)

    db_path = app.config["DB_PATH"]
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # REVIEWS
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

    # ENROLLS
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
    # migrations for enrolls
    for stmt in (
        "ALTER TABLE enrolls ADD COLUMN admin_note TEXT",
        "ALTER TABLE enrolls ADD COLUMN is_bot INTEGER DEFAULT 0",
    ):
        try:
            cur.execute(stmt)
        except sqlite3.OperationalError:
            pass

    # TEACHERS
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
    for stmt in (
        "ALTER TABLE teachers ADD COLUMN highlights TEXT",
        "ALTER TABLE teachers ADD COLUMN badges TEXT",
    ):
        try:
            cur.execute(stmt)
        except sqlite3.OperationalError:
            pass

    # COURSES
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

    # GALLERY
    cur.execute("""
        CREATE TABLE IF NOT EXISTS gallery (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            photo TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # STUDENT ACCOUNTS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS student_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            public_code TEXT NOT NULL UNIQUE,
            name TEXT,
            course TEXT,
            last_payment_date TEXT,
            last_payment_amount INTEGER,
            lessons_total INTEGER,
            lessons_left INTEGER,
            comment TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    try:
        cur.execute("ALTER TABLE student_accounts ADD COLUMN teacher_id INTEGER REFERENCES teachers(id)")
    except sqlite3.OperationalError:
        pass

    # STUDENT LESSONS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS student_lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            start_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned',
            rescheduled_to TEXT,
            topic TEXT,
            comment TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES student_accounts(id) ON DELETE CASCADE
        );
    """)

    # STUDENT HOMEWORK
    cur.execute("""
        CREATE TABLE IF NOT EXISTS student_homework (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            title TEXT,
            comment TEXT,
            file_name TEXT,
            file_path TEXT,
            status TEXT DEFAULT 'new',
            teacher_comment TEXT,
            teacher_file_name TEXT,
            teacher_file_path TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            checked_at DATETIME,
            FOREIGN KEY(student_id) REFERENCES student_accounts(id)
        );
    """)
    for stmt in (
        "ALTER TABLE student_homework ADD COLUMN teacher_file_name TEXT",
        "ALTER TABLE student_homework ADD COLUMN teacher_file_path TEXT",
    ):
        try:
            cur.execute(stmt)
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()
