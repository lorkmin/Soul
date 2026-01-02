from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, jsonify

from .db import get_db
from .telegram import send_enroll_to_telegram, send_review_to_telegram, send_enroll_email_to_user

def register_public_routes(app: Flask) -> None:

    @app.get("/")
    def index():
        conn = get_db()
        reviews = conn.execute("""
            SELECT name, package, rating, text, created_at
            FROM reviews
            WHERE approved = 1
            ORDER BY created_at DESC
            LIMIT 9;
        """).fetchall()

        teachers = conn.execute("SELECT * FROM teachers ORDER BY created_at DESC").fetchall()
        courses = conn.execute("SELECT * FROM courses ORDER BY created_at ASC").fetchall()
        gallery = conn.execute("SELECT * FROM gallery ORDER BY created_at DESC LIMIT 12").fetchall()
        return render_template(
            "index.html",
            reviews=reviews,
            teachers=teachers,
            courses=courses,
            gallery=gallery,
        )

    @app.post("/add-review")
    def add_review():
        name = request.form.get("name", "").strip()
        package = request.form.get("package", "").strip()
        rating_raw = request.form.get("rating", "5").strip()
        text = request.form.get("text", "").strip()

        if not name or not text:
            return redirect(url_for("index"))

        try:
            rating = int(rating_raw)
            if rating < 1 or rating > 5:
                rating = 5
        except ValueError:
            rating = 5

        conn = get_db()
        conn.execute(
            "INSERT INTO reviews (name, package, rating, text, approved) VALUES (?, ?, ?, ?, 0)",
            (name, package or None, rating, text),
        )
        conn.commit()

        send_review_to_telegram({"name": name, "package": package, "rating": rating, "text": text})
        return redirect(url_for("index"))

    @app.post("/api/telegram/review")
    def api_telegram_review():
        data = request.get_json(force=True, silent=True) or {}
        secret = data.get("secret")
        if secret != app.config.get("TELEGRAM_API_SECRET", "change_me"):
            return jsonify({"ok": False, "error": "forbidden"}), 403

        name = (data.get("name") or "").strip()
        package = (data.get("package") or "").strip()
        rating = data.get("rating") or 5
        text = (data.get("text") or "").strip()
        if not name or not text:
            return jsonify({"ok": False, "error": "name and text required"}), 400

        try:
            rating = int(rating)
            if rating < 1 or rating > 5:
                rating = 5
        except (TypeError, ValueError):
            rating = 5

        conn = get_db()
        conn.execute(
            "INSERT INTO reviews (name, package, rating, text, approved) VALUES (?, ?, ?, ?, 0)",
            (name, package or None, rating, text),
        )
        conn.commit()

        send_review_to_telegram({"name": name, "package": package, "rating": rating, "text": text})
        return jsonify({"ok": True})

    @app.post("/enroll")
    def enroll():
        name = (request.form.get("name") or "").strip()
        contact = (request.form.get("contact") or "").strip()
        tariff = (request.form.get("tariff") or "").strip()
        level = (request.form.get("level") or "").strip()
        comment = (request.form.get("comment") or "").strip()

        if not name or not contact:
            return redirect(url_for("index"))

        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
        now = datetime.utcnow()

        conn = get_db()
        row = conn.execute(
            "SELECT created_at FROM enrolls WHERE ip = ? ORDER BY created_at DESC LIMIT 1",
            (ip,),
        ).fetchone()
        if row and row["created_at"]:
            try:
                last_dt = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
                if now - last_dt < timedelta(seconds=app.config["ENROLL_SPAM_SECONDS"]):
                    return redirect(url_for("thank_you"))
            except ValueError:
                pass

        conn.execute(
            """
            INSERT INTO enrolls (ip, name, contact, tariff, level, comment)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ip, name, contact, tariff or None, level or None, comment or None),
        )
        conn.commit()

        payload = {"name": name, "contact": contact, "tariff": tariff, "level": level, "comment": comment}
        send_enroll_to_telegram(payload)
        send_enroll_email_to_user(payload)

        return redirect(url_for("thank_you"))

    @app.get("/thanks")
    def thank_you():
        return render_template("thank_you.html")
