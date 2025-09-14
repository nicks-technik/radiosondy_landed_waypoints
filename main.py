import argparse
import asyncio
import logging
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime

import gpxpy
import gpxpy.gpx
import requests
import telegram
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Constants
EARTH_RADIUS_KM = 6371.0
GPX_SYMBOL_LAST_SEEN = "transport-airport"
GPX_SYMBOL_PREDICTED_LANDING = "z-ico01"
GPX_SYMBOL_RADIOSONDY_LANDING = "z-ico02"
APRS_DATA_TABLE_ID = "Table7"


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class Coordinates:
    lat: float
    lon: float


@dataclass
class SondeData:
    """Holds the parsed data for a radiosonde."""

    last_seen_coords: Coordinates
    last_seen_time: datetime
    course: float
    altitude: float
    speed_mps: float
    climb_rate: float


class SondeProcessor:
    def __init__(self, url: str, coords: str | None = None):
        self.url = url
        self.coords = coords
        self.sonde_number = self._extract_sonde_number(url)
        self.radiosondy_coords = None
        self.radiosondy_coords_description = None
        self._parse_radiosondy_coords()

    def _extract_sonde_number(self, url: str) -> str | None:
        match = re.search(r"sondenumber=([A-Z0-9]+)", url)
        if match:
            return match.group(1)
        logger.warning("Could not extract sonde number from URL.")
        return None

    def _parse_radiosondy_coords(self):
        if self.coords:
            try:
                coords_match = re.match(
                    r"([\d.\-]+),([\d.\-]+)(\s+at\s+(.*))?", self.coords
                )
                if coords_match:
                    lat_str = coords_match.group(1)
                    lon_str = coords_match.group(2)
                    self.radiosondy_coords = Coordinates(
                        lat=float(lat_str), lon=float(lon_str)
                    )
                    if coords_match.group(4):
                        self.radiosondy_coords_description = coords_match.group(4)
                else:
                    logger.warning(
                        "Invalid format for --coords. Please use 'lat,lon' or 'lat,lon at YYYY-MM-DDTHH:MM:SS.ssZ'."
                    )
                logger.info(f"radiosondy_coords: {self.radiosondy_coords}")
            except ValueError:
                logger.warning(
                    "Invalid format for --coords. Please use 'lat,lon' or 'lat,lon at YYYY-MM-DDTHH:MM:SS.ssZ'."
                )

    def fetch_website_content(self) -> str | None:
        """Fetches the HTML content of a given URL."""
        try:
            response = requests.get(self.url)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching website content: {e}")
            return None

    def calculate_landing_point(
        self,
        coords: Coordinates,
        altitude: float,
        speed: float,
        course: float,
        descent_rate: float,
        ground_height: float,
    ) -> tuple[Coordinates, float]:
        """Calculates the predicted landing point based on last known position, altitude, speed, and course."""
        height_to_descend = altitude - ground_height
        if height_to_descend < 0:
            height_to_descend = 0

        logger.info("Calculating landing point with:")
        logger.info(f"  - Altitude: {altitude} m")
        logger.info(f"  - Ground Height: {ground_height} m")
        logger.info(f"  - Height to Descend: {height_to_descend} m")
        logger.info(f"  - Speed: {speed} m/s")
        logger.info(f"  - Course: {course} degrees")
        logger.info(f"  - Descent Rate: {descent_rate} m/s")

        time_to_ground = height_to_descend / descent_rate
        logger.info(f"  - Time to Ground: {time_to_ground} s")

        distance_km = (speed * time_to_ground) / 1000.0
        logger.info(f"  - Distance: {distance_km} km")

        lat_rad = math.radians(coords.lat)
        lon_rad = math.radians(coords.lon)
        course_rad = math.radians(course)

        new_lat_rad = math.asin(
            math.sin(lat_rad) * math.cos(distance_km / EARTH_RADIUS_KM)
            + math.cos(lat_rad)
            * math.sin(distance_km / EARTH_RADIUS_KM)
            * math.cos(course_rad)
        )
        new_lon_rad = lon_rad + math.atan2(
            math.sin(course_rad)
            * math.sin(distance_km / EARTH_RADIUS_KM)
            * math.cos(lat_rad),
            math.cos(distance_km / EARTH_RADIUS_KM)
            - math.sin(lat_rad) * math.sin(new_lat_rad),
        )

        new_lat = math.degrees(new_lat_rad)
        new_lon = math.degrees(new_lon_rad)

        return Coordinates(lat=new_lat, lon=new_lon), time_to_ground

    def parse_last_seen_data(self, soup) -> SondeData | None:
        """Parses the HTML to find the last seen coordinates, time, course, altitude and speed."""
        try:
            aprs_data_table = soup.find("table", id=APRS_DATA_TABLE_ID)
            first_row = aprs_data_table.find("tbody").find("tr")
            cells = first_row.find_all("td")
            last_seen_time_str = cells[2].text
            lat_str = cells[3].text
            lon_str = cells[4].text
            course = cells[5].text
            speed_kmh = cells[6].text
            altitude = cells[7].text
            climb_rate_str = cells[8].text

            climb_rate_match = re.search(r"[-+]?\d*\.\d+|\d+", climb_rate_str)
            climb_rate = float(climb_rate_match.group()) if climb_rate_match else 0.0

            speed_mps = float(speed_kmh) * 1000 / 3600

            last_seen_time = datetime.strptime(last_seen_time_str, "%Y-%m-%d %H:%M:%S")
            logger.info(f"last_seen: ({float(lat_str)}, {float(lon_str)})")
            return SondeData(
                last_seen_coords=Coordinates(lat=float(lat_str), lon=float(lon_str)),
                last_seen_time=last_seen_time,
                course=float(course),
                altitude=float(altitude),
                speed_mps=speed_mps,
                climb_rate=climb_rate,
            )
        except (AttributeError, IndexError, ValueError) as e:
            logger.error(f"Could not parse last seen data: {e}")
            return None

    def get_coordinates(
        self, html_content: str
    ) -> tuple[SondeData | None, Coordinates | None, float, float]:
        """Parses HTML content to extract sonde data and calculate landing coordinates."""
        soup = BeautifulSoup(html_content, "html.parser")
        landing_point = None
        ground_height = 0.0
        time_to_ground = 0.0

        try:
            ground_altitude_match = re.search(r"Ground Altitude: (\d+) m", html_content)
            if ground_altitude_match:
                ground_height = float(ground_altitude_match.group(1))
        except (AttributeError, IndexError, ValueError) as e:
            logger.error(f"Could not parse ground height: {e}")

        sonde_data = self.parse_last_seen_data(soup)

        if sonde_data:
            descent_rate = abs(sonde_data.climb_rate)
            if descent_rate > 0:
                landing_point_coords, time_to_ground = self.calculate_landing_point(
                    sonde_data.last_seen_coords,
                    sonde_data.altitude,
                    sonde_data.speed_mps,
                    sonde_data.course,
                    descent_rate,
                    ground_height,
                )
                landing_point = landing_point_coords

        logger.info(f"landing_point: {landing_point}")

        return sonde_data, landing_point, ground_height, time_to_ground

    def create_gpx_file(
        self,
        sonde_data: SondeData,
        landing_point: Coordinates,
        ground_height: float,
        time_to_ground: float,
    ) -> str | None:
        """Creates a GPX file with waypoints for the last seen and landing point."""

        gpx = gpxpy.gpx.GPX()

        time_str = sonde_data.last_seen_time.strftime("%y%m%d_%H%M")

        last_seen_waypoint = gpxpy.gpx.GPXWaypoint()
        last_seen_waypoint.latitude = sonde_data.last_seen_coords.lat
        last_seen_waypoint.longitude = sonde_data.last_seen_coords.lon
        last_seen_waypoint.name = f"{self.sonde_number} Last Seen"
        last_seen_waypoint.description = f"Course: {sonde_data.course}, Speed {sonde_data.speed_mps}, Altitude: {sonde_data.altitude}, GroundHeight: {ground_height}"
        last_seen_waypoint.symbol = GPX_SYMBOL_LAST_SEEN
        gpx.waypoints.append(last_seen_waypoint)

        landing_point_waypoint = gpxpy.gpx.GPXWaypoint()
        landing_point_waypoint.latitude = landing_point.lat
        landing_point_waypoint.longitude = landing_point.lon
        landing_point_waypoint.name = f"{self.sonde_number} Predicted Landing"
        landing_point_waypoint.description = f"Time2Ground: {time_to_ground}, GroundHeight: {ground_height}, LandingTime: {time_str}"
        landing_point_waypoint.symbol = GPX_SYMBOL_PREDICTED_LANDING
        gpx.waypoints.append(landing_point_waypoint)

        if self.radiosondy_coords:
            radiosondy_waypoint = gpxpy.gpx.GPXWaypoint()
            radiosondy_waypoint.latitude = self.radiosondy_coords.lat
            radiosondy_waypoint.longitude = self.radiosondy_coords.lon
            radiosondy_waypoint.name = f"{self.sonde_number} radiosondy Landing Point"
            if self.radiosondy_coords_description:
                radiosondy_waypoint.description = self.radiosondy_coords_description
            radiosondy_waypoint.symbol = GPX_SYMBOL_RADIOSONDY_LANDING
            gpx.waypoints.append(radiosondy_waypoint)
            logger.info(f"radiosondy_coords: {self.radiosondy_coords}")

        try:
            filename = f"gpx/{self.sonde_number}_{time_str}_gpx_waypoint.gpx"
            with open(filename, "w") as f:
                f.write(gpx.to_xml())
            logger.info(f"Successfully created {filename}")
            return filename
        except IOError as e:
            logger.error(f"Error writing GPX file: {e}")
            return None

    async def send_to_telegram(self, file_path: str):
        """Sends the GPX file to a Telegram chat."""
        bot_token = os.getenv("ENV_TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("ENV_TELEGRAM_CHAT_ID")

        if not bot_token or not chat_id:
            logger.warning("Telegram bot token or chat ID not found in .env file.")
            return

        try:
            bot = telegram.Bot(token=bot_token)
            with open(file_path, "rb") as f:
                logger.info(f"Trying to send {file_path} to Telegram")
                await bot.send_document(chat_id=chat_id, document=f)
            logger.info(f"Successfully sent {file_path} to Telegram.")
        except Exception as e:
            logger.error(f"Error sending file to Telegram: {e}")


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Generate a GPX waypoint file from a radiosonde tracking website."
    )
    parser.add_argument("url", help="The URL of the radiosonde tracking website.")
    parser.add_argument(
        "--coords",
        help="Optional coordinates in format 'lat,lon' to add as a waypoint.",
    )
    return parser.parse_args()


async def main():
    """Main function to orchestrate the script execution."""
    load_dotenv()
    args = parse_arguments()

    processor = SondeProcessor(args.url, args.coords)

    if not processor.sonde_number:
        return

    html_content = processor.fetch_website_content()
    if html_content:
        sonde_data, landing_point, ground_height, time_to_ground = (
            processor.get_coordinates(html_content)
        )
        if sonde_data and landing_point:
            filename = processor.create_gpx_file(
                sonde_data, landing_point, ground_height, time_to_ground
            )
            if filename:
                await processor.send_to_telegram(filename)


if __name__ == "__main__":
    asyncio.run(main())
