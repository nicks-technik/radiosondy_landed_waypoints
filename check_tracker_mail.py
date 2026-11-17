#!/usr/bin/env python3
"""Hourly tracker-mail handler.

Looks for new messages from tracker@radiosondy.info in the Gmail inbox, takes
the link from the "Details" button and runs the radiosonde GPX script
(``main.py``) with it, which generates the GPX file and sends it as a ZIP to
Telegram.

A message is processed at most once; the message id is remembered in
``~/.hermes/logs/radiosondy_mail_state.json``. A message whose script run fails
is left unprocessed so the next hourly run retries it.

Usage:
    python check_tracker_mail.py [--dry-run] [--quiet]
"""

from __future__ import annotations

import argparse
import email
import imaplib
import json
import logging
import os
import re
import subprocess
import sys
from email.message import Message
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# --- Configuration -----------------------------------------------------------
GMAIL_ADDRESS = os.environ.get("RADIOSONDY_GMAIL_ADDRESS", "nick2faktor@gmail.com")
APP_PASSWORD_FILE = Path(
    os.environ.get("RADIOSONDY_APP_PASSWORD_FILE", "/home/hermes/.hermes/secrets/gmail_app_password")
)
TRACKER_SENDER = "tracker@radiosondy.info"
PROJECT_DIR = Path(__file__).resolve().parent
GPX_SCRIPT = PROJECT_DIR / "main.py"
STATE_FILE = Path(
    os.environ.get("RADIOSONDY_MAIL_STATE_FILE", "/home/hermes/.hermes/logs/radiosondy_mail_state.json")
)
ENV_FILE = Path("/home/hermes/.hermes/.env")
SCRIPT_TIMEOUT_S = 300

logger = logging.getLogger("radiosondy-mail")

DETAILS_LINK_RE = re.compile(r"https://radiosondy\.info/sonde(?:\.php|_archive\.php)\?sondenumber=[A-Za-z0-9]+")


# --- Helpers -----------------------------------------------------------------
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("State file unreadable, starting fresh: %s", STATE_FILE)
    return {"processed": []}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STATE_FILE)


def read_app_password() -> str:
    return APP_PASSWORD_FILE.read_text(encoding="utf-8").strip()


def html_parts(msg: Message) -> list[str]:
    parts: list[str] = []
    for part in msg.walk():
        if part.get_content_type() != "text/html":
            continue
        payload = part.get_payload(decode=True)
        if payload:
            parts.append(payload.decode("utf-8", errors="replace"))
    return parts


def details_link(msg: Message) -> str | None:
    """The href of the 'Details' button, falling back to any sonde link."""
    for html in html_parts(msg):
        soup = BeautifulSoup(html, "html.parser")
        for anchor in soup.find_all("a", href=True):
            if anchor.get_text(strip=True).lower() == "details":
                href = anchor["href"].strip()
                if DETAILS_LINK_RE.fullmatch(href):
                    return href
    for html in html_parts(msg):
        match = DETAILS_LINK_RE.search(html)
        if match:
            return match.group(0)
    return None


def tracker_messages(password: str) -> list[tuple[str, Message]]:
    """Return (message_id, parsed_message) for every tracker mail in the inbox."""
    result: list[tuple[str, Message]] = []
    with imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=30) as imap:
        imap.login(GMAIL_ADDRESS, password)
        imap.select("INBOX")
        typ, data = imap.search(None, "FROM", TRACKER_SENDER)
        if typ != "OK" or not data or not data[0]:
            return result
        for msg_id in data[0].split():
            typ, msg_data = imap.fetch(msg_id, "(BODY.PEEK[])")
            if typ != "OK" or not msg_data:
                continue
            part = msg_data[0]
            payload = part[1] if isinstance(part, tuple) and len(part) > 1 else b""
            if not isinstance(payload, (bytes, bytearray)):
                continue
            msg = email.message_from_bytes(payload)
            message_id = (msg.get("Message-ID") or msg.get("Message-Id") or "").strip("<>")
            if not message_id:
                fallback = msg_id.decode(errors="replace") if isinstance(msg_id, (bytes, bytearray)) else str(msg_id)
                message_id = f"rfc822:{fallback}"
            result.append((message_id, msg))
    return result


def run_gpx_script(url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GPX_SCRIPT), url],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=SCRIPT_TIMEOUT_S,
        check=False,
    )


def telegram_alert(text: str) -> None:
    """One ❌ to the News Group when the run itself fails."""
    if not ENV_FILE.exists():
        return
    env = {}
    for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"')
    token = env.get("NEWS_TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("NEWS_TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except requests.exceptions.RequestException as exc:
        logger.error("Telegram alert failed: %s", exc)


# --- Main --------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="do not run the GPX script")
    parser.add_argument("--quiet", action="store_true", help="suppress per-sonde output")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    state = load_state()
    processed = set(state.get("processed", []))
    password = read_app_password()

    ran = 0
    for message_id, msg in tracker_messages(password):
        if message_id in processed:
            continue

        subject = msg.get("Subject", "")
        url = details_link(msg)
        if not url:
            logger.warning("no Details link in %s (%s) - skipping", message_id, subject)
            processed.add(message_id)
            continue

        if args.dry_run:
            logger.info("would run %s for %s", GPX_SCRIPT.name, url)
            processed.add(message_id)
            ran += 1
            continue

        logger.info("running %s %s", GPX_SCRIPT.name, url)
        try:
            completed = run_gpx_script(url)
        except subprocess.TimeoutExpired:
            logger.error("script timed out for %s", url)
            telegram_alert(f"❌ radiosondy-mail: script timed out for {url}")
            continue

        if completed.returncode != 0:
            logger.error(
                "script failed for %s (exit %d): %s",
                url,
                completed.returncode,
                (completed.stderr or completed.stdout or "").strip()[-500:],
            )
            telegram_alert(f"❌ radiosondy-mail: script failed for {url} (exit {completed.returncode})")
            continue

        processed.add(message_id)
        ran += 1
        if not args.quiet:
            print(f"processed {url} -> GPX send OK")

    state["processed"] = sorted(processed)
    save_state(state)
    logger.info("run finished, %d message(s) handled", ran)
    return 0


if __name__ == "__main__":
    sys.exit(main())
