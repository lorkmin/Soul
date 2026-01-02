import requests
from flask import current_app

def send_enroll_to_telegram(payload: dict) -> None:
    token = current_app.config.get("TELEGRAM_BOT_TOKEN")
    chat_id = current_app.config.get("TELEGRAM_CHAT_ID")
    if (not token) or (not chat_id) or ("YOUR_TELEGRAM_BOT_TOKEN_HERE" in token):
        return

    text_lines = [
        "📝 *Новая заявка на занятия*",
        "",
        f"👤 Имя: {payload.get('name') or '-'}",
        f"📨 Контакт: {payload.get('contact') or '-'}",
        f"📦 Пакет: {payload.get('tariff') or 'не выбран'}",
        f"📊 Уровень: {payload.get('level') or '-'}",
    ]
    comment = payload.get("comment")
    if comment:
        text_lines.append("")
        text_lines.append(f"💬 Комментарий:\n{comment}")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(
            url,
            json={"chat_id": chat_id, "text": "\n".join(text_lines), "parse_mode": "Markdown"},
            timeout=10,
        )
    except requests.RequestException:
        pass

def send_review_to_telegram(review: dict) -> None:
    # stub
    return

def send_enroll_email_to_user(payload: dict) -> None:
    # stub
    return
