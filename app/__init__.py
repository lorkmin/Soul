import os
from flask import Flask

from .config import Config
from .db import init_db
from .filters import register_filters
from .routes_public import register_public_routes
from .routes_admin import register_admin_routes
from .routes_teacher import register_teacher_routes
from .routes_student import register_student_routes

def create_app() -> Flask:
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config.from_object(Config())

    # filters
    register_filters(app)

    # ensure folders exist
    for p in (
        app.config["UPLOAD_FOLDER"],
        app.config["TEACHER_UPLOAD"],
        app.config["COURSE_UPLOAD"],
        app.config["GALLERY_UPLOAD"],
        app.config["HOMEWORK_UPLOAD_FOLDER"],
    ):
        os.makedirs(p, exist_ok=True)

    # DB init/migrations (lightweight)
    init_db(app)

    # routes
    register_public_routes(app)
    register_admin_routes(app)
    register_teacher_routes(app)
    register_student_routes(app)

    return app
