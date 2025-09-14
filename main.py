import argparse
import math
import os
import re
from datetime import datetime

import gpxpy
import gpxpy.gpx
import requests
import telegram
from bs4 import BeautifulSoup
from dotenv import load_dotenv


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


def calculate_landing_point(
    lat, lon, altitude, speed, course, descent_rate, ground_height
):
    """Calculates the predicted landing point based on last known position, altitude, speed, and course.

    Args:
        lat (float): Last known latitude.
        lon (float): Last known longitude.
        altitude (float): Last known altitude in meters.
        speed (float): Last known horizontal speed in m/s.
        course (float): Last known course in degrees.
        descent_rate (float): The descent rate in m/s.
        ground_height (float): The ground height in meters.

    Returns:
        tuple: A tuple containing the predicted latitude and longitude.
    """
    height_to_descend = altitude - ground_height
    if height_to_descend < 0:
        height_to_descend = 0

    print(f"Calculating landing point with:")
    print(f"  - Altitude: {altitude} m")
    print(f"  - Ground Height: {ground_height} m")
    print(f"  - Height to Descend: {height_to_descend} m")
    print(f"  - Speed: {speed} m/s")
    print(f"  - Course: {course} degrees")
    print(f"  - Descent Rate: {descent_rate} m/s")

    global time_to_ground

    time_to_ground = height_to_descend / descent_rate
    print(f"  - Time to Ground: {time_to_ground} s")

    distance_km = (speed * time_to_ground) / 1000.0
    print(f"  - Distance: {distance_km} km")

    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    course_rad = math.radians(course)

    # Earth radius in km
    earth_radius_km = 6371.0

    new_lat_rad = math.asin(
        math.sin(lat_rad) * math.cos(distance_km / earth_radius_km)
        + math.cos(lat_rad)
        * math.sin(distance_km / earth_radius_km)
        * math.cos(course_rad)
    )
    new_lon_rad = lon_rad + math.atan2(
        math.sin(course_rad)
        * math.sin(distance_km / earth_radius_km)
        * math.cos(lat_rad),
        math.cos(distance_km / earth_radius_km)
        - math.sin(lat_rad) * math.sin(new_lat_rad),
    )

    new_lat = math.degrees(new_lat_rad)
    new_lon = math.degrees(new_lon_rad)

    return new_lat, new_lon


def parse_last_seen_data(soup):
    """Parses the HTML to find the last seen coordinates, time, course, altitude and speed.

    Args:
        soup (BeautifulSoup): The BeautifulSoup object of the HTML content.

    Returns:
        tuple: A tuple containing the last seen coordinates (lat, lon),
            the last seen time (datetime object), the course (str),
            the altitude (str) and the speed (str). Returns (None, None, None, None, None)
            if parsing fails.
    """
    try:
        aprs_data_table = soup.find("table", id="Table7")
        first_row = aprs_data_table.find("tbody").find("tr")
        cells = first_row.find_all("td")
        last_seen_time_str = cells[2].text
        lat_str = cells[3].text
        lon_str = cells[4].text
        course = cells[5].text  # Assuming Kurs is in the 6th column (index 5)
        speed_kmh = cells[6].text  # Assuming Speed is in the 7th column (index 6)
        altitude = cells[7].text  # Assuming Höhe is in the 8th column (index 7)
        climb_rate_str = cells[8].text  # Assuming Clb is in the 9th column (index 8)

        # Extract the numeric value from the climb rate string
        climb_rate_match = re.search(r"[-+]?\d*\.\d+|\d+", climb_rate_str)
        climb_rate = float(climb_rate_match.group()) if climb_rate_match else 0.0

        # Convert speed from km/h to m/s
        speed_mps = float(speed_kmh) * 1000 / 3600

        last_seen = (float(lat_str), float(lon_str))
        last_seen_time = datetime.strptime(last_seen_time_str, "%Y-%m-%d %H:%M:%S")
        print(f"last_seen: {last_seen}")
        return (
            last_seen,
            last_seen_time,
            float(course),
            float(altitude),
            speed_mps,
            climb_rate,
        )
    except (AttributeError, IndexError, ValueError) as e:
        print(f"Could not parse last seen data: {e}")
        return None, None, None, None, None, None


