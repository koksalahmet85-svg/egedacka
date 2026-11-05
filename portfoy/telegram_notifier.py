"""
telegram_notifier.py — raporu Telegram Bot API ile gönderir.

Ortam değişkenleri (GitHub'da repo Secrets olarak tanımlanır):
  TELEGRAM_BOT_TOKEN   BotFather'ın verdiği token
  TELEGRAM_CHAT_ID     Mesajın gideceği sohbet ID'si

Test:  TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... python3 telegram_notifier.py "deneme"
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("cloue.telegram")
API = "https://api.telegram.org/bot{token}/sendMessage"
LIMIT = 4000  # Telegram sınırı 4096 karakter


def _chunks(text: str, size: int = LIMIT):
    buf = ""
    for line in text.splitlines(keepends=True):
        if len(buf) + len(line) > size:
            yield buf
            buf = ""
        buf += line
    if buf:
        yield buf


def _post(token: str, chat_id: str, text: str, retries: int = 4) -> bool:
    # <pre> blok: hizalı tablo, HTML kaçışı gerekli
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": f"<pre>{safe}</pre>", "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"}).encode()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(API.format(token=token), data=body)
            with urllib.request.urlopen(req, timeout=20) as r:
                if json.load(r).get("ok"):
                    return True
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="ignore")[:200]
            if e.code == 429:  # rate limit: Telegram'ın söylediği kadar bekle
                wait = json.loads(detail or "{}").get("parameters", {}).get("retry_after", 2 ** attempt)
                time.sleep(wait); continue
            if 400 <= e.code < 500:  # token/chat_id hatası: tekrar denemenin anlamı yok
                log.error("Telegram %s: %s", e.code, detail); return False
            log.warning("Telegram %s (deneme %d)", e.code, attempt + 1)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            log.warning("Telegram bağlantı hatası (deneme %d): %s", attempt + 1, e)
        time.sleep(2 ** attempt)
    return False


def send_message(text: str) -> bool:
    """Mesajı gönderir; başarısız olursa False döner ama programı düşürmez."""
    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID tanımlı değil; mesaj atlanıyor.")
        return False
    return all(_post(token, chat_id, part) for part in _chunks(text))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(0 if send_message(" ".join(sys.argv[1:]) or "Cloue test mesajı ✅") else 1)
