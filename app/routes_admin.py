import csv
import io
import sqlite3
from flask import Flask, app, render_template, request, redirect, url_for, send_file, session

from .auth import login_required
from .db import get_db
from .utils import save_upload
from datetime import datetime, timedelta
def register_admin_routes(app: Flask) -> None:

    @app.get("/admin")
    @login_required
    def admin_dashboard():
        conn = get_db()

        # последние 7 дней
        since_dt = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

        stats = {}

        # Заявки
        stats["enrolls_total"] = conn.execute("SELECT COUNT(*) FROM enrolls").fetchone()[0]
        stats["enrolls_7d"] = conn.execute(
            "SELECT COUNT(*) FROM enrolls WHERE created_at >= ?",
            (since_dt,),
        ).fetchone()[0]
        # Боты (если колонка есть)
        try:
            stats["bots_total"] = conn.execute("SELECT COUNT(*) FROM enrolls WHERE is_bot = 1").fetchone()[0]
            stats["bots_7d"] = conn.execute(
                "SELECT COUNT(*) FROM enrolls WHERE is_bot = 1 AND created_at >= ?",
                (since_dt,),
            ).fetchone()[0]
        except Exception:
            stats["bots_total"] = 0
            stats["bots_7d"] = 0

        # Ученики
        stats["students_total"] = conn.execute("SELECT COUNT(*) FROM student_accounts").fetchone()[0]
        stats["students_no_teacher"] = conn.execute(
            "SELECT COUNT(*) FROM student_accounts WHERE teacher_id IS NULL"
        ).fetchone()[0]

        # Домашки
        stats["hw_total"] = conn.execute("SELECT COUNT(*) FROM student_homework").fetchone()[0]
        stats["hw_new"] = conn.execute(
            "SELECT COUNT(*) FROM student_homework WHERE status = 'new'"
        ).fetchone()[0]
        stats["hw_7d"] = conn.execute(
            "SELECT COUNT(*) FROM student_homework WHERE created_at >= ?",
            (since_dt,),
        ).fetchone()[0]

        # Материалы
        stats["materials_total"] = conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
        stats["materials_published"] = conn.execute("SELECT COUNT(*) FROM materials WHERE is_published = 1").fetchone()[0]

        # Быстрые списки (небольшие)
        last_enrolls = conn.execute("""
            SELECT id, name, contact, created_at, is_bot
            FROM enrolls
            ORDER BY id DESC
            LIMIT 5
        """).fetchall()

        hw_new_list = conn.execute("""
            SELECT h.id, h.title, h.created_at, s.name AS student_name, s.public_code AS student_code
            FROM student_homework h
            JOIN student_accounts s ON s.id = h.student_id
            WHERE h.status = 'new'
            ORDER BY h.created_at DESC
            LIMIT 5
        """).fetchall()

        return render_template(
            "admin_dashboard.html",
            stats=stats,
            last_enrolls=last_enrolls,
            hw_new_list=hw_new_list,
        )

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        error = None
        next_url = request.args.get("next") or url_for("admin_enrolls")

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()

            if username == app.config["ADMIN_USER"] and password == app.config["ADMIN_PASSWORD"]:
                session["admin_logged_in"] = True
                return redirect(next_url)
            error = "Неверный логин или пароль"

        return render_template("admin_login.html", error=error)

    @app.get("/admin/logout")
    def admin_logout():
        session.pop("admin_logged_in", None)
        return redirect(url_for("admin_login"))

    @app.get("/admin")
    @login_required
    def admin_index():
        return redirect(url_for("admin_enrolls"))

    # ===== ENROLLS =====

    @app.get("/admin/enrolls")
    @login_required
    def admin_enrolls():
        conn = get_db()
        enrolls = conn.execute(
            """
            SELECT id, created_at, ip, name, contact, tariff, level, comment,
                   COALESCE(is_bot, 0) AS is_bot,
                   admin_note
            FROM enrolls
            ORDER BY created_at DESC
            LIMIT 500
            """
        ).fetchall()
        return render_template("admin_enrolls.html", enrolls=enrolls)

    @app.post("/admin/enrolls/<int:enroll_id>/note")
    @login_required
    def admin_enroll_note(enroll_id: int):
        """Update admin note + bot flag for an enroll row."""
        note = (request.form.get("admin_note") or "").strip()

        # из-за hidden + checkbox может прийти ["0"] или ["0","1"]
        is_bot_vals = [v.strip().lower() for v in request.form.getlist("is_bot")]
        is_bot = 1 if "1" in is_bot_vals or "true" in is_bot_vals or "on" in is_bot_vals or "yes" in is_bot_vals else 0

        conn = get_db()
        conn.execute(
            "UPDATE enrolls SET admin_note = ?, is_bot = ? WHERE id = ?",
            (note or None, is_bot, enroll_id),
        )
        conn.commit()
        return redirect(url_for("admin_enrolls"))

        return redirect(url_for("admin_enrolls"))

    @app.get("/admin/enrolls/export")
    @login_required
    def admin_enrolls_export():
        conn = get_db()
        rows = conn.execute(
            """
            SELECT id, created_at, ip, name, contact, tariff, level, comment,
                   COALESCE(is_bot, 0) AS is_bot,
                   admin_note
            FROM enrolls
            ORDER BY created_at DESC
            """
        ).fetchall()

        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")
        writer.writerow([
            "id", "created_at", "ip", "name", "contact",
            "tariff", "level", "comment", "is_bot", "admin_note"
        ])
        for row in rows:
            writer.writerow([
                row["id"],
                row["created_at"],
                row["ip"],
                row["name"],
                row["contact"],
                row["tariff"] or "",
                row["level"] or "",
                row["comment"] or "",
                int(row["is_bot"] or 0),
                row["admin_note"] or "",
            ])

        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode("utf-8-sig")),
            mimetype="text/csv; charset=utf-8",
            as_attachment=True,
            download_name="enrolls.csv",
        )

    # ===== REVIEWS =====

    @app.get("/admin/reviews")
    @login_required
    def admin_reviews():
        conn = get_db()
        reviews = conn.execute(
            """
            SELECT id, created_at, name, package, rating, text, approved
            FROM reviews
            ORDER BY created_at DESC
            LIMIT 500
            """
        ).fetchall()
        return render_template("admin_reviews.html", reviews=reviews)

    @app.post("/admin/reviews/<int:review_id>/approve")
    @login_required
    def admin_review_approve(review_id: int):
        conn = get_db()
        conn.execute("UPDATE reviews SET approved = 1 WHERE id = ?", (review_id,))
        conn.commit()
        return redirect(url_for("admin_reviews"))

    @app.post("/admin/reviews/<int:review_id>/hide")
    @login_required
    def admin_review_hide(review_id: int):
        conn = get_db()
        conn.execute("UPDATE reviews SET approved = 0 WHERE id = ?", (review_id,))
        conn.commit()
        return redirect(url_for("admin_reviews"))

    @app.post("/admin/reviews/<int:review_id>/delete")
    @login_required
    def admin_review_delete(review_id: int):
        conn = get_db()
        conn.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
        conn.commit()
        return redirect(url_for("admin_reviews"))

    # ===== TEACHERS =====

    @app.get("/admin/teachers")
    @login_required
    def admin_teachers():
        conn = get_db()
        rows = conn.execute("SELECT * FROM teachers ORDER BY created_at DESC").fetchall()
        return render_template("admin_teachers.html", teachers=rows)

    @app.post("/admin/teachers/add")
    @login_required
    def admin_teachers_add():
        name = request.form["name"]
        role = request.form.get("role", "")
        bio = request.form.get("bio", "")
        highlights = request.form.get("highlights", "")
        badges = request.form.get("badges", "")

        photo = None
        file = request.files.get("photo")
        if file and file.filename:
            photo = save_upload(file, app.config["TEACHER_UPLOAD"])

        conn = get_db()
        conn.execute(
            """
            INSERT INTO teachers (name, role, bio, photo, highlights, badges)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, role, bio, photo, highlights, badges),
        )
        conn.commit()
        return redirect(url_for("admin_teachers"))

    @app.route("/admin/teachers/<int:tid>/edit", methods=["GET", "POST"])
    @login_required
    def admin_teachers_edit(tid: int):
        conn = get_db()
        teacher = conn.execute("SELECT * FROM teachers WHERE id = ?", (tid,)).fetchone()
        if not teacher:
            return redirect(url_for("admin_teachers"))

        if request.method == "POST":
            name = request.form["name"]
            role = request.form.get("role", "")
            bio = request.form.get("bio", "")
            highlights = request.form.get("highlights", "")
            badges = request.form.get("badges", "")

            file = request.files.get("photo")
            new_photo = save_upload(file, app.config["TEACHER_UPLOAD"]) if file and file.filename else None

            if new_photo:
                conn.execute(
                    """
                    UPDATE teachers
                    SET name = ?, role = ?, bio = ?, photo = ?, highlights = ?, badges = ?
                    WHERE id = ?
                    """,
                    (name, role, bio, new_photo, highlights, badges, tid),
                )
            else:
                conn.execute(
                    """
                    UPDATE teachers
                    SET name = ?, role = ?, bio = ?, highlights = ?, badges = ?
                    WHERE id = ?
                    """,
                    (name, role, bio, highlights, badges, tid),
                )
            conn.commit()
            return redirect(url_for("admin_teachers"))

        return render_template("admin_teacher_edit.html", teacher=teacher)

    @app.post("/admin/teachers/delete/<int:tid>")
    @login_required
    def admin_teachers_delete(tid: int):
        conn = get_db()
        conn.execute("DELETE FROM teachers WHERE id = ?", (tid,))
        conn.commit()
        return redirect(url_for("admin_teachers"))

    # ===== COURSES =====

    @app.get("/admin/courses")
    @login_required
    def admin_courses():
        conn = get_db()
        rows = conn.execute("SELECT * FROM courses ORDER BY created_at DESC").fetchall()
        return render_template("admin_courses.html", courses=rows)

    @app.post("/admin/courses/add")
    @login_required
    def admin_courses_add():
        title = request.form["title"]
        price = request.form.get("price") or None
        lessons = request.form.get("lessons") or None
        description = request.form.get("description", "")
        hero_tags = (request.form.get("hero_tags") or "").strip()

        photo = save_upload(request.files.get("photo"), app.config["COURSE_UPLOAD"])

        conn = get_db()
        conn.execute(
            """
            INSERT INTO courses (title, price, lessons, description, photo, hero_tags)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (title, price, lessons, description, photo, hero_tags),
        )
        conn.commit()
        return redirect(url_for("admin_courses"))

    @app.post("/admin/courses/delete/<int:cid>")
    @login_required
    def admin_courses_delete(cid: int):
        conn = get_db()
        conn.execute("DELETE FROM courses WHERE id = ?", (cid,))
        conn.commit()
        return redirect(url_for("admin_courses"))

    @app.route("/admin/courses/<int:cid>/edit", methods=["GET", "POST"])
    @login_required
    def admin_courses_edit(cid: int):
        conn = get_db()
        course = conn.execute("SELECT * FROM courses WHERE id = ?", (cid,)).fetchone()
        if not course:
            return redirect(url_for("admin_courses"))

        if request.method == "POST":
            title = request.form["title"]
            price = request.form.get("price") or None
            lessons = request.form.get("lessons") or None
            description = request.form.get("description", "")
            hero_tags = (request.form.get("hero_tags") or "").strip()

            file = request.files.get("photo")
            new_photo = save_upload(file, app.config["COURSE_UPLOAD"]) if file and file.filename else None

            if new_photo:
                conn.execute(
                    """
                    UPDATE courses
                    SET title=?, price=?, lessons=?, description=?, photo=?, hero_tags=?
                    WHERE id=?
                    """,
                    (title, price, lessons, description, new_photo, hero_tags, cid),
                )
            else:
                conn.execute(
                    """
                    UPDATE courses
                    SET title=?, price=?, lessons=?, description=?, hero_tags=?
                    WHERE id=?
                    """,
                    (title, price, lessons, description, hero_tags, cid),
                )
            conn.commit()
            return redirect(url_for("admin_courses"))

        return render_template("admin_course_edit.html", course=course)

    # ===== GALLERY =====

    @app.get("/admin/gallery")
    @login_required
    def admin_gallery():
        conn = get_db()
        images = conn.execute("SELECT * FROM gallery ORDER BY created_at DESC").fetchall()
        return render_template("admin_gallery.html", images=images)

    @app.post("/admin/gallery/add")
    @login_required
    def admin_gallery_add():
        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip()
        photo = save_upload(request.files.get("photo"), app.config["GALLERY_UPLOAD"])
        if not photo:
            return redirect(url_for("admin_gallery"))

        conn = get_db()
        conn.execute(
            "INSERT INTO gallery (title, description, photo) VALUES (?, ?, ?)",
            (title or None, description or None, photo),
        )
        conn.commit()
        return redirect(url_for("admin_gallery"))

    @app.post("/admin/gallery/delete/<int:gid>")
    @login_required
    def admin_gallery_delete(gid: int):
        conn = get_db()
        conn.execute("DELETE FROM gallery WHERE id = ?", (gid,))
        conn.commit()
        return redirect(url_for("admin_gallery"))
