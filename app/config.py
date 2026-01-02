import os
from pathlib import Path

class Config:
    """Runtime configuration loaded from environment variables."""

    def __init__(self):
        base_dir = Path(__file__).resolve().parent.parent  # /opt/Soul (when deployed)
        self.BASE_DIR = str(base_dir)
        self.DB_PATH = str(base_dir / "soul.db")

        # Flask
        self.SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "change-me")
        self.MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20 MB

        # Admin auth
        self.ADMIN_USER = os.getenv("ADMIN_USER", "")
        self.ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

        # Teacher auth
        self.TEACHER_KEY = os.getenv("TEACHER_KEY", "")

        # Anti spam
        self.ENROLL_SPAM_SECONDS = int(os.getenv("ENROLL_SPAM_SECONDS", "60"))

        # Telegram
        self.TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
        self.TELEGRAM_API_SECRET = os.getenv("TELEGRAM_API_SECRET", "change_me")

        # Uploads
        upload_folder = base_dir / "static" / "uploads"
        self.UPLOAD_FOLDER = str(upload_folder)
        self.TEACHER_UPLOAD = str(upload_folder / "teachers")
        self.COURSE_UPLOAD = str(upload_folder / "courses")
        self.GALLERY_UPLOAD = str(upload_folder / "gallery")
        self.HOMEWORK_UPLOAD_FOLDER = str(upload_folder / "homework")

        self.ALLOWED_EXT = {"png", "jpg", "jpeg", "webp"}
        self.ALLOWED_HW_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "doc", "docx", "ppt", "pptx", "zip", "txt"}
