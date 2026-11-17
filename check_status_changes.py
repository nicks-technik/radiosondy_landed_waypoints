#!/usr/bin/env python3
"""Daily radiosondy.info "Status Changes" watcher.

Watches the radiosondes that radiosondy.info's tracker (tracker@radiosondy.info)
announces by email, checks each sonde's "Status Changes" table on its archive
page once a day, and mails new entries to radiosonde@hornick.de.

Read-only w.r.t. the mailbox: the inbox is only searched, never modified.
State (which table rows were already reported) lives outside the git checkout,
in ~/.hermes/logs/radiosondy_status_state.json.

Usage:
    python check_status_changes.py [--dry-run] [--quiet]
"""

from __future__ import annotations

import argparse
import imaplib
import json
import logging
import os
import re
import smtplib
import sys
import time
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from xml.sax.saxutils import escape

import requests
from bs4 import BeautifulSoup

# --- Configuration -----------------------------------------------------------
GMAIL_ADDRESS = os.environ.get("RADIOSONDY_GMAIL_ADDRESS", "nick2faktor@gmail.com")
APP_PASSWORD_FILE = Path(
    os.environ.get("RADIOSONDY_APP_PASSWORD_FILE", "/home/hermes/.hermes/secrets/gmail_app_password")
)
RECIPIENT = os.environ.get("RADIOSONDY_NOTIFY_ADDRESS", "radiosonde@hornick.de")
TRACKER_SENDER = "tracker@radiosondy.info"
SONDE_PAGE_URL = "https://radiosondy.info/sonde_archive.php?sondenumber={sonde}"
PREDICT_KML_URL = "https://radiosondy.info/local_storage/PREDICT/{sonde}_predict.kml"
STATUS_TABLE_ID = "Table6"
STATE_FILE = Path(
    os.environ.get("RADIOSONDY_STATE_FILE", "/home/hermes/.hermes/logs/radiosondy_status_state.json")
)
ENV_FILE = Path("/home/hermes/.hermes/.env")

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
REQUEST_TIMEOUT_S = 30
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465

logger = logging.getLogger("radiosondy-status")

SONDE_TOKEN_RE = re.compile(r"\b[A-Z]{1,3}[0-9][A-Z0-9]{4,9}\b")
NEAREST_CITY_RE = re.compile(r"(?:Nearest City|Nächste Stadt)\s*:\s*([^<\"\[\]]+)", re.IGNORECASE)
LANDING_TIME_RE = re.compile(
    r"Balloon landing at [^<]*?at\s+(\d{4}-\d{2}-\d{2}T[\d:.]+Z)", re.IGNORECASE
)


# --- Helpers -----------------------------------------------------------------
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("State file unreadable, starting fresh: %s", STATE_FILE)
    return {"sondes": {}}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STATE_FILE)


def read_app_password() -> str:
    return APP_PASSWORD_FILE.read_text(encoding="utf-8").strip()


def norm(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())


# ---Mailbox: find announced sondes ------------------------------------------
def find_announced_sondes(password: str) -> list[str]:
    """Search the inbox for tracker@radiosondy.info mail and return sonde numbers."""
    found: list[str] = []
    try:
        with imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=30) as imap:
            imap.login(GMAIL_ADDRESS, password)
            imap.select("INBOX")
            typ, data = imap.search(None, "FROM", TRACKER_SENDER)
            if typ != "OK" or not data or not data[0]:
                return found
            for msg_id in data[0].split():
                typ, msg_data = imap.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
                if typ != "OK" or not msg_data:
                    continue
                part = msg_data[0]
                payload = part[1] if isinstance(part, tuple) and len(part) > 1 else b""
                if not isinstance(payload, (bytes, bytearray)):
                    continue
                raw = payload.decode("utf-8", errors="replace")
                subject = raw.split("Subject:", 1)[-1].strip()
                sonde = sonde_from_subject(subject)
                if sonde:
                    found.append(sonde)
    except (imaplib.IMAP4.error, OSError) as exc:
        logger.error("Mailbox search failed: %s", exc)
        raise
    return list(dict.fromkeys(found))


