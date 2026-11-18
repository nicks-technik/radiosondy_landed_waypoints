"""Tests for the daily Status Changes watcher."""

import io
import json
import os
import sys
import time
import zipfile
from email.message import EmailMessage
from pathlib import Path
from xml.etree import ElementTree as ET

from check_status_changes import (
    OverviewRow,
    build_message,
    build_new_sonde_message,
    format_landing_time,
    format_receivers,
    main,
    merge_gpx,
    newest_gpx_per_sonde,
    parse_nearest_city,
    parse_status_rows,
    parse_tracker_distance,
    parse_tracker_receiver,
    sonde_from_subject,
    tracker_body_text,
    watched_sondes,
    waypoints_attachment,
)

TABLE_HTML = """
<html><body>
<table id="Table6" class="table table-condensed table-striped table-hover">
  <thead>
  <tr>
    <th>Launch Site</th><th>Type</th><th>AUX</th><th>Frequency</th>
    <th>Status</th><th>Finder</th><th>Landing Point</th>
    <th>Description</th><th>Changes made by</th>
  </tr>
  </thead>
  <tbody>
    <tr class="success">
      <td>Idar-Oberstein (DE)</td><td>DFM</td><td>NO</td><td>403.87 MHz</td>
      <td>FOUND</td><td>DB8NZ</td><td>49.81748, 10.35534</td>
      <td>Dachlandung - geborgen</td><td>db8nz - 2026-11-17 16:36:44z</td>
    </tr>
  </tbody>
</table>
</body></html>
"""


def test_sonde_from_subject_with_date():
    subject = "[INFO] Idar-Oberstein (DE) D23029639 2026-11-17"
    assert sonde_from_subject(subject) == "D23029639"


def test_sonde_from_subject_other_site_and_type():
    subject = "[INFO] Altenstadt (DE) W1120605 2026-11-16"
    assert sonde_from_subject(subject) == "W1120605"


def test_sonde_from_subject_fallback():
    assert sonde_from_subject("Radiosonde X3722094 meldet sich") == "X3722094"


def test_sonde_from_subject_without_sonde():
    assert sonde_from_subject("[INFO] Keine Sonde hier") is None


def test_parse_status_rows_reads_table_body():
    rows = parse_status_rows(TABLE_HTML)
    assert rows == [
        [
            "Idar-Oberstein (DE)",
            "DFM",
            "NO",
            "403.87 MHz",
            "FOUND",
            "DB8NZ",
            "49.81748, 10.35534",
            "Dachlandung - geborgen",
            "db8nz - 2026-11-17 16:36:44z",
        ]
    ]


def test_parse_status_rows_empty_body():
    html = """
    <html><body>
    <table id="Table6"><thead><tr><th>Launch Site</th></tr></thead>
    <tbody></tbody></table>
    </body></html>
    """
    assert parse_status_rows(html) == []


def test_parse_status_rows_missing_table():
    assert parse_status_rows("<html><body>nothing</body></html>") == []


def test_build_message_contains_link_and_sonde():
    msg = build_message("D23031993", parse_status_rows(TABLE_HTML))
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert msg["Subject"] == "[Radiosondy] D23031993 Status Änderung: FOUND"
    assert msg["To"] == "radiosonde@hornick.de"
    assert "https://radiosondy.info/sonde_archive.php?sondenumber=D23031993" in body
    assert "D23031993" in body
    assert "FOUND" in body


def test_build_message_lists_all_sondes():
    overview = [
        ("D23029639", "Schönau (DE)", "2026-11-17 13:15 UTC", "34.3 km", "nicklmhf"),
        ("D23029434", "Babenhausen (DE)", "2026-11-17 11:47 UTC", "24.3 km", "nickl"),
        ("D23032007", None, None, "-", "-"),
    ]
    msg = build_message("D23029639", parse_status_rows(TABLE_HTML), overview)
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert "Alle überwachten Sonden (3):" in body
    assert "D23029639 | Schönau (DE) | Landung: 2026-11-17 13:15 UTC | 34.3 km" in body
    assert "D23029434 | Babenhausen (DE) | Landung: 2026-11-17 11:47 UTC | 24.3 km" in body
    assert "D23032007 | - | Landung: - | -" in body
    for watched, _, _, _, _ in overview:
        assert f"https://radiosondy.info/sonde_archive.php?sondenumber={watched}" in body


