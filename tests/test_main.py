import argparse
import asyncio
import os
import re
import requests
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from main import Coordinates, SondeData, SondeProcessor, parse_arguments

# Mock data for testing
MOCK_URL = "http://example.com/track.php?sondenumber=S123456"
MOCK_HTML_CONTENT = """
<html>
<body>
    <table id="Table7">
        <tbody>
            <tr>
                <td>1</td>
                <td>2</td>
                <td>2023-10-27 10:00:00</td>
                <td>50.00</td>
                <td>10.00</td>
                <td>90.0</td>
                <td>100.0</td>
                <td>10000.0</td>
                <td>-5.0</td>
            </tr>
        </tbody>
    </table>
    <div>Ground Altitude: 100 m</div>
</body>
</html>
"""
MOCK_HTML_CONTENT_NO_GROUND_ALT = """
<html>
<body>
    <table id="Table7">
        <tbody>
            <tr>
                <td>1</td>
                <td>2</td>
                <td>2023-10-27 10:00:00</td>
                <td>50.00</td>
                <td>10.00</td>
                <td>90.0</td>
                <td>100.0</td>
                <td>10000.0</td>
                <td>-5.0</td>
            </tr>
        </tbody>
    </table>
</body>
</html>
"""
MOCK_HTML_CONTENT_MISSING_DATA = """
<html>
<body>
    <table id="Table7">
        <tbody>
            <tr>
                <td>1</td>
                <td>2</td>
                <td>2023-10-27 10:00:00</td>
                <td>50.00</td>
                <td>10.00</td>
            </tr>
        </tbody>
    </table>
</body>
</html>
"""


@pytest.fixture
def mock_env_vars():
    with patch.dict(os.environ, {"ENV_TELEGRAM_BOT_TOKEN": "test_token", "ENV_TELEGRAM_CHAT_ID": "12345"}):
        yield


# Tests for parse_arguments
def test_parse_arguments_valid_url():
    with patch("argparse.ArgumentParser.parse_args", return_value=argparse.Namespace(url=MOCK_URL, coords=None)):
        args = parse_arguments()
        assert args.url == MOCK_URL
        assert args.coords is None


def test_parse_arguments_valid_url_and_coords():
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(url=MOCK_URL, coords="51.0,11.0"),
    ):
        args = parse_arguments()
        assert args.url == MOCK_URL
        assert args.coords == "51.0,11.0"


def test_parse_arguments_valid_url_and_coords_with_description():
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(url=MOCK_URL, coords="51.0,11.0 at 2023-10-27T10:00:00.00Z"),
    ):
        args = parse_arguments()
        assert args.url == MOCK_URL
        assert args.coords == "51.0,11.0 at 2023-10-27T10:00:00.00Z"


# Tests for SondeProcessor.__init__
def test_sonde_processor_init_valid_url():
    processor = SondeProcessor(MOCK_URL)
    assert processor.url == MOCK_URL
    assert processor.sonde_number == "S123456"
    assert processor.radiosondy_coords is None


def test_sonde_processor_init_valid_url_and_coords():
    processor = SondeProcessor(MOCK_URL, coords="51.0,11.0")
    assert processor.url == MOCK_URL
    assert processor.sonde_number == "S123456"
    assert processor.radiosondy_coords == Coordinates(lat=51.0, lon=11.0)
    assert processor.radiosondy_coords_description is None


def test_sonde_processor_init_valid_url_and_coords_with_description():
    processor = SondeProcessor(MOCK_URL, coords="51.0,11.0 at 2023-10-27T10:00:00.00Z")
    assert processor.url == MOCK_URL
    assert processor.sonde_number == "S123456"
    assert processor.radiosondy_coords == Coordinates(lat=51.0, lon=11.0)
    assert processor.radiosondy_coords_description == "2023-10-27T10:00:00.00Z"


