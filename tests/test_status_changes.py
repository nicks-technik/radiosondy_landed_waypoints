"""Tests for the daily Status Changes watcher."""

from check_status_changes import (
    build_message,
    format_landing_time,
    parse_nearest_city,
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
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert msg["Subject"] == "[Radiosondy] D23031993 Status Änderung: FOUND"
    assert msg["To"] == "radiosonde@hornick.de"
    assert "https://radiosondy.info/sonde_archive.php?sondenumber=D23031993" in body
    assert "D23031993" in body
    assert "FOUND" in body


def test_build_message_lists_all_sondes():
    overview = [
        ("D23029639", "Schönau (DE)", "2026-11-17 13:15 UTC"),
        ("D23029434", "Babenhausen (DE)", "2026-11-17 11:47 UTC"),
        ("D23032007", None, None),
    ]
    msg = build_message("D23029639", parse_status_rows(TABLE_HTML), overview)
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert "Alle überwachten Sonden (3):" in body
    assert "D23029639 | Schönau (DE) | Landung: 2026-11-17 13:15 UTC" in body
    assert "D23029434 | Babenhausen (DE) | Landung: 2026-11-17 11:47 UTC" in body
    assert "D23032007 | - | Landung: -" in body
    for watched, _, _ in overview:
        assert f"https://radiosondy.info/sonde_archive.php?sondenumber={watched}" in body


def test_build_message_links_open_all_page():
    overview = [("D23029639", "Schönau (DE)", "2026-11-17 13:15 UTC")]
    msg = build_message("D23029639", parse_status_rows(TABLE_HTML), overview)
    html = msg.get_body(preferencelist=("html",)).get_content()
    assert '<a href="https://radiosondy.info/sonde_archive.php?sondenumber=D23029639">' in html


def test_build_message_html_links_every_sonde():
    overview = [
        ("D23029639", "Schönau (DE)", "2026-11-17 13:15 UTC"),
        ("D23032007", None, None),
    ]
    msg = build_message("D23029639", parse_status_rows(TABLE_HTML), overview)
    html = msg.get_body(preferencelist=("html",)).get_content()
    assert 'href="https://radiosondy.info/sonde_archive.php?sondenumber=D23029639"' in html
    assert 'href="https://radiosondy.info/sonde_archive.php?sondenumber=D23032007"' in html
    assert "Schönau (DE)" in html


def test_build_message_html_escapes_city():
    overview = [("D23029639", "<b>Schönau</b> (DE)", None)]
    msg = build_message("D23029639", parse_status_rows(TABLE_HTML), overview)
    html = msg.get_body(preferencelist=("html",)).get_content()
    assert "&lt;b&gt;Schönau&lt;/b&gt; (DE)" in html


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
