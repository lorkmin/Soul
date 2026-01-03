import os
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename

from .db import get_db
from .auth import login_required

def _allowed_pdf(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() == "pdf"

def register_admin_materials_routes(app: Flask) -> None:

    @app.get("/admin/materials")
    @login_required
    def admin_materials():
        conn = get_db()
        materials = conn.execute("""
            SELECT m.*,
                   s.name AS student_name
            FROM materials m
            LEFT JOIN student_accounts s ON s.id = m.student_id
            ORDER BY m.sort_order DESC, m.created_at DESC, m.id DESC
        """).fetchall()

        students = conn.execute("""
            SELECT id, name, public_code, course
            FROM student_accounts
            ORDER BY name
            LIMIT 500
        """).fetchall()

        return render_template("admin_materials.html", materials=materials, students=students)

    @app.post("/admin/materials/add")
    @login_required
    def admin_materials_add():
        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip()
        mtype = (request.form.get("type") or "").strip()  # video/pdf/link
        url = (request.form.get("url") or "").strip()

        visibility = (request.form.get("visibility") or "all").strip()
        course = (request.form.get("course") or "").strip() or None
        student_id_raw = (request.form.get("student_id") or "").strip()
        student_id = int(student_id_raw) if student_id_raw.isdigit() else None

        sort_order_raw = (request.form.get("sort_order") or "0").strip()
        sort_order = int(sort_order_raw) if sort_order_raw.lstrip("-").isdigit() else 0
        is_published = 1 if (request.form.get("is_published") == "1") else 0

        if not title:
            flash("Название обязательно", "error")
            return redirect(url_for("admin_materials"))

        file_path = None
        if mtype == "pdf":
            f = request.files.get("file")
            if not f or not f.filename:
                flash("Для PDF нужно загрузить файл", "error")
                return redirect(url_for("admin_materials"))
            if not _allowed_pdf(f.filename):
                flash("Разрешены только PDF", "error")
                return redirect(url_for("admin_materials"))

            os.makedirs(app.config["MATERIALS_UPLOAD_FOLDER"], exist_ok=True)
            safe_name = secure_filename(f.filename)
            # уникализируем
            base, ext = os.path.splitext(safe_name)
            final_name = safe_name
            abs_path = os.path.join(app.config["MATERIALS_UPLOAD_FOLDER"], final_name)
            i = 1
            while os.path.exists(abs_path):
                final_name = f"{base}_{i}{ext}"
                abs_path = os.path.join(app.config["MATERIALS_UPLOAD_FOLDER"], final_name)
                i += 1

            f.save(abs_path)
            file_path = f"uploads/materials/{final_name}"
            url = None  # для pdf url не нужен

        elif mtype in ("video", "link"):
            if not url:
                flash("Для ссылки/видео нужно указать URL", "error")
                return redirect(url_for("admin_materials"))
        else:
            flash("Неверный тип материала", "error")
            return redirect(url_for("admin_materials"))

        # нормализуем visibility
        if visibility not in ("all", "course", "student"):
            visibility = "all"
        if visibility != "course":
            course = None
        if visibility != "student":
            student_id = None

        conn = get_db()
        conn.execute("""
            INSERT INTO materials
            (title, description, type, url, file_path, visibility, course, student_id, sort_order, is_published)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (title, description or None, mtype, url or None, file_path, visibility, course, student_id, sort_order, is_published))
        conn.commit()

        flash("Материал добавлен", "success")
        return redirect(url_for("admin_materials"))

    @app.post("/admin/materials/<int:mid>/delete")
    @login_required
    def admin_materials_delete(mid: int):
        conn = get_db()
        row = conn.execute("SELECT * FROM materials WHERE id=?", (mid,)).fetchone()
        if not row:
            return redirect(url_for("admin_materials"))

        # удалить pdf с диска (best-effort)
        if row["type"] == "pdf" and row["file_path"]:
            abs_path = os.path.join(app.static_folder, row["file_path"])
            try:
                if os.path.exists(abs_path):
                    os.remove(abs_path)
            except OSError:
                pass

        conn.execute("DELETE FROM materials WHERE id=?", (mid,))
        conn.commit()
        flash("Удалено", "success")
        return redirect(url_for("admin_materials"))
