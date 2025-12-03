import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

resp = requests.post(
    url,
    json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": "Тестовое сообщение от Soul-сайта ✅",
    },
    timeout=10,
)

print("Status:", resp.status_code)
print("Response:", resp.text)