def test_build_message_links_open_all_page():
    overview = [("D23029639", "Schönau (DE)", "2026-11-17 13:15 UTC", "34.3 km", "nicklmhf")]
    msg = build_message("D23029639", parse_status_rows(TABLE_HTML), overview)
    html = msg.get_body(preferencelist=("html",)).get_content()
    assert '<a href="https://radiosondy.info/sonde_archive.php?sondenumber=D23029639">' in html


def test_build_message_html_links_every_sonde():
    overview = [
        ("D23029639", "Schönau (DE)", "2026-11-17 13:15 UTC", "34.3 km", "nicklmhf"),
        ("D23032007", None, None, "-", "-"),
    ]
    msg = build_message("D23029639", parse_status_rows(TABLE_HTML), overview)
    html = msg.get_body(preferencelist=("html",)).get_content()
    assert 'href="https://radiosondy.info/sonde_archive.php?sondenumber=D23029639"' in html
    assert 'href="https://radiosondy.info/sonde_archive.php?sondenumber=D23032007"' in html
    assert "Schönau (DE)" in html
    assert "34.3 km" in html


def test_build_message_html_escapes_city():
    overview = [("D23029639", "<b>Schönau</b> (DE)", None, "-", "nicklmhf")]
    msg = build_message("D23029639", parse_status_rows(TABLE_HTML), overview)
    html = msg.get_body(preferencelist=("html",)).get_content()
    assert "&lt;b&gt;Schönau&lt;/b&gt; (DE)" in html


def test_overview_is_sorted_youngest_first():
    overview = [
        ("D23029434", "Babenhausen (DE)", "2026-11-17 11:47 UTC", "24.3 km", "nickl"),
        ("D23032096", "Kleinrinderfeld (DE)", "2026-11-17 18:27 UTC", "31.0 km", "nicklmhf"),
        ("D23029639", "Schönau (DE)", "2026-11-17 13:15 UTC", "34.3 km", "nicklmhf"),
        ("V3220905", "Aura im Sinngrund (DE)", None, "-", "-"),
    ]
    msg = build_message("D23029639", parse_status_rows(TABLE_HTML), overview)
    body = msg.get_body(preferencelist=("plain",)).get_content()
    order = [body.index(f"  {sonde} |") for sonde in ("D23032096", "D23029639", "D23029434", "V3220905")]
    assert order == sorted(order), body


def test_build_new_sonde_message_announces_the_sonde():
    msg = build_new_sonde_message("D23032007")
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert msg["Subject"] == "[Radiosondy] Neue Sonde D23032007"
    assert msg["To"] == "radiosonde@hornick.de"
    assert "Neue Sonde: D23032007" in body
    assert "https://radiosondy.info/sonde_archive.php?sondenumber=D23032007" in body
    assert "Status Änderungen" not in body


def test_build_new_sonde_message_includes_overview_table():
    overview: list[tuple[str, str | None, str | None, str, str]] = [
        ("D23029639", "Schönau (DE)", "2026-11-17 13:15 UTC", "34.3 km", "nicklmhf"),
        ("D23032007", "Randersacker (DE)", "2026-11-17 16:58 UTC", "33.9 km", "nickl"),
    ]
    msg = build_new_sonde_message("D23032007", overview)
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert "Alle überwachten Sonden (2):" in body
    assert "D23029639 | Schönau (DE) | Landung: 2026-11-17 13:15 UTC | 34.3 km" in body
    html = msg.get_body(preferencelist=("html",)).get_content()
    assert 'href="https://radiosondy.info/sonde_archive.php?sondenumber=D23032007"' in html
    assert "Schönau (DE)" in html
    assert "Entfernung vom QTH" in html
    assert "Empfänger" in html


def test_parse_nearest_city_english():
    html = '<h4 class="info-title">Nearest City: Rechtenbach (DE) [5.01 km]</h4>'
    assert parse_nearest_city(html) == "Rechtenbach (DE)"


def test_parse_nearest_city_german():
    html = "<h4>Nächste Stadt: Waldaschaff (DE) [1.20 km]</h4>"
    assert parse_nearest_city(html) == "Waldaschaff (DE)"


def test_parse_nearest_city_ignores_meta_description():
    html = (
        '<meta name="description" content="Start Date: 2026-11-17 | Status: Unknown | '
        'Nearest City: Schönau (DE)"/>\n'
        "<h4>Nearest City: Schönau (DE) [2.01 km]</h4>"
    )
    assert parse_nearest_city(html) == "Schönau (DE)"


def test_parse_nearest_city_missing():
    assert parse_nearest_city("<html><body>nothing</body></html>") is None


def test_format_landing_time():
    assert format_landing_time("2026-11-17T13:15:13.375Z") == "2026-11-17 13:15 UTC"