def sonde_from_subject(subject: str) -> str | None:
    """'[INFO] Idar-Oberstein (DE) D23029639 2026-11-17' -> 'D23029639'."""
    tokens = subject.split()
    for index, token in enumerate(tokens):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", token) and index > 0:
            candidate = tokens[index - 1]
            if SONDE_TOKEN_RE.fullmatch(candidate):
                return candidate
    match = SONDE_TOKEN_RE.search(subject)
    return match.group(0) if match else None


# --- Website: parse the Status Changes table ---------------------------------
def parse_status_rows(html: str) -> list[list[str]]:
    """Parse the 'Status Changes' table (Table6) of a sonde archive page."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id=STATUS_TABLE_ID)
    if table is None:
        logger.warning("status table #%s not found", STATUS_TABLE_ID)
        return []
    rows: list[list[str]] = []
    body = table.find("tbody")
    for tr in (body or table).find_all("tr"):
        cells = [norm(td.get_text(" ")) for td in tr.find_all(["td", "th"])]
        if not cells or cells == [""]:
            continue
        if cells[0].lower() == "launch site":
            continue  # header row
        rows.append(cells)
    return rows


def fetch_sonde_html(sonde: str, session: requests.Session, attempts: int = 3) -> str:
    url = SONDE_PAGE_URL.format(sonde=sonde)
    last_error: requests.exceptions.RequestException | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT_S)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as exc:
            last_error = exc
            logger.warning("%s: fetch attempt %d/%d failed: %s", sonde, attempt, attempts, exc)
            if attempt < attempts:
                time.sleep(2 * attempt)
    raise last_error  # type: ignore[misc]


def parse_nearest_city(html: str) -> str | None:
    """'Nearest City: Schönau (DE) [2.01 km]' -> 'Schönau (DE)'."""
    match = NEAREST_CITY_RE.search(html)
    if not match:
        return None
    return norm(match.group(1)) or None


def format_landing_time(raw: str) -> str:
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return raw
    return moment.strftime("%Y-%m-%d %H:%M UTC")


def fetch_landing_time(sonde: str, session: requests.Session) -> str | None:
    """Predicted landing time from radiosondy.info's prediction KML."""
    try:
        response = session.get(PREDICT_KML_URL.format(sonde=sonde), timeout=REQUEST_TIMEOUT_S)
    except requests.exceptions.RequestException as exc:
        logger.warning("%s: prediction KML fetch failed: %s", sonde, exc)
        return None
    if response.status_code != 200:
        return None
    match = LANDING_TIME_RE.search(response.text)
    return format_landing_time(match.group(1)) if match else None


def fetch_status_changes(sonde: str, session: requests.Session) -> list[list[str]]:
    return parse_status_rows(fetch_sonde_html(sonde, session))


