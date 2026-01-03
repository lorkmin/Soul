import os
from flask import Flask, render_template, abort, send_file
from .db import get_db
from .auth import student_login_required  # у тебя он есть, раз есть кабинет ученика
from flask import abort
from .auth import teacher_login_required, login_required  # эти у тебя точно есть?
from flask import session

try:
    from .auth import student_login_required
except ImportError:
    student_login_required = None

def require_student():
    # Подстрой под то, как у тебя хранится student_id в session
    sid = session.get("student_id")
    if not sid:
        abort(403)
    return int(sid)

def _material_allowed_for_student(m, student) -> bool:
    if not m or not m["is_published"]:
        return False

    vis = m["visibility"]
    if vis == "all":
        return True
    if vis == "course":
        return (m["course"] or "") == (student["course"] or "")
    if vis == "student":
        return m["student_id"] == student["id"]
    return False

def register_student_materials_routes(app: Flask) -> None:

    @app.get("/student/materials")
    @student_login_required
    def student_materials():
        # предполагаю: current student хранится в g / session и у тебя есть helper.
        # Если у тебя есть функция get_current_student() — используй её.
        # Ниже — пример, как обычно делают:
        from flask import g
        student = g.student  # <-- подстрой под свой проект

        conn = get_db()
        all_rows = conn.execute("""
            SELECT *
            FROM materials
            WHERE is_published=1
            ORDER BY sort_order DESC, created_at DESC, id DESC
        """).fetchall()

        materials = [m for m in all_rows if _material_allowed_for_student(m, student)]
        return render_template("student_materials.html", materials=materials)

    @app.get("/student/materials/<int:mid>/pdf")
    @student_login_required
    def student_material_pdf(mid: int):
        from flask import g
        student = g.student  # <-- подстрой под свой проект

        conn = get_db()
        m = conn.execute("SELECT * FROM materials WHERE id=?", (mid,)).fetchone()
        if not m or m["type"] != "pdf" or not m["file_path"]:
            abort(404)

        if not _material_allowed_for_student(m, student):
            abort(403)

        abs_path = os.path.join(app.static_folder, m["file_path"])
        if not os.path.exists(abs_path):
            abort(404)

        # ВАЖНО: inline => откроется в браузере
        return send_file(
            abs_path,
            mimetype="application/pdf",
            as_attachment=False,
            download_name=os.path.basename(abs_path),
            conditional=True,  # поддержка Range/кеширование
            etag=True,
            max_age=0,
        )
