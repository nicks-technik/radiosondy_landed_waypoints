"""Tests for the daily Status Changes watcher."""

from check_status_changes import (
    build_message,
    parse_status_rows,
    sonde_from_subject,
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
    body = msg.get_content()
    assert msg["Subject"] == "[Radiosondy] D23031993 Status Änderung: FOUND"
    assert msg["To"] == "radiosonde@hornick.de"
    assert "https://radiosondy.info/sonde_archive.php?sondenumber=D23031993" in body
    assert "D23031993" in body
    assert "FOUND" in body