def test_sonde_processor_init_invalid_coords_format():
    processor = SondeProcessor(MOCK_URL, coords="invalid_coords")
    assert processor.radiosondy_coords is None


# Tests for fetch_website_content
@patch("requests.get")
def test_fetch_website_content_success(mock_get):
    mock_response = MagicMock()
    mock_response.text = MOCK_HTML_CONTENT
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    processor = SondeProcessor(MOCK_URL)
    content = processor.fetch_website_content()
    assert content == MOCK_HTML_CONTENT
    mock_get.assert_called_once_with(MOCK_URL)


@patch("requests.get")
def test_fetch_website_content_http_error(mock_get):
    mock_get.side_effect = requests.exceptions.RequestException("HTTP Error")

    processor = SondeProcessor(MOCK_URL)
    content = processor.fetch_website_content()
    assert content is None
    mock_get.assert_called_once_with(MOCK_URL)


@patch("requests.get")
def test_fetch_website_content_connection_error(mock_get):
    mock_get.side_effect = requests.exceptions.ConnectionError("Connection Error")

    processor = SondeProcessor(MOCK_URL)
    content = processor.fetch_website_content()
    assert content is None
    mock_get.assert_called_once_with(MOCK_URL)


# Tests for parse_last_seen_data
def test_parse_last_seen_data_success():
    processor = SondeProcessor(MOCK_URL)
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(MOCK_HTML_CONTENT, "html.parser")
    sonde_data = processor.parse_last_seen_data(soup)

    assert sonde_data is not None
    assert sonde_data.last_seen_coords == Coordinates(lat=50.0, lon=10.0)
    assert sonde_data.last_seen_time == datetime(2023, 10, 27, 10, 0, 0)
    assert sonde_data.course == 90.0
    assert sonde_data.altitude == 10000.0
    assert sonde_data.speed_mps == pytest.approx(100.0 * 1000 / 3600)
    assert sonde_data.climb_rate == -5.0


def test_parse_last_seen_data_missing_data():
    processor = SondeProcessor(MOCK_URL)
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(MOCK_HTML_CONTENT_MISSING_DATA, "html.parser")
    sonde_data = processor.parse_last_seen_data(soup)
    assert sonde_data is None


def test_parse_last_seen_data_invalid_html():
    processor = SondeProcessor(MOCK_URL)
    from bs4 import BeautifulSoup

    soup = BeautifulSoup("<div>Invalid HTML</div>", "html.parser")
    sonde_data = processor.parse_last_seen_data(soup)
    assert sonde_data is None


# Tests for calculate_landing_point
def test_calculate_landing_point_basic():
    processor = SondeProcessor(MOCK_URL)
    coords = Coordinates(lat=50.0, lon=10.0)
    altitude = 10000.0
    speed = 27.7778  # 100 km/h in m/s
    course = 90.0
    descent_rate = 5.0
    ground_height = 100.0

    landing_coords, time_to_ground = processor.calculate_landing_point(
        coords, altitude, speed, course, descent_rate, ground_height
    )

    assert time_to_ground == pytest.approx((10000.0 - 100.0) / 5.0)
    assert isinstance(landing_coords, Coordinates)
    assert landing_coords.lat != coords.lat  # Should have moved
    assert landing_coords.lon != coords.lon  # Should have moved


def test_calculate_landing_point_height_to_descend_negative():
    processor = SondeProcessor(MOCK_URL)
    coords = Coordinates(lat=50.0, lon=10.0)
    altitude = 50.0
    speed = 27.7778
    course = 90.0
    descent_rate = 5.0
    ground_height = 100.0

    landing_coords, time_to_ground = processor.calculate_landing_point(
        coords, altitude, speed, course, descent_rate, ground_height
    )

    assert time_to_ground == 0.0
    assert landing_coords == coords  # Should not have moved


