import radiosondy_web as web


def test_requested_sondes_parses_query():
    assert web.requested_sondes("sondes=D23029639,D23029434") == ["D23029639", "D23029434"]


def test_requested_sondes_strips_and_deduplicates():
    assert web.requested_sondes("sondes=D1,%20D2%20,D1") == ["D1", "D2"]


def test_requested_sondes_empty_without_parameter():
    assert web.requested_sondes("") == []
    assert web.requested_sondes("other=1") == []


def test_render_contains_urls_and_opener_logic():
    body = web.render(["D23029639", "D23029434"]).decode()
    assert "https://radiosondy.info/sonde_archive.php?sondenumber=D23029639" in body
    assert "https://radiosondy.info/sonde_archive.php?sondenumber=D23029434" in body
    assert "window.open" in body
    assert "window.location.replace(urls[0])" in body


def test_render_without_sondes_stays_quiet():
    body = web.render([]).decode()
    assert "Keine Sonde uebergeben." in body
