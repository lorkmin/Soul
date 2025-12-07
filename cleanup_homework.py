#!/usr/bin/env python3
import os
import time
import sqlite3
from datetime import datetime, timedelta

# Корневая папка проекта
PROJECT_ROOT = "/opt/Soul"

# Папка, где лежат загруженные домашки
HOMEWORK_DIR = os.path.join(PROJECT_ROOT, "static", "uploads", "homework")

# Путь к БД
DB_PATH = os.path.join(PROJECT_ROOT, "soul.db")

# Сколько дней храним файлы
KEEP_DAYS = 20


def cleanup_files():
    """Удаляет файлы из HOMEWORK_DIR, старше KEEP_DAYS."""
    if not os.path.isdir(HOMEWORK_DIR):
        print(f"Directory not found: {HOMEWORK_DIR}")
        return []

    now = time.time()
    cutoff = now - KEEP_DAYS * 24 * 3600

    deleted_rel_paths = []

    for fname in os.listdir(HOMEWORK_DIR):
        full_path = os.path.join(HOMEWORK_DIR, fname)

        if not os.path.isfile(full_path):
            continue

        file_mtime = os.path.getmtime(full_path)

        if file_mtime < cutoff:
            try:
                os.remove(full_path)
                # В БД путь хранится как "uploads/homework/имя"
                rel_path = os.path.join("uploads", "homework", fname)
                deleted_rel_paths.append(rel_path)
                print(f"[✔] Deleted file: {rel_path}")
            except Exception as e:
                print(f"[!] Error deleting {fname}: {e}")

    print(f"File cleanup complete. Deleted {len(deleted_rel_paths)} old file(s).")
    return deleted_rel_paths


def cleanup_db(deleted_rel_paths):
    """
    Удаляет записи из student_homework, у которых:
      - file_path == одному из удалённых путей
      - ИЛИ файл по file_path вообще не существует на диске.
    """
    if not os.path.exists(DB_PATH):
        print(f"DB not found: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1) Удаляем записи по уже удалённым файлам (из этого запуска)
    total_deleted = 0
    if deleted_rel_paths:
        qmarks = ",".join("?" for _ in deleted_rel_paths)
        cur.execute(
            f"DELETE FROM student_homework WHERE file_path IN ({qmarks})",
            deleted_rel_paths,
        )
        total_deleted += cur.rowcount
        print(f"[DB] Deleted {cur.rowcount} rows by recently removed files.")

    # 2) Дополнительно сканируем все записи и убираем те, у кого файла уже нет
    cur.execute("SELECT id, file_path FROM student_homework")
    rows = cur.fetchall()

    ids_to_delete = []
    for r in rows:
        file_path = r["file_path"]
        if not file_path:
            continue
        full_path = os.path.join(PROJECT_ROOT, "static", file_path)
        if not os.path.exists(full_path):
            ids_to_delete.append(r["id"])

    if ids_to_delete:
        qmarks = ",".join("?" for _ in ids_to_delete)
        cur.execute(
            f"DELETE FROM student_homework WHERE id IN ({qmarks})",
            ids_to_delete,
        )
        total_deleted += cur.rowcount
        print(f"[DB] Deleted {cur.rowcount} rows with missing files on disk.")

    conn.commit()
    conn.close()
    print(f"DB cleanup complete. Total deleted rows: {total_deleted}.")


def main():
    print("=== Homework cleanup started ===")
    deleted_paths = cleanup_files()
    cleanup_db(deleted_paths)
    print("=== Homework cleanup finished ===")


if __name__ == "__main__":
    main()