def test_calculate_landing_point_zero_descent_rate():
    processor = SondeProcessor(MOCK_URL)
    coords = Coordinates(lat=50.0, lon=10.0)
    altitude = 10000.0
    speed = 27.7778
    course = 90.0
    descent_rate = 0.0
    ground_height = 100.0

    # Expect division by zero, which should be handled by the caller or result in specific behavior
    with pytest.raises(ZeroDivisionError):
        processor.calculate_landing_point(coords, altitude, speed, course, descent_rate, ground_height)


# Tests for get_coordinates
def test_get_coordinates_success():
    processor = SondeProcessor(MOCK_URL)
    sonde_data, landing_point, ground_height, time_to_ground = processor.get_coordinates(MOCK_HTML_CONTENT)

    assert sonde_data is not None
    assert landing_point is not None
    assert ground_height == 100.0
    assert time_to_ground > 0


def test_get_coordinates_no_ground_altitude():
    processor = SondeProcessor(MOCK_URL)
    sonde_data, landing_point, ground_height, time_to_ground = processor.get_coordinates(MOCK_HTML_CONTENT_NO_GROUND_ALT)

    assert sonde_data is not None
    assert landing_point is not None
    assert ground_height == 0.0  # Default value
    assert time_to_ground > 0


def test_get_coordinates_parse_last_seen_data_fails():
    processor = SondeProcessor(MOCK_URL)
    sonde_data, landing_point, ground_height, time_to_ground = processor.get_coordinates("<div>Invalid HTML</div>")

    assert sonde_data is None
    assert landing_point is None
    assert ground_height == 0.0
    assert time_to_ground == 0.0


# Tests for create_gpx_file
@patch("builtins.open", new_callable=mock_open)
@patch("gpxpy.gpx.GPX.to_xml", return_value="<gpx>test</gpx>")
def test_create_gpx_file_success(mock_to_xml, mock_file_open):
    processor = SondeProcessor(MOCK_URL)
    sonde_data = SondeData(
        last_seen_coords=Coordinates(lat=50.0, lon=10.0),
        last_seen_time=datetime(2023, 10, 27, 10, 0, 0),
        course=90.0,
        altitude=10000.0,
        speed_mps=27.7778,
        climb_rate=-5.0,
    )
    landing_point = Coordinates(lat=50.1, lon=10.1)
    ground_height = 100.0
    time_to_ground = 1000.0

    filename = processor.create_gpx_file(sonde_data, landing_point, ground_height, time_to_ground)

    assert filename == "gpx/S123456_231027_1000_gpx_waypoint.gpx"
    mock_file_open.assert_called_once_with(filename, "w")
    mock_file_open().write.assert_called_once_with("<gpx>test</gpx>")


@patch("builtins.open", new_callable=mock_open)
@patch("gpxpy.gpx.GPX.to_xml", return_value="<gpx>test</gpx>")
def test_create_gpx_file_with_radiosondy_coords(mock_to_xml, mock_file_open):
    processor = SondeProcessor(MOCK_URL, coords="51.0,11.0")
    sonde_data = SondeData(
        last_seen_coords=Coordinates(lat=50.0, lon=10.0),
        last_seen_time=datetime(2023, 10, 27, 10, 0, 0),
        course=90.0,
        altitude=10000.0,
        speed_mps=27.7778,
        climb_rate=-5.0,
    )
    landing_point = Coordinates(lat=50.1, lon=10.1)
    ground_height = 100.0
    time_to_ground = 1000.0

    filename = processor.create_gpx_file(sonde_data, landing_point, ground_height, time_to_ground)

    assert filename == "gpx/S123456_231027_1000_gpx_waypoint.gpx"
    mock_file_open.assert_called_once_with(filename, "w")
    mock_file_open().write.assert_called_once_with("<gpx>test</gpx>")
    # Further assertions could check the content of the GPX to ensure radiosondy_coords are included


