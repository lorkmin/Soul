import os
from flask import Flask, render_template, session, redirect, url_for, request, abort, send_file

from .db import get_db
from .auth import student_login_required

from collections import OrderedDict


def _material_allowed_for_student(m, student) -> bool:
    if not m or not m["is_published"]:
        return False

    vis = (m["visibility"] or "all")
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

        if not student:
            session.pop("student_id", None)
            session.pop("student_code", None)
            return redirect(url_for("student_dashboard"))

        # ВАЖНО: таблица называется materials (а не student_materials)
        rows = conn.execute("""
            SELECT *
            FROM materials
            WHERE is_published = 1
            ORDER BY
            COALESCE(topic, '') ASC,
            sort_order DESC,
            created_at DESC,
            id DESC
        """).fetchall()


        # фильтруем по доступности
        allowed = [m for m in rows if _material_allowed_for_student(m, student)]

        groups = OrderedDict()
        for m in rows:
            # фильтр доступа
            if not _material_allowed_for_student(m, student):
                continue

            topic = (m["topic"] or "Без темы").strip()
            groups.setdefault(topic, []).append(m)


        return render_template(
            "student_materials.html",
            student=student,
            groups=groups,
        )


    @app.get("/student/materials/<int:mid>/pdf")
    @student_login_required
    def student_material_pdf(mid: int):
        conn = get_db()

        student_id = session.get("student_id")
        student = conn.execute(
            "SELECT * FROM student_accounts WHERE id = ?",
            (student_id,),
        ).fetchone()
        if not student:
            abort(403)

        m = conn.execute("SELECT * FROM materials WHERE id=?", (mid,)).fetchone()
        if not m or m["type"] != "pdf" or not m["file_path"]:
            abort(404)

        if not _material_allowed_for_student(m, student):
            abort(403)

        abs_path = os.path.join(app.static_folder, m["file_path"])
        if not os.path.exists(abs_path):
            abort(404)

        # inline => откроется в браузере
        return send_file(
            abs_path,
            mimetype="application/pdf",
            as_attachment=False,
            download_name=os.path.basename(abs_path),
            conditional=True,
            etag=True,
            max_age=0,
        )
