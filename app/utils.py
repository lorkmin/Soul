import os
import random
from datetime import datetime
from typing import List, Optional
from flask import current_app

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
