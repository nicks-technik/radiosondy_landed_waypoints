import os
from dotenv import load_dotenv
import telegram
import argparse
import requests
from bs4 import BeautifulSoup
import re
import xml.etree.ElementTree as ET
from datetime import datetime
import gpxpy
import gpxpy.gpx


def fetch_website_content(url):
    """Fetches the HTML content of a given URL.

    Args:
        url (str): The URL to fetch the content from.

    Returns:
        str: The HTML content of the website, or None if an error occurred.
    """
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching website content: {e}")
        return None


def parse_coordinates(html_content):
    """Parses the HTML to find the last seen and landing point coordinates.

    Args:
        html_content (str): The HTML content of the radiosonde tracking website.

    Returns:
        tuple: A tuple containing the last seen coordinates (lat, lon),
               the predicted landing point coordinates (lat, lon), and the
               last seen time (datetime object). Returns (None, None, None)
               if parsing fails.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    last_seen = None
    landing_point = None
    last_seen_time = None

    # Find last seen coordinates and time
    try:
        aprs_data_table = soup.find("table", id="Table7")
        first_row = aprs_data_table.find("tbody").find("tr")
        cells = first_row.find_all("td")
        last_seen_time_str = cells[2].text
        lat_str = cells[3].text
        lon_str = cells[4].text
        last_seen = (float(lat_str), float(lon_str))
        last_seen_time = datetime.strptime(last_seen_time_str, "%Y-%m-%d %H:%M:%S")
    except (AttributeError, IndexError, ValueError) as e:
        print(f"Could not parse last seen coordinates: {e}")

    # Find predicted landing coordinates from KML file
    try:
        script_tag = soup.find("script", string=re.compile(r"_predict\.kml"))
        if script_tag:
            match = re.search(
                r"'(mail_reports/PREDICT/.*?_predict\.kml)'", script_tag.string
            )
            if match:
                kml_url = f"http://radiosondy.info/{match.group(1)}"
                kml_content = fetch_website_content(kml_url)
                if kml_content:
                    root = ET.fromstring(kml_content)
                    # KML namespace is often present, so we need to handle it
                    namespace = root.tag.split("}")[0][1:]
                    coords_tag = root.find(
                        f".//{{{namespace}}}Point/{{{namespace}}}coordinates"
                    )
                    if coords_tag is not None:
                        coords_str = coords_tag.text.strip()
                        lon, lat, _ = map(float, coords_str.split(','))
                        landing_point = (lat, lon)
    except Exception as e:
        print(f"Could not parse predicted landing coordinates: {e}")

    return last_seen, landing_point, last_seen_time


def create_gpx_file(last_seen, landing_point, sonde_number, last_seen_time):
    """Creates a GPX file with waypoints for the last seen and landing point.

    Args:
        last_seen (tuple): A tuple containing the latitude and longitude of the last seen position.
        landing_point (tuple): A tuple containing the latitude and longitude of the predicted landing position.
        sonde_number (str): The radiosonde identification number.
        last_seen_time (datetime): The timestamp of the last seen position.

    Returns:
        str: The filename of the created GPX file, or None if an error occurred.
    """
    gpx = gpxpy.gpx.GPX()

    # Create last seen waypoint
    last_seen_waypoint = gpxpy.gpx.GPXWaypoint()
    last_seen_waypoint.latitude = last_seen[0]
    last_seen_waypoint.longitude = last_seen[1]
    last_seen_waypoint.name = "Last Seen"
    gpx.waypoints.append(last_seen_waypoint)

    # Create landing point waypoint
    landing_point_waypoint = gpxpy.gpx.GPXWaypoint()
    landing_point_waypoint.latitude = landing_point[0]
    landing_point_waypoint.longitude = landing_point[1]
    landing_point_waypoint.name = "Predicted Landing"
    gpx.waypoints.append(landing_point_waypoint)

    try:
        time_str = last_seen_time.strftime("%y%m%d_%H%M")
        filename = f"gpx/{sonde_number}_{time_str}_gpx_waypoint.gpx"
        with open(filename, "w") as f:
            f.write(gpx.to_xml())
        print(f"Successfully created {filename}")
        return filename
    except IOError as e:
        print(f"Error writing GPX file: {e}")
        return None


async def send_to_telegram(file_path):
    """Sends the GPX file to a Telegram chat.

    This function reads the Telegram bot token and chat ID from the .env file.

    Args:
        file_path (str): The path to the GPX file to send.
    """
    bot_token = os.getenv("ENV_TELEGRAM_BOT_TOKEN")
    print(f"bot_token: {bot_token}")
    chat_id = os.getenv("ENV_TELEGRAM_CHAT_ID")
    print(f"chat_id: {chat_id}")

    if not bot_token or not chat_id:
        print("Telegram bot token or chat ID not found in .env file.")
        return

    try:
        bot = telegram.Bot(token=bot_token)
        with open(file_path, "rb") as f:
            await bot.send_document(chat_id=chat_id, document=f)
        print(f"Successfully sent {file_path} to Telegram.")
    except Exception as e:
        print(f"Error sending file to Telegram: {e}")


def main():
    """Main function to orchestrate the script execution.

    This function parses the command-line arguments, fetches and parses the
    radiosonde data, creates a GPX file, and sends it to Telegram.
    """
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Generate a GPX waypoint file from a radiosonde tracking website."
    )
    parser.add_argument("url", help="The URL of the radiosonde tracking website.")
    args = parser.parse_args()

    html_content = fetch_website_content(args.url)
    if html_content:
        last_seen, landing_point, last_seen_time = parse_coordinates(html_content)
        if last_seen and landing_point and last_seen_time:
            match = re.search(r"sondenumber=([A-Z0-9]+)", args.url)
            if match:
                sonde_number = match.group(1)
                filename = create_gpx_file(
                    last_seen, landing_point, sonde_number, last_seen_time
                )
                if filename:
                    import asyncio

                    asyncio.run(send_to_telegram(filename))
            else:
                print("Could not extract sonde number from URL.")


if __name__ == "__main__":
    main()