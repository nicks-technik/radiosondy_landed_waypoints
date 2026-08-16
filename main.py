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
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            })
            response = session.get(self.url)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching website content: {e}")
            return None

    def fetch_prediction_kml(self) -> str | None:
        """Fetches the prediction KML file for the sonde."""
        try:
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            })
            
            # Build prediction URL from radiosondy.info
            kml_url = f"https://radiosondy.info/local_storage/PREDICT/{self.sonde_number}_predict.kml"
            logger.info(f"Fetching prediction KML from: {kml_url}")
            
            response = session.get(kml_url)
            if response.status_code == 200:
                logger.info("Successfully fetched prediction KML data")
                return response.text
            else:
                logger.warning(f"Prediction KML returned status {response.status_code}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching prediction KML: {e}")
            return None

    def parse_prediction_kml(self, kml_content: str) -> tuple[Coordinates | None, str | None]:
        """Parses the prediction KML to extract landing coordinates and timestamp."""
        if not kml_content:
            return None, None
            
        try:
            # Use regex to find the Balloon Landing placemark
            landing_pattern = r'<name>Balloon Landing</name>.*?<description>([^<]*)</description>.*?<coordinates>([^<]+)</coordinates>'
            match = re.search(landing_pattern, kml_content, re.DOTALL | re.IGNORECASE)
            
            if match:
                description = match.group(1)
                coord_str = match.group(2).strip()
                
                # Parse coordinates (format: lon,lat,alt)
                coord_parts = coord_str.split(',')
                if len(coord_parts) >= 2:
                    lon = float(coord_parts[0])
                    lat = float(coord_parts[1])
                    coords = Coordinates(lat=lat, lon=lon)
                    
                    # Extract timestamp from description (format: "Balloon landing at 49.91424,9.51475 at 2026-08-11T11:53:27.125Z.")
                    time_match = re.search(r'at (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z)', description)
                    if time_match:
                        timestamp = time_match.group(1)
                        logger.info(f"Parsed prediction: ({lat}, {lon}) at {timestamp}")
                        return coords, timestamp
                    
                    logger.info(f"Parsed prediction coordinates: ({lat}, {lon})")
                    return coords, None
                    
        except (AttributeError, IndexError, ValueError) as e:
            logger.error(f"Could not parse prediction KML: {e}")
            
        return None, None

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
            if aprs_data_table is None:
                # Try alternative table IDs or formats
                tables = soup.find_all('table')
                if tables:
                    # Try first table with data rows
                    for table in tables:
                        rows = table.find_all('tr')
                        if rows and len(rows) > 1:
                            cells = rows[0].find_all(['th', 'td'])
                            cell_text = [cell.get_text(strip=True) for cell in cells]
                            if any('Date' in text or 'Time' in text for text in cell_text):
                                aprs_data_table = table
                                break
            
            if aprs_data_table is None:
                logger.warning("Could not find APRS data table in page. Trying GeoJSON endpoint.")
                return self.parse_last_seen_from_geojson()
                
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
            # Fallback to GeoJSON endpoint
            return self.parse_last_seen_from_geojson()

    def parse_last_seen_from_geojson(self) -> SondeData | None:
        """Parses the GeoJSON file for last seen data when the HTML table is unavailable."""
        try:
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            })
            
            # Try multiple URL patterns for GeoJSON
            # sonde.php pages use export/export_map.php endpoint
            geojson_urls = [
                f"https://radiosondy.info/export/export_map.php?sonde_map=1&sondenumber={self.sonde_number}",
                f"https://radiosondy.info/local_storage/GeoJSON/{self.sonde_number}.json",
                f"https://radiosondy.info/local_storage/GeoJSON/{self.sonde_number[0]}/{self.sonde_number}.json",
            ]
            
            data = None
            for url in geojson_urls:
                logger.info(f"Fetching GeoJSON from: {url}")
                response = session.get(url)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        logger.info("Successfully fetched GeoJSON data")
                        break
                    except Exception as json_err:
                        logger.debug(f"JSON parse failed for {url}: {json_err}")
                        continue
                        
            if not data:
                logger.warning("Could not fetch GeoJSON from any URL pattern")
                return None
                
            # Look for the sonde data point (Point features with properties)
            for feature in data.get('features', []):
                props = feature.get('properties', {})
                coords = feature.get('geometry', {}).get('coordinates', [])
                
                # Skip LineString features (flight path)
                geom_type = feature.get('geometry', {}).get('type')
                if geom_type != 'Point':
                    continue
                    
                # Look for Point features with telemetry data (indicates it's the last known position)
                if len(coords) >= 3:
                    lon, lat, alt = coords[0], coords[1], coords[2]
                    
                    # Check if this has telemetry data (indicates it's the last known position)
                    report = props.get('report', '')
                    popup_content = props.get('popupContent', '')
                    # Strip HTML tags for easier regex parsing
                    import html as html_module
                    from html.parser import HTMLParser
                    
                    class StripTagsParser(HTMLParser):
                        def __init__(self):
                            super().__init__()
                            self.result = []
                        def handle_data(self, data):
                            self.result.append(data)
                        def get_text(self):
                            return ''.join(self.result)
                    
                    parser = StripTagsParser()
                    parser.feed(popup_content or '')
                    clean_popup = parser.get_text()
                    
                    if report or props.get('speed') or props.get('course') or 'Report:' in (popup_content or ''):
                        # Parse date/time from clean popup content
                        time_match = re.search(r'Report:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})z', clean_popup, re.IGNORECASE)
                        if not time_match:
                            time_match = re.search(r'Report:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', clean_popup, re.IGNORECASE)
                            
                        if time_match:
                            last_seen_time_str = time_match.group(1)
                            last_seen_time = datetime.strptime(last_seen_time_str, "%Y-%m-%d %H:%M:%S")
                        else:
                            # Try using report field directly
                            report_str = props.get('report', '')
                            time_match = re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', report_str, re.IGNORECASE)
                            if time_match:
                                last_seen_time = datetime.strptime(time_match.group(1), "%Y-%m-%d %H:%M:%S")
                            else:
                                last_seen_time = datetime.now()
                        
                        # Extract data from clean popup content
                        course = 0.0
                        speed_kmh = 0.0
                        climb_rate = 0.0
                        
                        # Course
                        course_match = re.search(r'Course:\s*([\d.]+)', clean_popup)
                        if course_match:
                            course = float(course_match.group(1))
                        
                        # Speed
                        speed_match = re.search(r'Speed:\s*([\d.]+)', clean_popup)
                        if speed_match:
                            speed_kmh = float(speed_match.group(1))
                        
                        # Climbing/descent rate
                        climbing_match = re.search(r'Climbing:\s*(-?[\d.]+)', clean_popup)
                        if climbing_match:
                            climb_rate = float(climbing_match.group(1))
                             
                        speed_mps = speed_kmh * 1000 / 3600 if speed_kmh > 0 else 0.0
                        
                        logger.info(f"last_seen (from GeoJSON): ({lat}, {lon}) at {last_seen_time}")
                        return SondeData(
                            last_seen_coords=Coordinates(lat=lat, lon=lon),
                            last_seen_time=last_seen_time,
                            course=course,
                            altitude=alt,
                            speed_mps=speed_mps,
                            climb_rate=climb_rate,
                        )
                        
        except Exception as e:
            logger.error(f"Could not parse GeoJSON data: {e}")
            
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
            # Use default descent rate if not available
            if descent_rate == 0:
                descent_rate = 7.0
                logger.info(f"Using default descent rate: {descent_rate} m/s")
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

        time_str = sonde_data.last_seen_time.strftime("%y%m%d_%H%M")

        try:
            filename = f"gpx/{self.sonde_number}_{time_str}_gpx_waypoint.gpx"
            # Build GPX XML manually for maximum compatibility
            xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
            xml_lines.append('<gpx version="1.1" creator="gpx.py">')
            
            # Last Seen waypoint
            xml_lines.append(f'  <wpt lat="{sonde_data.last_seen_coords.lat}" lon="{sonde_data.last_seen_coords.lon}">')
            xml_lines.append(f'    <name>{self.sonde_number} Last Seen</name>')
            xml_lines.append(f'    <desc>Course: {sonde_data.course}, Speed {sonde_data.speed_mps}, Altitude: {sonde_data.altitude}, GroundHeight: {ground_height}</desc>')
            xml_lines.append(f'    <sym>{GPX_SYMBOL_LAST_SEEN}</sym>')
            xml_lines.append('  </wpt>')
            
            # Predicted Landing waypoint
            xml_lines.append(f'  <wpt lat="{landing_point.lat}" lon="{landing_point.lon}">')
            xml_lines.append(f'    <name>{self.sonde_number} My Predicted Landing</name>')
            xml_lines.append(f'    <desc>Time2Ground: {time_to_ground}, GroundHeight: {ground_height}</desc>')
            xml_lines.append(f'    <sym>{GPX_SYMBOL_PREDICTED_LANDING}</sym>')
            xml_lines.append('  </wpt>')
            
            # Radiosondy coords waypoint
            if self.radiosondy_coords:
                xml_lines.append(f'  <wpt lat="{self.radiosondy_coords.lat}" lon="{self.radiosondy_coords.lon}">')
                xml_lines.append(f'    <name>{self.sonde_number} radiosondy Landing Point</name>')
                if self.radiosondy_coords_description:
                    xml_lines.append(f'    <desc>{self.radiosondy_coords_description}</desc>')
                else:
                    xml_lines.append('    <desc></desc>')
                xml_lines.append(f'    <sym>{GPX_SYMBOL_RADIOSONDY_LANDING}</sym>')
                xml_lines.append('  </wpt>')
            
            xml_lines.append('</gpx>')
            xml_content = '\n'.join(xml_lines)
            
            # Write with explicit UTF-8 encoding and Unix line endings for maximum compatibility
            with open(filename, "w", encoding="utf-8", newline="\n") as f:
                f.write(xml_content)
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

    # Fetch prediction data first (works for both sonde.php and sonde_archive.php pages)
    kml_content = processor.fetch_prediction_kml()
    if kml_content:
        pred_coords, timestamp = processor.parse_prediction_kml(kml_content)
        if pred_coords and timestamp:
            coords_str = f"{pred_coords.lat},{pred_coords.lon} at {timestamp}"
            coords_match = re.match(
                r"([\d.\-]+),([\d.\-]+)(\s+at\s+(.*))", coords_str
            )
            if coords_match:
                processor.radiosondy_coords = Coordinates(
                    lat=float(coords_match.group(1)),
                    lon=float(coords_match.group(2))
                )
                processor.radiosondy_coords_description = coords_match.group(4)
                logger.info(f"Auto-detected coords from prediction: {processor.radiosondy_coords}")
        elif pred_coords:
            processor.radiosondy_coords = pred_coords
            logger.info(f"Auto-detected coords from prediction: {processor.radiosondy_coords}")

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