@patch("builtins.open", side_effect=IOError("Disk Full"))
def test_create_gpx_file_io_error(mock_file_open):
    processor = SondeProcessor(MOCK_URL)
    sonde_data = SondeData(
        last_seen_coords=Coordinates(lat=50.0, lon=10.0),
        last_seen_time=datetime(2023, 10, 27, 10, 0, 0),
        course=90.0,
        altitude=10000.0,
        speed_mps=27.7778,
        climb_rate=-5.0,
    )
    landing_point = Coordinates(lat=50.1, lon=10.1)
    ground_height = 100.0
    time_to_ground = 1000.0

    filename = processor.create_gpx_file(sonde_data, landing_point, ground_height, time_to_ground)

    assert filename is None


# Tests for send_to_telegram
@pytest.mark.asyncio
@patch("telegram.Bot")
async def test_send_to_telegram_success(mock_bot_class, mock_env_vars):
    mock_bot_instance = AsyncMock()
    mock_bot_class.return_value = mock_bot_instance

    processor = SondeProcessor(MOCK_URL)
    test_file_path = "gpx/test_file.gpx"

    with patch("builtins.open", mock_open(read_data="gpx content")) as mock_file_open:
        await processor.send_to_telegram(test_file_path)
        mock_bot_class.assert_called_once_with(token="test_token")
        mock_bot_instance.send_document.assert_called_once()
        mock_file_open.assert_called_once_with(test_file_path, "rb")


@pytest.mark.asyncio
@patch("telegram.Bot")
async def test_send_to_telegram_missing_env_vars(mock_bot_class):
    # Clear env vars for this test
    with patch.dict(os.environ, {}, clear=True):
        processor = SondeProcessor(MOCK_URL)
        test_file_path = "gpx/test_file.gpx"
        await processor.send_to_telegram(test_file_path)
        mock_bot_class.assert_not_called()


@pytest.mark.asyncio
@patch("telegram.Bot")
async def test_send_to_telegram_send_document_fails(mock_bot_class, mock_env_vars):
    mock_bot_instance = AsyncMock()
    mock_bot_instance.send_document.side_effect = Exception("Telegram Error")
    mock_bot_class.return_value = mock_bot_instance

    processor = SondeProcessor(MOCK_URL)
    test_file_path = "gpx/test_file.gpx"

    with patch("builtins.open", mock_open(read_data="gpx content")):
        await processor.send_to_telegram(test_file_path)
        mock_bot_class.assert_called_once_with(token="test_token")
        mock_bot_instance.send_document.assert_called_once()


# Test for main function (integration-like test)
@pytest.mark.asyncio
@patch("main.parse_arguments")
@patch.object(SondeProcessor, "fetch_website_content", return_value=MOCK_HTML_CONTENT)
@patch.object(SondeProcessor, "get_coordinates")
@patch.object(SondeProcessor, "create_gpx_file", return_value="gpx/test_file.gpx")
@patch.object(SondeProcessor, "send_to_telegram", new_callable=AsyncMock)
async def test_main_function_success(
    mock_send_to_telegram,
    mock_create_gpx_file,
    mock_get_coordinates,
    mock_fetch_website_content,
    mock_parse_arguments,
    mock_env_vars,
):
    mock_parse_arguments.return_value = argparse.Namespace(url=MOCK_URL, coords=None)
    mock_get_coordinates.return_value = (
        SondeData(
            last_seen_coords=Coordinates(lat=50.0, lon=10.0),
            last_seen_time=datetime(2023, 10, 27, 10, 0, 0),
            course=90.0,
            altitude=10000.0,
            speed_mps=27.7778,
            climb_rate=-5.0,
        ),
        Coordinates(lat=50.1, lon=10.1),
        100.0,
        1000.0,
    )

    from main import main

    await main()

    mock_parse_arguments.assert_called_once()
    mock_fetch_website_content.assert_called_once()
    mock_get_coordinates.assert_called_once()
    mock_create_gpx_file.assert_called_once()
    mock_send_to_telegram.assert_called_once_with("gpx/test_file.gpx")


