"""Tests for the hourly tracker-mail handler."""

import json
from email.message import EmailMessage

import check_tracker_mail as c

EMAIL_HTML = """
<html><body>
<a href="https://www.openstreetmap.org/directions?route=49.8,9.6;50.0,9.7">Route</a>
<a href="https://radiosondy.info/sonde.php?sondenumber=D23029639"
   style="display:inline-block">Details</a>
</body></html>
"""


def make_message(html: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = "[INFO] Idar-Oberstein (DE) D23029639 2026-11-17"
    msg["Message-ID"] = "<123.456-sendEmail@api-radiosondy>"
    msg.set_content("plain", subtype="plain")
    msg.add_alternative(html, subtype="html")
    return msg


def test_details_link_from_button():
    assert c.details_link(make_message(EMAIL_HTML)) == (
        "https://radiosondy.info/sonde.php?sondenumber=D23029639"
    )


def test_details_link_fallback_to_any_sonde_link():
    html = '<html><body><a href="https://radiosondy.info/sonde_archive.php?sondenumber=X3722094">x</a></body></html>'
    assert c.details_link(make_message(html)) == (
        "https://radiosondy.info/sonde_archive.php?sondenumber=X3722094"
    )


def test_details_link_missing():
    assert c.details_link(make_message("<html><body>nothing</body></html>")) is None


def test_sonde_number_from_url():
    assert c.sonde_number("https://radiosondy.info/sonde.php?sondenumber=D23029639") == "D23029639"
    assert c.sonde_number("https://radiosondy.info/sonde_archive.php?sondenumber=X3722094") == "X3722094"
    assert c.sonde_number("https://example.com/nope") is None


def test_state_roundtrip(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(c, "STATE_FILE", state_file)
    assert c.load_state() == {"processed": []}
    c.save_state({"processed": ["a", "b"]})
    assert c.load_state() == {"processed": ["a", "b"]}
    assert json.loads(state_file.read_text())["processed"] == ["a", "b"]
    assert state_file.parent.exists()