def test_format_landing_time_invalid():
    assert format_landing_time("not-a-date") == "not-a-date"


def test_parse_tracker_distance():
    text = "Liebe(r) Nick Horn (nicklmhf) Entfernung von Deinem QTH 4.05 km · 51° NE Nächste Stadt"
    assert parse_tracker_distance(text) == "4.05 km · 51° NE"


def test_parse_tracker_distance_without_bearing():
    assert parse_tracker_distance("Entfernung von Deinem QTH 12,5 km") == "12.5 km"


def test_parse_tracker_distance_missing():
    assert parse_tracker_distance("Nächste Stadt Karbach (DE)") is None


def test_tracker_body_text_strips_html():
    message = EmailMessage()
    message.set_content("<p>Entfernung von Deinem QTH 4.05 km · 51° NE</p>", subtype="html")
    assert "4.05 km" in tracker_body_text(message)


def test_first_pickup_rows_are_saved_as_baseline(tmp_path, monkeypatch):
    """A sonde first seen with rows already present must not report them later."""
    state_file = tmp_path / "state.json"
    monkeypatch.setattr("check_status_changes.STATE_FILE", state_file)
    monkeypatch.setattr("check_status_changes.read_app_password", lambda: "pw")
    monkeypatch.setattr(
        "check_status_changes.watched_sondes",
        lambda pw, state: state["sondes"].update(
            {"D23034927": {"rows": []}}
        ) or {"D23034927": {"distance": None, "receivers": []}},
    )
    monkeypatch.setattr("check_status_changes.fetch_sonde_html", lambda sonde, session: "<html></html>")
    monkeypatch.setattr("check_status_changes.fetch_landing_time", lambda sonde, session: None)
    monkeypatch.setattr(
        "check_status_changes.parse_status_rows", lambda html: [["Idar-Oberstein (DE)", "DFM"]]
    )
    monkeypatch.setattr("check_status_changes.send_message", lambda msg, pw: None)
    monkeypatch.setattr(sys, "argv", ["check_status_changes.py"])

    assert main() == 0
    state = json.loads(state_file.read_text())
    assert state["sondes"]["D23034927"]["rows"] == [["Idar-Oberstein (DE)", "DFM"]]

    # second run: the stored rows are the baseline, so nothing is reported
    assert main() == 0


def test_parse_tracker_receiver():
    text = "Liebe(r) Nick Horn (nicklmhf) Es befindet sich eine Sonde in der Nähe Deines QTHs!"
    assert parse_tracker_receiver(text) == "nicklmhf"


def test_parse_tracker_receiver_other_account():
    text = "Liebe(r) Nick Hornick (nickl) Es befindet sich eine Sonde"
    assert parse_tracker_receiver(text) == "nickl"


def test_parse_tracker_receiver_missing():
    assert parse_tracker_receiver("Nächste Stadt Karbach (DE)") is None


def test_format_receivers():
    assert format_receivers([]) == "-"
    assert format_receivers(["nickl"]) == "nickl"
    assert format_receivers(["nickl", "nicklmhf"]) == "nickl, nicklmhf"


def test_watched_sondes_drops_mail_that_left_the_inbox(monkeypatch):
    state = {"sondes": {"D23029639": {"rows": []}, "D23034927": {"rows": []}}}
    record = {
        "sonde": "D23034927",
        "message_id": "m1",
        "distance": "4.05 km",
        "receiver": "nicklmhf",
    }
    monkeypatch.setattr(
        "check_status_changes.find_announced_mails",
        lambda password: [record],
    )
    records = watched_sondes("pw", state)
    assert list(records) == ["D23034927"]
    assert set(state["sondes"]) == {"D23034927"}


def test_watched_sondes_adds_new_mail(monkeypatch):
    state = {"sondes": {}}
    monkeypatch.setattr(
        "check_status_changes.find_announced_mails",
        lambda password: [
            {"sonde": "D23034927", "message_id": "m1", "distance": None, "receiver": None}
        ],
    )
    assert watched_sondes("pw", state) == {
        "D23034927": {"distance": None, "receivers": []}
    }
    assert state["sondes"]["D23034927"] == {"rows": []}


def test_watched_sondes_merges_two_receivers_for_one_sonde(monkeypatch):
    state = {"sondes": {}}
    monkeypatch.setattr(
        "check_status_changes.find_announced_mails",
        lambda password: [
            {"sonde": "D23034927", "message_id": "m1", "distance": "4.05 km", "receiver": "nicklmhf"},
            {"sonde": "D23034927", "message_id": "m2", "distance": "4.05 km", "receiver": "nickl"},
        ],
    )
    assert watched_sondes("pw", state) == {
        "D23034927": {"distance": "4.05 km", "receivers": ["nicklmhf", "nickl"]}
    }
    assert state["sondes"] == {"D23034927": {"rows": []}}