@pytest.mark.asyncio
@patch("main.parse_arguments")
@patch.object(SondeProcessor, "fetch_website_content", return_value=None)
@patch.object(SondeProcessor, "get_coordinates")
@patch.object(SondeProcessor, "create_gpx_file")
@patch.object(SondeProcessor, "send_to_telegram", new_callable=AsyncMock)
async def test_main_function_fetch_fails(
    mock_send_to_telegram,
    mock_create_gpx_file,
    mock_get_coordinates,
    mock_fetch_website_content,
    mock_parse_arguments,
    mock_env_vars,
):
    mock_parse_arguments.return_value = argparse.Namespace(url=MOCK_URL, coords=None)

    from main import main

    await main()

    mock_parse_arguments.assert_called_once()
    mock_fetch_website_content.assert_called_once()
    mock_get_coordinates.assert_not_called()
    mock_create_gpx_file.assert_not_called()
    mock_send_to_telegram.assert_not_called()


@pytest.mark.asyncio
@patch("main.parse_arguments")
@patch.object(SondeProcessor, "fetch_website_content", return_value=MOCK_HTML_CONTENT)
@patch.object(SondeProcessor, "get_coordinates", return_value=(None, None, 0.0, 0.0))
@patch.object(SondeProcessor, "create_gpx_file")
@patch.object(SondeProcessor, "send_to_telegram", new_callable=AsyncMock)
async def test_main_function_get_coordinates_fails(
    mock_send_to_telegram,
    mock_create_gpx_file,
    mock_get_coordinates,
    mock_fetch_website_content,
    mock_parse_arguments,
    mock_env_vars,
):
    mock_parse_arguments.return_value = argparse.Namespace(url=MOCK_URL, coords=None)

    from main import main

    await main()

    mock_parse_arguments.assert_called_once()
    mock_fetch_website_content.assert_called_once()
    mock_get_coordinates.assert_called_once()
    mock_create_gpx_file.assert_not_called()
    mock_send_to_telegram.assert_not_called()


@pytest.mark.asyncio
@patch("main.parse_arguments")
@patch.object(SondeProcessor, "fetch_website_content", return_value=MOCK_HTML_CONTENT)
@patch.object(SondeProcessor, "get_coordinates")
@patch.object(SondeProcessor, "create_gpx_file", return_value=None)
@patch.object(SondeProcessor, "send_to_telegram", new_callable=AsyncMock)
async def test_main_function_create_gpx_file_fails(
    mock_send_to_telegram,
    mock_create_gpx_file,
    mock_get_coordinates,
    mock_fetch_website_content,
    mock_parse_arguments,
    mock_env_vars,
):
    mock_parse_arguments.return_value = argparse.Namespace(url=MOCK_URL, coords=None)
    mock_get_coordinates.return_value = (
        SondeData(
            last_seen_coords=Coordinates(lat=50.0, lon=10.0),
            last_seen_time=datetime(2023, 10, 27, 10, 0, 0),
            course=90.0,
            altitude=10000.0,
            speed_mps=27.7778,
            climb_rate=-5.0,
        ),
        Coordinates(lat=50.1, lon=10.1),
        100.0,
        1000.0,
    )

    from main import main

    await main()

    mock_parse_arguments.assert_called_once()
    mock_fetch_website_content.assert_called_once()
    mock_get_coordinates.assert_called_once()
    mock_create_gpx_file.assert_called_once()
    mock_send_to_telegram.assert_not_called()


@pytest.mark.asyncio
@patch("main.parse_arguments")
@patch.object(SondeProcessor, "_extract_sonde_number", return_value=None)
async def test_main_function_no_sonde_number(
    mock_extract_sonde_number,
    mock_parse_arguments,
    mock_env_vars,
):
    mock_parse_arguments.return_value = argparse.Namespace(url=MOCK_URL, coords=None)

    from main import main

    await main()

    mock_parse_arguments.assert_called_once()
    mock_extract_sonde_number.assert_called_once()