def get_coordinates(html_content):
    """Get the HTML to find the last seen coordinates.

    Args:
        html_content (str): The HTML content of the radiosonde tracking website.

    """
    soup = BeautifulSoup(html_content, "html.parser")
    landing_point = None
    ground_height = 0.0

    # Find ground height
    try:
        ground_altitude_match = re.search(r"Ground Altitude: (\d+) m", html_content)
        if ground_altitude_match:
            ground_height = float(ground_altitude_match.group(1))
    except Exception as e:
        print(f"Could not parse ground height: {e}")

    # Use the new helper function to parse last seen data
    last_seen, last_seen_time, course, altitude, speed, climb_rate = (
        parse_last_seen_data(soup)
    )

    if (
        last_seen
        and course is not None
        and altitude is not None
        and speed is not None
        and climb_rate is not None
    ):
        # Use the absolute value of the climb rate as the descent rate
        descent_rate = abs(climb_rate)
        if descent_rate > 0:
            landing_point = calculate_landing_point(
                last_seen[0],
                last_seen[1],
                altitude,
                speed,
                course,
                descent_rate,
                ground_height,
            )

    print(f"landing_point: {landing_point}")

    return (
        last_seen,
        landing_point,
        last_seen_time,
        course,
        altitude,
        speed,
        ground_height,
        time_to_ground,
    )


def create_gpx_file(
    last_seen,
    landing_point,
    sonde_number,
    last_seen_time,
    course,
    altitude,
    speed,
    ground_height,
    time_to_ground,
):
    """Creates a GPX file with waypoints for the last seen and landing point.

    Args:
        last_seen (tuple): A tuple containing the latitude and longitude of the last seen position.
        landing_point (tuple): A tuple containing the latitude and longitude of the predicted landing position.
        sonde_number (str): The radiosonde identification number.
        last_seen_time (datetime): The timestamp of the last seen position.
        course (str): The course of the radiosonde at the last seen position.
        altitude (str): The altitude of the radiosonde at the last seen position.

    Returns:
        str: The filename of the created GPX file, or None if an error occurred.
    """

    gpx = gpxpy.gpx.GPX()

    time_str = last_seen_time.strftime("%y%m%d_%H%M")

    # Create last seen waypoint
    last_seen_waypoint = gpxpy.gpx.GPXWaypoint()
    last_seen_waypoint.latitude = last_seen[0]
    last_seen_waypoint.longitude = last_seen[1]
    last_seen_waypoint.name = f"{sonde_number} Last Seen"
    last_seen_waypoint.description = f"Course: {course}, Speed {speed}, Altitude: {altitude}, GroundHeight: {ground_height}"
    last_seen_waypoint.symbol = "transport-airport"
    gpx.waypoints.append(last_seen_waypoint)

    # Create landing point waypoint
    landing_point_waypoint = gpxpy.gpx.GPXWaypoint()
    landing_point_waypoint.latitude = landing_point[0]
    landing_point_waypoint.longitude = landing_point[1]
    landing_point_waypoint.name = f"{sonde_number} Predicted Landing"
    landing_point_waypoint.description = f"Time2Ground: {time_to_ground}, GroundHeight: {ground_height}, LandingTime: {time_str}"
    landing_point_waypoint.symbol = "z-ico01"
    gpx.waypoints.append(landing_point_waypoint)

    try:
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
    chat_id = os.getenv("ENV_TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("Telegram bot token or chat ID not found in .env file.")
        return

    try:
        bot = telegram.Bot(token=bot_token)
        with open(file_path, "rb") as f:
            print(f"Try to send {file_path} to Telegram")
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
        (
            last_seen,
            landing_point,
            last_seen_time,
            course,
            altitude,
            speed,
            ground_height,
            time_to_ground,
        ) = get_coordinates(html_content)
        if (
            last_seen
            and landing_point
            and last_seen_time
            and course is not None
            and altitude is not None
        ):
            match = re.search(r"sondenumber=([A-Z0-9]+)", args.url)
            if match:
                sonde_number = match.group(1)
                filename = create_gpx_file(
                    last_seen,
                    landing_point,
                    sonde_number,
                    last_seen_time,
                    course,
                    altitude,
                    speed,
                    ground_height,
                    time_to_ground,
                )
                if filename:
                    import asyncio

                    print(f"filename: {filename}")
                    asyncio.run(send_to_telegram(filename))
            else:
                print("Could not extract sonde number from URL.")


if __name__ == "__main__":
    main()
