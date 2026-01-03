import os
from datetime import datetime

from flask import Flask, render_template, request, session

from werkzeug.utils import secure_filename

from .db import get_db
from .utils import hw_allowed

def register_student_routes(app: Flask) -> None:

    @app.route("/student", methods=["GET", "POST"])
    def student_dashboard():
        code = None
        student = None
        not_found = False

        lessons_planned = []
        lessons_rescheduled = []
        lessons_done = []
        lessons_canceled = []
        homework_list = []

        # Determine code:
        if request.method == "POST" and request.form.get("action") != "upload_homework":
            code = (request.form.get("code") or "").strip()
        else:
            code = (request.values.get("code") or "").strip()

        conn = get_db()

        if code:
            student = conn.execute(
                "SELECT * FROM student_accounts WHERE public_code = ?",
                (code,),
            ).fetchone()
            if not student:
                not_found = True
                session.pop("student_id", None)  # <-- чтобы не оставалась старая сессия
            else:
                session["student_id"] = student["id"]  # <-- ВОТ ЭТО


        if student:
            rows = conn.execute(
                """
                SELECT *
                FROM student_lessons
                WHERE student_id = ?
                ORDER BY start_at
                """,
                (student["id"],),
            ).fetchall()

            for r in rows:
                status = (r["status"] or "").lower() if "status" in r.keys() else ""
                if not status:
                    status = "planned"
                if status == "planned":
                    lessons_planned.append(r)
                elif status == "rescheduled":
                    lessons_rescheduled.append(r)
                elif status == "done":
                    lessons_done.append(r)
                elif status == "canceled":
                    lessons_canceled.append(r)
                else:
                    lessons_planned.append(r)

        # Upload homework
        if student and request.method == "POST" and request.form.get("action") == "upload_homework":
            file = request.files.get("hw_file")
            title = (request.form.get("hw_title") or "").strip()
            comment = (request.form.get("hw_comment") or "").strip()

            if file and file.filename and hw_allowed(file.filename):
                filename = secure_filename(file.filename)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                new_name = f"stu{student['id']}_{ts}_{filename}"
                abs_path = os.path.join(app.config["HOMEWORK_UPLOAD_FOLDER"], new_name)
                file.save(abs_path)

                rel_path = f"uploads/homework/{new_name}"

                conn.execute(
                    """
                    INSERT INTO student_homework (student_id, title, comment, file_name, file_path, status)
                    VALUES (?, ?, ?, ?, ?, 'new')
                    """,
                    (student["id"], title or None, comment or None, filename, rel_path),
                )
                conn.commit()

            homework_list = conn.execute(
                "SELECT * FROM student_homework WHERE student_id = ? ORDER BY created_at DESC",
                (student["id"],),
            ).fetchall()

        elif student:
            homework_list = conn.execute(
                "SELECT * FROM student_homework WHERE student_id = ? ORDER BY created_at DESC",
                (student["id"],),
            ).fetchall()

        return render_template(
            "student_dashboard.html",
            code=code,
            student=student,
            not_found=not_found,
            homework_list=homework_list,
            lessons_planned=lessons_planned,
            lessons_rescheduled=lessons_rescheduled,
            lessons_done=lessons_done,
            lessons_canceled=lessons_canceled,
        )
