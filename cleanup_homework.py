#!/usr/bin/env python3
import os
import time
from datetime import datetime, timedelta

# Папка, где лежат загруженные домашки
HOMEWORK_DIR = "/opt/Soul/static/uploads/homework"

# Сколько дней храним файлы
KEEP_DAYS = 20

def cleanup():
    if not os.path.isdir(HOMEWORK_DIR):
        print(f"Directory not found: {HOMEWORK_DIR}")
        return

    now = time.time()
    cutoff = now - KEEP_DAYS * 24 * 3600

    deleted = 0

    for fname in os.listdir(HOMEWORK_DIR):
        full_path = os.path.join(HOMEWORK_DIR, fname)

        if not os.path.isfile(full_path):
            continue

        file_mtime = os.path.getmtime(full_path)

        if file_mtime < cutoff:
            try:
                os.remove(full_path)
                deleted += 1
                print(f"[✔] Deleted: {fname}")
            except Exception as e:
                print(f"[!] Error deleting {fname}: {e}")

    print(f"Cleanup complete. Deleted {deleted} old file(s).")

if __name__ == "__main__":
    cleanup()
