import os
import random
from datetime import datetime
from typing import List, Optional
from flask import current_app
import json
from .db import get_db

def split_tags(s: str) -> List[str]:
    if not s:
        return []
    return [t.strip() for t in s.split(",") if t.strip()]

def save_upload(file, folder: str) -> Optional[str]:
    if not file or not getattr(file, "filename", ""):
        return None
    if "." not in file.filename:
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in current_app.config["ALLOWED_EXT"]:
        return None
    filename = f"{datetime.utcnow().timestamp()}.{ext}"
    filepath = os.path.join(folder, filename)
    file.save(filepath)
    return filename

def hw_allowed(filename: str) -> bool:
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in current_app.config["ALLOWED_HW_EXTENSIONS"]

def generate_student_code() -> str:
    """Generate unique 6-digit code like 038421."""
    conn = get_db()
    while True:
        code = f"{random.randint(0, 999999):06d}"
        exists = conn.execute(
            "SELECT 1 FROM student_accounts WHERE public_code = ?",
            (code,),
        ).fetchone()
        if not exists:
            return code

def tags_to_json(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return "[]"
    # "❤️ Бесплатно, ⌛ 60 мин" -> ["❤️ Бесплатно", "⌛ 60 мин"]
    tags = [t.strip() for t in raw.split(",") if t.strip()]
    return json.dumps(tags, ensure_ascii=False)

def tags_json_to_text(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    if raw.startswith("["):
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return ", ".join(str(x).strip() for x in data if str(x).strip())
        except Exception:
            pass
    # если в БД лежит старый формат строкой — возвращаем как есть
    return raw

def tags_json_to_list(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
        except Exception:
            return []
    # совместимость со старым форматом
    return [t.strip() for t in raw.split(",") if t.strip()]
