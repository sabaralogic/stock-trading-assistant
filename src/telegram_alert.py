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

def send_telegram_photo(
    token: str,
    chat_id: str,
    photo_path: str,
    caption: str = ""
) -> None:

    url = f"https://api.telegram.org/bot{token}/sendPhoto"

    with open(photo_path, "rb") as photo:

        response = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "caption": caption,
            },
            files={
                "photo": photo,
            },
        )

    response.raise_for_status()