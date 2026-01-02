import calendar
import csv
import io
import os
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from werkzeug.utils import secure_filename

from .auth import teacher_login_required
from .db import get_db
from .utils import generate_student_code, hw_allowed

def register_teacher_routes(app: Flask) -> None:

    # ===== Teacher auth (by TEACHER_KEY) =====

    @app.get("/teacher/login")
    def teacher_login():
        error = request.args.get("error")
        return render_template("teacher_login.html", error=error)

    @app.post("/teacher/login")
    def teacher_login_post():
        code = (request.form.get("code") or "").strip()
        if app.config.get("TEACHER_KEY") and code == app.config["TEACHER_KEY"]:
            session["teacher_logged_in"] = True
            next_url = request.args.get("next") or url_for("teacher_students")
            return redirect(next_url)
        error = "Неверный ID преподавателя"
        return render_template("teacher_login.html", error=error)

    @app.get("/teacher/logout")
    def teacher_logout():
        session.pop("teacher_logged_in", None)
        return redirect(url_for("teacher_login"))

    # ===== Students =====

    @app.get("/teacher/students")
    @teacher_login_required
    def teacher_students():
        conn = get_db()
        students = conn.execute("""
            SELECT s.*, t.name AS teacher_name
            FROM student_accounts AS s
            LEFT JOIN teachers AS t ON t.id = s.teacher_id
            ORDER BY s.name COLLATE NOCASE
        """).fetchall()
        return render_template("teacher_students.html", students=students)

    @app.route("/teacher/students/add", methods=["GET", "POST"])
    @teacher_login_required
    def teacher_students_add():
        conn = get_db()
        if request.method == "POST":
            name = (request.form.get("name") or "").strip()
            course = (request.form.get("course") or "").strip()
            last_payment_date = (request.form.get("last_payment_date") or "").strip()
            last_payment_amount = request.form.get("last_payment_amount") or None
            lessons_total = request.form.get("lessons_total") or None
            lessons_left = request.form.get("lessons_left") or None
            comment = (request.form.get("comment") or "").strip()
            teacher_id = request.form.get("teacher_id") or None

            code = generate_student_code()

            conn.execute(
                """
                INSERT INTO student_accounts (
                    public_code, name, course, last_payment_date, last_payment_amount,
                    lessons_total, lessons_left, comment, teacher_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    code,
                    name or None,
                    course or None,
                    last_payment_date or None,
                    int(last_payment_amount) if last_payment_amount else None,
                    int(lessons_total) if lessons_total else None,
                    int(lessons_left) if lessons_left else None,
                    comment or None,
                    int(teacher_id) if teacher_id else None,
                ),
            )
            conn.commit()
            return redirect(url_for("teacher_students"))

        teachers = conn.execute("SELECT id, name FROM teachers ORDER BY name").fetchall()
        return render_template("teacher_student_form.html", student=None, teachers=teachers)

    @app.route("/teacher/students/<int:sid>/edit", methods=["GET", "POST"])
    @teacher_login_required
    def teacher_students_edit(sid: int):
        conn = get_db()
        student = conn.execute("SELECT * FROM student_accounts WHERE id = ?", (sid,)).fetchone()
        if not student:
            return redirect(url_for("teacher_students"))

        if request.method == "POST":
            name = (request.form.get("name") or "").strip()
            course = (request.form.get("course") or "").strip()
            last_payment_date = (request.form.get("last_payment_date") or "").strip()
            last_payment_amount = request.form.get("last_payment_amount") or None
            lessons_total = request.form.get("lessons_total") or None
            lessons_left = request.form.get("lessons_left") or None
            comment = (request.form.get("comment") or "").strip()
            teacher_id = request.form.get("teacher_id") or None

            conn.execute(
                """
                UPDATE student_accounts
                SET name=?, course=?, last_payment_date=?, last_payment_amount=?,
                    lessons_total=?, lessons_left=?, comment=?, teacher_id=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    name or None,
                    course or None,
                    last_payment_date or None,
                    int(last_payment_amount) if last_payment_amount else None,
                    int(lessons_total) if lessons_total else None,
                    int(lessons_left) if lessons_left else None,
                    comment or None,
                    int(teacher_id) if teacher_id else None,
                    sid,
                ),
            )
            conn.commit()
            return redirect(url_for("teacher_students"))

        teachers = conn.execute("SELECT id, name FROM teachers ORDER BY name").fetchall()
        return render_template("teacher_student_form.html", student=student, teachers=teachers)

    @app.post("/teacher/students/<int:sid>/delete")
    @teacher_login_required
    def teacher_students_delete(sid: int):
        conn = get_db()
        conn.execute("DELETE FROM student_accounts WHERE id = ?", (sid,))
        conn.commit()
        return redirect(url_for("teacher_students"))

    @app.get("/teacher/students/export")
    @teacher_login_required
    def teacher_students_export():
        conn = get_db()
        rows = conn.execute("""
            SELECT s.*, t.name AS teacher_name
            FROM student_accounts AS s
            LEFT JOIN teachers AS t ON t.id = s.teacher_id
            ORDER BY s.name COLLATE NOCASE
        """).fetchall()

        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")
        writer.writerow([
            "ID","Публичный код","Имя","Курс","Преподаватель",
            "Всего занятий","Осталось занятий","Последняя оплата (дата)",
            "Последняя оплата (₽)","Комментарий",
        ])
        for r in rows:
            writer.writerow([
                r["id"],
                r["public_code"] or "",
                r["name"] or "",
                r["course"] or "",
                r["teacher_name"] or "",
                r["lessons_total"] or "",
                r["lessons_left"] or "",
                r["last_payment_date"] or "",
                r["last_payment_amount"] or "",
                r["comment"] or "",
            ])

        data = output.getvalue().encode("utf-8-sig")
        buf = io.BytesIO(data); buf.seek(0)
        return send_file(
            buf,
            mimetype="text/csv; charset=utf-8",
            as_attachment=True,
            download_name=f"students_{datetime.now().date()}.csv",
        )

    # ===== Lessons =====

    @app.get("/teacher/students/<int:sid>/lessons")
    @teacher_login_required
    def teacher_student_lessons(sid: int):
        conn = get_db()
        student = conn.execute("SELECT * FROM student_accounts WHERE id = ?", (sid,)).fetchone()
        if not student:
            return redirect(url_for("teacher_students"))

        lessons = conn.execute(
            "SELECT * FROM student_lessons WHERE student_id = ? ORDER BY start_at",
            (sid,),
        ).fetchall()

        return render_template("teacher_lessons.html", student=student, lessons=lessons)

    @app.route("/teacher/students/<int:sid>/lessons/add", methods=["GET", "POST"])
    @teacher_login_required
    def teacher_student_lesson_add(sid: int):
        conn = get_db()
        student = conn.execute("SELECT * FROM student_accounts WHERE id = ?", (sid,)).fetchone()
        if not student:
            return redirect(url_for("teacher_students"))

        if request.method == "POST":
            start_at = (request.form.get("start_at") or "").strip()
            status = (request.form.get("status") or "planned").strip()
            rescheduled_to = (request.form.get("rescheduled_to") or "").strip()
            topic = (request.form.get("topic") or "").strip()
            comment = (request.form.get("comment") or "").strip()

            conn.execute(
                """
                INSERT INTO student_lessons (student_id, start_at, status, rescheduled_to, topic, comment)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (sid, start_at, status, rescheduled_to or None, topic or None, comment or None),
            )
            conn.commit()
            return redirect(url_for("teacher_student_lessons", sid=sid))

        return render_template("teacher_lesson_form.html", student=student, lesson=None)

    @app.route("/teacher/lessons/<int:lid>/edit", methods=["GET", "POST"])
    @teacher_login_required
    def teacher_lesson_edit(lid: int):
        conn = get_db()
        lesson = conn.execute("SELECT * FROM student_lessons WHERE id = ?", (lid,)).fetchone()
        if not lesson:
            return redirect(url_for("teacher_students"))

        student = conn.execute("SELECT * FROM student_accounts WHERE id = ?", (lesson["student_id"],)).fetchone()

        if request.method == "POST":
            start_at = (request.form.get("start_at") or "").strip()
            status = (request.form.get("status") or "planned").strip()
            rescheduled_to = (request.form.get("rescheduled_to") or "").strip()
            topic = (request.form.get("topic") or "").strip()
            comment = (request.form.get("comment") or "").strip()

            conn.execute(
                """
                UPDATE student_lessons
                SET start_at=?, status=?, rescheduled_to=?, topic=?, comment=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (start_at, status, rescheduled_to or None, topic or None, comment or None, lid),
            )
            conn.commit()
            return redirect(url_for("teacher_student_lessons", sid=lesson["student_id"]))

        return render_template("teacher_lesson_form.html", student=student, lesson=lesson)

    @app.post("/teacher/lessons/<int:lid>/delete")
    @teacher_login_required
    def teacher_lesson_delete(lid: int):
        conn = get_db()
        row = conn.execute("SELECT student_id FROM student_lessons WHERE id = ?", (lid,)).fetchone()
        if not row:
            return redirect(url_for("teacher_students"))
        sid = row["student_id"]
        conn.execute("DELETE FROM student_lessons WHERE id = ?", (lid,))
        conn.commit()
        return redirect(url_for("teacher_student_lessons", sid=sid))

    # ===== Teacher schedule =====

    @app.get("/teacher/schedule")
    @teacher_login_required
    def teacher_schedule():
        conn = get_db()

        teachers = conn.execute(
            "SELECT id, name FROM teachers ORDER BY name COLLATE NOCASE"
        ).fetchall()

        teacher_id = request.args.get("teacher_id") or ""
        month_str = request.args.get("month")

        today = datetime.today()
        if month_str:
            try:
                year, month = map(int, month_str.split("-"))
            except ValueError:
                year, month = today.year, today.month
        else:
            year, month = today.year, today.month

        teacher = None
        lessons_by_day = {}

        if teacher_id:
            teacher = conn.execute("SELECT * FROM teachers WHERE id = ?", (teacher_id,)).fetchone()

            if month == 12:
                month_start = datetime(year, 12, 1)
                month_end = datetime(year + 1, 1, 1)
            else:
                month_start = datetime(year, month, 1)
                month_end = datetime(year, month + 1, 1)

            rows = conn.execute(
                """
                SELECT sl.*, sa.name AS student_name
                FROM student_lessons sl
                JOIN student_accounts sa ON sa.id = sl.student_id
                WHERE sa.teacher_id = ?
                  AND sl.start_at >= ?
                  AND sl.start_at < ?
                ORDER BY sl.start_at
                """,
                (
                    teacher_id,
                    month_start.strftime("%Y-%m-%d %H:%M"),
                    month_end.strftime("%Y-%m-%d %H:%M"),
                ),
            ).fetchall()

            for r in rows:
                day_key = r["start_at"][:10]
                lessons_by_day.setdefault(day_key, []).append(r)

        cal = calendar.Calendar(firstweekday=0)
        weeks = []
        for week in cal.monthdatescalendar(year, month):
            week_cells = []
            for d in week:
                date_str = d.strftime("%Y-%m-%d")
                week_cells.append({
                    "date": d,
                    "in_month": d.month == month,
                    "lessons": lessons_by_day.get(date_str, []),
                })
            weeks.append(week_cells)

        month_name = calendar.month_name[month]

        return render_template(
            "teacher_schedule.html",
            teachers=teachers,
            teacher_id=teacher_id,
            teacher=teacher,
            year=year,
            month=month,
            month_str=f"{year:04d}-{month:02d}",
            month_name=month_name,
            weeks=weeks,
        )

    # ===== Homework =====

    @app.get("/teacher/homework")
    @teacher_login_required
    def teacher_homework_list():
        conn = get_db()
        rows = conn.execute("""
            SELECT
                h.*,
                s.name AS student_name,
                s.public_code AS student_code,
                s.course AS student_course
            FROM student_homework h
            JOIN student_accounts s ON s.id = h.student_id
            ORDER BY h.created_at DESC
            LIMIT 200
        """).fetchall()
        return render_template("teacher_homework_list.html", homework=rows)

    @app.route("/teacher/homework/<int:hw_id>", methods=["GET", "POST"])
    @teacher_login_required
    def teacher_homework_review(hw_id: int):
        conn = get_db()
        hw = conn.execute("""
            SELECT
                h.*,
                s.name AS student_name,
                s.public_code AS student_code,
                s.course AS student_course
            FROM student_homework h
            JOIN student_accounts s ON s.id = h.student_id
            WHERE h.id = ?
        """, (hw_id,)).fetchone()

        if not hw:
            flash("Домашнее задание не найдено", "error")
            return redirect(url_for("teacher_homework_list"))

        if request.method == "POST":
            status = request.form.get("status") or "checked"
            teacher_comment = (request.form.get("teacher_comment") or "").strip()
            file = request.files.get("teacher_file")

            teacher_file_name = hw["teacher_file_name"]
            teacher_file_path = hw["teacher_file_path"]

            if file and file.filename and hw_allowed(file.filename):
                orig_name = secure_filename(file.filename)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                new_name = f"hw{hw['id']}_reply_{ts}_{orig_name}"
                abs_path = os.path.join(app.config["HOMEWORK_UPLOAD_FOLDER"], new_name)
                file.save(abs_path)
                teacher_file_name = orig_name
                teacher_file_path = f"uploads/homework/{new_name}"

            conn.execute("""
                UPDATE student_homework
                SET status=?, teacher_comment=?, teacher_file_name=?, teacher_file_path=?,
                    checked_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (
                status,
                teacher_comment or None,
                teacher_file_name,
                teacher_file_path,
                hw_id,
            ))
            conn.commit()
            flash("Домашнее задание обновлено", "success")
            return redirect(url_for("teacher_homework_list"))

        return render_template("teacher_homework_review.html", hw=hw)

    @app.post("/teacher/homework/<int:hw_id>/delete")
    @teacher_login_required
    def teacher_homework_delete(hw_id: int):
        """Delete homework row and files (student+teacher) if present."""
        conn = get_db()
        hw = conn.execute("SELECT * FROM student_homework WHERE id = ?", (hw_id,)).fetchone()
        if not hw:
            flash("Домашнее задание не найдено", "error")
            return redirect(url_for("teacher_homework_list"))

        # delete files on disk (best-effort)
        for rel in (hw["file_path"], hw["teacher_file_path"]):
            if rel:
                abs_path = os.path.join(app.static_folder, rel)
                try:
                    if os.path.exists(abs_path):
                        os.remove(abs_path)
                except OSError:
                    pass

        conn.execute("DELETE FROM student_homework WHERE id = ?", (hw_id,))
        conn.commit()
        flash("Домашнее задание удалено", "success")
        return redirect(url_for("teacher_homework_list"))

    @app.route("/teacher/homework/add", methods=["GET", "POST"])
    @teacher_login_required
    def teacher_homework_add():
        conn = get_db()
        conn.row_factory = sqlite3.Row

        # список учеников для выбора
        students = conn.execute("""
            SELECT id, name, public_code, course
            FROM student_accounts
            ORDER BY name COLLATE NOCASE
        """).fetchall()

        if request.method == "POST":
            student_id = request.form.get("student_id")
            title = (request.form.get("title") or "").strip()
            teacher_comment = (request.form.get("teacher_comment") or "").strip()
            file = request.files.get("teacher_file")

            if not student_id:
                conn.close()
                return redirect(url_for("teacher_homework_add"))

            teacher_file_name = None
            teacher_file_path = None

            if file and file.filename and hw_allowed(file.filename):
                orig_name = secure_filename(file.filename)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                new_name = f"task_stu{student_id}_{ts}_{orig_name}"
                abs_path = os.path.join(HOMEWORK_UPLOAD_FOLDER, new_name)
                file.save(abs_path)

                teacher_file_name = orig_name
                teacher_file_path = f"uploads/homework/{new_name}"

            conn.execute("""
                INSERT INTO student_homework (
                    student_id,
                    title,
                    comment,
                    file_name,
                    file_path,
                    status,
                    teacher_comment,
                    teacher_file_name,
                    teacher_file_path
                ) VALUES (?, ?, NULL, NULL, NULL, 'assigned', ?, ?, ?)
            """, (
                int(student_id),
                title or None,
                teacher_comment or None,
                teacher_file_name,
                teacher_file_path,
            ))
            conn.commit()
            conn.close()
            return redirect(url_for("teacher_homework_list"))

        conn.close()
        return render_template("teacher_homework_add.html", students=students)

    # NOTE: выдача нового задания ученику (teacher_homework_add) оставлена как ранее,
    # но для работы нужен шаблон teacher_homework_add.html.
