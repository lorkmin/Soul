import requests

TELEGRAM_BOT_TOKEN = "7586193673:AAE_MeqS01U4s7ZAzntj5thXoyRCtP2PxjU"
TELEGRAM_CHAT_ID = "-1003426957203"

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