GPX_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<gpx version="1.1" creator="gpx.py">\n'
    '  <wpt lat="{lat}" lon="{lon}">\n'
    "    <name>{sonde} Last Seen</name>\n"
    "  </wpt>\n"
    '  <wpt lat="{lat}" lon="{lon}">\n'
    "    <name>{sonde} My Predicted Landing</name>\n"
    "  </wpt>\n"
    "</gpx>\n"
)


def write_gpx(
    directory: Path, sonde: str, lat: str, lon: str, age_s: int = 0, index: int = 0
) -> Path:
    path = directory / f"{sonde}_261118_12{index:02d}_Ort_DE_gpx_waypoint.gpx"
    path.write_text(GPX_TEMPLATE.format(lat=lat, lon=lon, sonde=sonde), encoding="utf-8")
    stamp = time.time() - age_s
    os.utime(path, (stamp, stamp))
    return path


def test_newest_gpx_per_sonde(tmp_path, monkeypatch):
    monkeypatch.setattr("check_status_changes.GPX_DIR", tmp_path)
    write_gpx(tmp_path, "D23034927", "50.0", "9.0", age_s=90, index=0)
    new = write_gpx(tmp_path, "D23034927", "50.1", "9.1", age_s=10, index=1)
    write_gpx(tmp_path, "D23034927", "50.2", "9.2", age_s=50, index=2)
    other = write_gpx(tmp_path, "D23029639", "51.0", "10.0", index=0)

    # the newest file per sonde, in the order of the requested sondes
    assert newest_gpx_per_sonde(["D23029639", "D23034927", "D99999999"]) == [other, new]


def test_merge_gpx_combines_all_waypoints(tmp_path):
    first = write_gpx(tmp_path, "D23034927", "50.0", "9.0")
    second = write_gpx(tmp_path, "D23029639", "51.0", "10.0")

    merged = merge_gpx([first, second])

    assert merged is not None
    root = ET.fromstring(merged)
    names = [wpt.findtext("name") for wpt in root.findall("wpt")]
    assert names == [
        "D23034927 Last Seen",
        "D23034927 My Predicted Landing",
        "D23029639 Last Seen",
        "D23029639 My Predicted Landing",
    ]


def test_merge_gpx_without_waypoints(tmp_path):
    empty = tmp_path / "empty.gpx"
    empty.write_text('<?xml version="1.0"?><gpx version="1.1"></gpx>', encoding="utf-8")
    assert merge_gpx([empty]) is None
    assert merge_gpx([]) is None


def test_waypoints_attachment_is_a_zip_with_one_gpx(tmp_path, monkeypatch):
    monkeypatch.setattr("check_status_changes.GPX_DIR", tmp_path)
    write_gpx(tmp_path, "D23034927", "50.0", "9.0")
    overview: list[OverviewRow] = [
        ("D23034927", "Karbach (DE)", "2026-11-18 12:00 UTC", "4.05 km", "nicklmhf")
    ]

    attachment = waypoints_attachment(overview)

    assert attachment is not None
    name, data = attachment
    assert name.startswith("radiosondy_waypoints_") and name.endswith(".zip")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert len(zf.namelist()) == 1
        assert zf.namelist()[0].endswith(".gpx")
        root = ET.fromstring(zf.read(zf.namelist()[0]).decode("utf-8"))
    assert len(root.findall("wpt")) == 2


def test_waypoints_attachment_without_gpx_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr("check_status_changes.GPX_DIR", tmp_path)
    assert waypoints_attachment([("D23034927", None, None, "-", "-")]) is None
    assert waypoints_attachment(None) is None


def test_build_message_carries_the_zip(tmp_path, monkeypatch):
    monkeypatch.setattr("check_status_changes.GPX_DIR", tmp_path)
    write_gpx(tmp_path, "D23034927", "50.0", "9.0")
    overview: list[OverviewRow] = [
        ("D23034927", "Karbach (DE)", "2026-11-18 12:00 UTC", "4.05 km", "nicklmhf")
    ]

    msg = build_message("D23034927", [["a", "b", "c", "d", "FOUND"]], overview)

    attachments = [part for part in msg.walk() if part.get_filename()]
    assert len(attachments) == 1
    assert attachments[0].get_content_type() == "application/zip"
