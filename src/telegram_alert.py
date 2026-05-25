import requests


def send_telegram_message(token: str, chat_id: str, message: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    response = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        },
        timeout=10,
    )

    response.raise_for_status()