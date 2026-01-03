import os
from datetime import datetime

from flask import Flask, render_template, request, session, redirect, url_for, abort
from werkzeug.utils import secure_filename

from .db import get_db
from .utils import hw_allowed


def register_student_routes(app: Flask) -> None:

    def _load_student_by_session(conn):
        sid = session.get("student_id")
        if not sid:
            return None
        try:
            sid = int(sid)
        except (TypeError, ValueError):
            session.pop("student_id", None)
            return None

        student = conn.execute(
            "SELECT * FROM student_accounts WHERE id = ?",
            (sid,),
        ).fetchone()

        if not student:
            session.pop("student_id", None)
        return student

    def _load_student_by_code(conn, code: str):
        return conn.execute(
            "SELECT * FROM student_accounts WHERE public_code = ?",
            (code,),
        ).fetchone()

    def _split_lessons(rows):
        planned, rescheduled, done, canceled = [], [], [], []
        for r in rows:
            status = (r["status"] or "").lower() if "status" in r.keys() else ""
            if not status:
                status = "planned"

            if status == "planned":
                planned.append(r)
            elif status == "rescheduled":
                rescheduled.append(r)
            elif status == "done":
                done.append(r)
            elif status == "canceled":
                canceled.append(r)
            else:
                planned.append(r)
        return planned, rescheduled, done, canceled

    @app.route("/student", methods=["GET", "POST"])
    def student_dashboard():
        conn = get_db()

        not_found = False

        # ---------- POST: либо "вход по коду", либо "загрузка ДЗ" ----------
        if request.method == "POST":
            action = (request.form.get("action") or "").strip()

            # 1) вход по коду
            if action != "upload_homework":
                code = (request.form.get("code") or "").strip()
                if not code:
                    not_found = True
                    return render_template(
                        "student_dashboard.html",
                        code="",
                        student=None,
                        not_found=not_found,
                        homework_list=[],
                        lessons_planned=[],
                        lessons_rescheduled=[],
                        lessons_done=[],
                        lessons_canceled=[],
                    )

                student = _load_student_by_code(conn, code)
                if not student:
                    not_found = True
                    return render_template(
                        "student_dashboard.html",
                        code=code,
                        student=None,
                        not_found=not_found,
                        homework_list=[],
                        lessons_planned=[],
                        lessons_rescheduled=[],
                        lessons_done=[],
                        lessons_canceled=[],
                    )

                # Сохраняем в сессию и делаем redirect (PRG!)
                session["student_id"] = student["id"]
                return redirect(url_for("student_dashboard"))

            # 2) загрузка домашки
            student = _load_student_by_session(conn)
            if not student:
                # нет сессии -> на страницу входа
                return redirect(url_for("student_dashboard"))

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

            # ВАЖНО: после POST тоже редиректим (PRG!), чтобы “Назад” не просил повторить POST
            return redirect(url_for("student_dashboard"))

        # ---------- GET ----------
        # Если пришли по ссылке /student?code=XXXX — залогиним в session и почистим URL
        code_qs = (request.args.get("code") or "").strip()
        if code_qs:
            student = _load_student_by_code(conn, code_qs)
            if not student:
                not_found = True
                return render_template(
                    "student_dashboard.html",
                    code=code_qs,
                    student=None,
                    not_found=not_found,
                    homework_list=[],
                    lessons_planned=[],
                    lessons_rescheduled=[],
                    lessons_done=[],
                    lessons_canceled=[],
                )
            session["student_id"] = student["id"]
            return redirect(url_for("student_dashboard"))

        # Обычный вход: пробуем взять ученика из session
        student = _load_student_by_session(conn)

        lessons_planned = []
        lessons_rescheduled = []
        lessons_done = []
        lessons_canceled = []
        homework_list = []

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

            lessons_planned, lessons_rescheduled, lessons_done, lessons_canceled = _split_lessons(rows)

            homework_list = conn.execute(
                "SELECT * FROM student_homework WHERE student_id = ? ORDER BY created_at DESC",
                (student["id"],),
            ).fetchall()

        return render_template(
            "student_dashboard.html",
            # code в URL мы больше не держим (это нормально). Если хочешь — можно показать student["public_code"].
            code=student["public_code"] if student else "",
            student=student,
            not_found=not_found,
            homework_list=homework_list,
            lessons_planned=lessons_planned,
            lessons_rescheduled=lessons_rescheduled,
            lessons_done=lessons_done,
            lessons_canceled=lessons_canceled,
        )

    @app.get("/student/logout")
    def student_logout():
        session.pop("student_id", None)
        return redirect(url_for("student_dashboard"))
