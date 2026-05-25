import requests

MAX_TELEGRAM_MESSAGE_LENGTH = 3500

def split_message(
    message: str,
    limit: int = MAX_TELEGRAM_MESSAGE_LENGTH
) -> list[str]:

    chunks = []
    current_chunk = ""
    for line in message.splitlines(keepends=True):
        if len(current_chunk) + len(line) > limit:
            chunks.append(current_chunk)
            current_chunk = line
        else:
            current_chunk += line

    if current_chunk:
        chunks.append(current_chunk)

    return chunks

def send_telegram_message(
    token: str,
    chat_id: str,
    message: str
) -> None:

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    message_chunks = split_message(message)
    for chunk in message_chunks:
        response = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "HTML",
            },
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