# --- Notification ------------------------------------------------------------
def build_message(
    sonde: str,
    new_rows: list[list[str]],
    overview: list[tuple[str, str | None, str | None]] | None = None,
) -> EmailMessage:
    url = SONDE_PAGE_URL.format(sonde=sonde)
    statuses = [row[4] if len(row) > 4 else "?" for row in new_rows]
    subject = f"[Radiosondy] {sonde} Status Änderung: {', '.join(statuses)}"

    lines = [
        f"Radiosonde: {sonde}",
        f"Link: {url}",
        "",
        "Neue Einträge im Abschnitt 'Status Änderungen':",
        "",
    ]
    for row in new_rows:
        lines.append("  " + " | ".join(row))

    html_parts = [
        f'<p>Radiosonde: <a href="{url}">{sonde}</a><br>',
        f'Link: <a href="{url}">{url}</a></p>',
        "<p><b>Neue Einträge im Abschnitt 'Status Änderungen':</b></p>",
        '<table border="0" cellpadding="4" cellspacing="0">',
    ]
    for row in new_rows:
        cells = "".join(f"<td>{escape(cell)}</td>" for cell in row)
        html_parts.append(f"<tr>{cells}</tr>")
    html_parts.append("</table>")

    if overview:
        lines += [
            "",
            f"Alle überwachten Sonden ({len(overview)}):",
            "",
        ]
        html_parts += [
            f"<p><b>Alle überwachten Sonden ({len(overview)}):</b></p>",
            '<table border="0" cellpadding="4" cellspacing="0">',
            "<tr><th>Sonde</th><th>Nächste Stadt</th><th>Landung</th></tr>",
        ]
        for watched_sonde, city, landing in overview:
            watched_url = SONDE_PAGE_URL.format(sonde=watched_sonde)
            lines.append(
                f"  {watched_sonde} | {city or '-'} | Landung: {landing or '-'} | {watched_url}"
            )
            html_parts.append(
                "<tr>"
                f'<td><a href="{watched_url}">{watched_sonde}</a></td>'
                f"<td>{escape(city or '-')}</td>"
                f"<td>{escape(landing or '-')}</td>"
                "</tr>"
            )
        html_parts.append("</table>")

    lines += [
        "",
        "Details bitte auf der obigen Seite prüfen.",
        "",
        "-- via radiosondy-status (Hermes)",
    ]
    html_parts.append("<p>Details bitte auf der obigen Seite prüfen.</p>")
    html_parts.append("<p>-- via radiosondy-status (Hermes)</p>")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = RECIPIENT
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="gmail.com")
    msg.set_content("\n".join(lines), charset="utf-8")
    msg.add_alternative("".join(html_parts), subtype="html")
    return msg


def send_message(msg: EmailMessage, password: str) -> None:
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.login(GMAIL_ADDRESS, password)
        smtp.send_message(msg)


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
    parser.add_argument("--dry-run", action="store_true", help="do not send mail")
    parser.add_argument("--quiet", action="store_true", help="suppress change output")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    state = load_state()
    password = read_app_password()
    session = requests.Session()
    session.headers.update(HTTP_HEADERS)

    announced = find_announced_sondes(password)
    for sonde in announced:
        state["sondes"].setdefault(sonde, {"rows": []})

    notified = 0
    cities: dict[str, str | None] = {}
    for sonde in sorted(state["sondes"]):
        try:
            html = fetch_sonde_html(sonde, session)
        except requests.exceptions.RequestException as exc:
            logger.error("%s: fetch failed: %s", sonde, exc)
            continue

        cities[sonde] = parse_nearest_city(html)
        rows = parse_status_rows(html)

        known = [tuple(r) for r in state["sondes"][sonde].get("rows", [])]
        new_rows = [r for r in rows if tuple(r) not in known]

        if not new_rows:
            continue

        state["sondes"][sonde]["rows"] = rows

        overview = [
            (watched, cities.get(watched), fetch_landing_time(watched, session))
            for watched in sorted(state["sondes"])
        ]

        if args.dry_run:
            summary = ", ".join(
                f"{watched}={city or '-'}/{landing or '-'}" for watched, city, landing in overview
            )
            logger.info("%s: %d new row(s) (dry run); %s", sonde, len(new_rows), summary)
            continue

        try:
            send_message(build_message(sonde, new_rows, overview), password)
        except (smtplib.SMTPException, OSError) as exc:
            logger.error("%s: sending failed: %s", sonde, exc)
            telegram_alert(f"❌ radiosondy-status: {sonde} notification failed: {exc}")
            continue

        notified += 1
        if not args.quiet:
            print(f"{sonde}: {len(new_rows)} new status change(s) -> {RECIPIENT}")

    if not args.dry_run:
        save_state(state)
    logger.info("run finished, %d notification(s) sent", notified)
    return 0


if __name__ == "__main__":
    sys.exit(main())
