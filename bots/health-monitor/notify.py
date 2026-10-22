"""
Send health report to Telegram.
"""

import requests
import config


def send_telegram(text: str, chat_id: int = None, parse_mode: str = "Markdown"):
    """Send message to Telegram."""
    chat_id = chat_id or config.CHAT_ID
    url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage"

    # Split long messages (Telegram limit is 4096 chars)
    chunks = split_message(text, 4000)

    for chunk in chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": parse_mode,
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code != 200:
                # Retry without parse_mode if markdown fails
                payload["parse_mode"] = None
                resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
        except Exception as e:
            print(f"Telegram send error: {e}")
            # Last resort: try plain text
            try:
                payload["parse_mode"] = None
                payload["text"] = chunk
                requests.post(url, json=payload, timeout=10)
            except Exception as e2:
                print(f"Telegram send failed completely: {e2}")


def split_message(text: str, max_len: int = 4000) -> list:
    """Split long message into chunks."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break

        # Find a good split point
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len

        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")

    return chunks
