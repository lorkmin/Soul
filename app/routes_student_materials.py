from flask import Flask, render_template, session, redirect, url_for, request
from .db import get_db
from .auth import student_login_required

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
        conn = get_db()

        student_id = session.get("student_id")
        student = conn.execute(
            "SELECT * FROM student_accounts WHERE id = ?",
            (student_id,),
        ).fetchone()

        # если вдруг ученик удалён/битая сессия
        if not student:
            session.pop("student_id", None)
            return redirect(url_for("student_dashboard"))

        # TODO: тут уже твоя таблица материалов
        rows = conn.execute(
            """
            SELECT *
            FROM student_materials
            WHERE is_published = 1
            ORDER BY created_at DESC
            """
        ).fetchall()

        return render_template(
            "student_materials.html",
            student=student,
            materials=rows,
        )

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
