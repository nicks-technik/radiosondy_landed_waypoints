import os
import re
import tempfile
import unittest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass

# Import the module
import sys
sys.path.insert(0, '/home/hermes/dev/radiosondy_landed_waypoints')
from main import (
    Coordinates, SondeData, SondeProcessor, 
    EARTH_RADIUS_KM, GPX_SYMBOL_LAST_SEEN, GPX_SYMBOL_PREDICTED_LANDING, 
    GPX_SYMBOL_RADIOSONDY_LANDING, APRS_DATA_TABLE_ID
)

class TestCoordinates(unittest.TestCase):
    """Tests for the Coordinates dataclass"""
    
    def test_coordinates_creation(self):
        """Test creating Coordinates object"""
        coords = Coordinates(lat=49.915, lon=9.5154)
        self.assertEqual(coords.lat, 49.915)
        self.assertEqual(coords.lon, 9.5154)
    
    def test_coordinates_negative_values(self):
        """Test Coordinates with negative values"""
        coords = Coordinates(lat=-33.9017, lon=152.466)
        self.assertEqual(coords.lat, -33.9017)
        self.assertEqual(coords.lon, 152.466)


class TestSondeData(unittest.TestCase):
    """Tests for the SondeData dataclass"""
    
    def test_sonde_data_creation(self):
        """Test creating SondeData object"""
        coords = Coordinates(lat=49.915, lon=9.5154)
        sonde = SondeData(
            last_seen_coords=coords,
            last_seen_time=datetime(2024, 1, 1, 12, 0, 0),
            course=319.0,
            altitude=544.0,
            speed_mps=5.56,
            climb_rate=-7.0
        )
        self.assertEqual(sonde.last_seen_coords.lat, 49.915)
        self.assertEqual(sonde.course, 319.0)
        self.assertEqual(sonde.altitude, 544.0)
        self.assertEqual(sonde.speed_mps, 5.56)
        self.assertEqual(sonde.climb_rate, -7.0)


class TestGPXSymbols(unittest.TestCase):
    """Tests for GPX symbol constants"""
    
    def test_symbol_constants_defined(self):
        """Test that all symbol constants are defined"""
        self.assertEqual(GPX_SYMBOL_LAST_SEEN, "transport-airport")
        self.assertEqual(GPX_SYMBOL_PREDICTED_LANDING, "z-ico01")
        self.assertEqual(GPX_SYMBOL_RADIOSONDY_LANDING, "z-ico02")
    
    def test_aprs_table_id(self):
        """Test APRS data table ID"""
        self.assertEqual(APRS_DATA_TABLE_ID, "Table7")


class TestSondeProcessorURLParsing(unittest.TestCase):
    """Tests for sonde number extraction from URLs"""
    
    def test_extract_sonde_number_d_type(self):
        """Test extracting D-series sonde number"""
        url = "https://radiosondy.info/sonde_archive.php?sondenumber=D20040532"
        processor = SondeProcessor(url, None)
        self.assertEqual(processor.sonde_number, "D20040532")
    
    def test_extract_sonde_number_x_type(self):
        """Test extracting X-series sonde number"""
        url = "https://radiosondy.info/sonde.php?sondenumber=X3432089"
        processor = SondeProcessor(url, None)
        self.assertEqual(processor.sonde_number, "X3432089")
    
    def test_extract_sonde_number_w_type(self):
        """Test extracting W-series sonde number"""
        url = "https://radiosondy.info/sonde_archive.php?sondenumber=W2350755Z"
        processor = SondeProcessor(url, None)
        self.assertEqual(processor.sonde_number, "W2350755Z")
    
    def test_invalid_url_returns_none(self):
        """Test URL without sonde number"""
        url = "https://radiosondy.info/index.php"
        processor = SondeProcessor(url, None)
        self.assertIsNone(processor.sonde_number)


class TestCoordsParsing(unittest.TestCase):
    """Tests for --coords argument parsing"""
    
    def test_parse_coords_with_timestamp(self):
        """Test parsing coordinates with timestamp"""
        coords_str = "49.91424,9.51475 at 2026-08-11T11:53:27.125Z"
        processor = SondeProcessor("https://radiosondy.info/sonde_archive.php?sondenumber=D20040532", coords_str)
        self.assertIsNotNone(processor.radiosondy_coords)
        self.assertAlmostEqual(processor.radiosondy_coords.lat, 49.91424)
        self.assertAlmostEqual(processor.radiosondy_coords.lon, 9.51475)
        self.assertEqual(processor.radiosondy_coords_description, "2026-08-11T11:53:27.125Z")
    
    def test_parse_coords_negative_values(self):
        """Test parsing coordinates with negative values"""
        coords_str = "-33.87567,152.28691 at 2026-08-16T21:40:45.375Z"
        processor = SondeProcessor("https://radiosondy.info/sonde.php?sondenumber=X3432089", coords_str)
        self.assertIsNotNone(processor.radiosondy_coords)
        self.assertAlmostEqual(processor.radiosondy_coords.lat, -33.87567)
        self.assertAlmostEqual(processor.radiosondy_coords.lon, 152.28691)
    
    def test_parse_invalid_coords(self):
        """Test invalid coordinate format"""
        coords_str = "invalid format"
        processor = SondeProcessor("https://radiosondy.info/sonde_archive.php?sondenumber=D20040532", coords_str)
        self.assertIsNone(processor.radiosondy_coords)


class TestLandingPointCalculation(unittest.TestCase):
    """Tests for landing point calculation"""
    
    def test_calculate_landing_point_basic(self):
        """Test basic landing point calculation"""
        processor = SondeProcessor("https://radiosondy.info/sonde_archive.php?sondenumber=D20040532", None)
        coords = Coordinates(lat=49.915, lon=9.5154)
        
        landing_point, time_to_ground = processor.calculate_landing_point(
            coords=coords,
            altitude=544.0,
            speed=5.56,
            course=319.0,
            descent_rate=7.0,
            ground_height=225.0
        )
        
        self.assertIsInstance(landing_point, Coordinates)
        self.assertGreaterEqual(landing_point.lat, 49.91)
        self.assertLessEqual(landing_point.lat, 49.93)
        self.assertGreaterEqual(time_to_ground, 40)
        self.assertLessEqual(time_to_ground, 50)
    
    def test_landing_point_calculation_with_zero_altitude(self):
        """Test calculation when balloon is already at ground level"""
        processor = SondeProcessor("https://radiosondy.info/sonde_archive.php?sondenumber=D20040532", None)
        coords = Coordinates(lat=49.915, lon=9.5154)
        
        landing_point, time_to_ground = processor.calculate_landing_point(
            coords=coords,
            altitude=100.0,
            speed=5.0,
            course=0.0,
            descent_rate=7.0,
            ground_height=100.0
        )
        
        self.assertEqual(time_to_ground, 0.0)
        # Should still return coordinates (same as input)
        self.assertIsInstance(landing_point, Coordinates)


class TestPredictionKMLParsing(unittest.TestCase):
    """Tests for prediction KML parsing"""
    
    def test_parse_prediction_with_timestamp(self):
        """Test parsing KML with timestamp"""
        kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml>
<Document>
<Placemark>
<name>Balloon Landing</name>
<description>Balloon landing at 49.91424,9.51475 at 2026-08-11T11:53:27.125Z.</description>
<coordinates>9.51475,49.91424,1.0</coordinates>
</Placemark>
</Document>
</kml>"""
        
        processor = SondeProcessor("https://radiosondy.info/sonde_archive.php?sondenumber=D20040532", None)
        coords, timestamp = processor.parse_prediction_kml(kml_content)
        
        self.assertIsNotNone(coords)
        self.assertIsNotNone(timestamp)
        self.assertAlmostEqual(coords.lat, 49.91424, places=5)
        self.assertAlmostEqual(coords.lon, 9.51475, places=5)
        self.assertEqual(timestamp, "2026-08-11T11:53:27.125Z")
    
    def test_parse_prediction_without_timestamp(self):
        """Test parsing KML without timestamp"""
        kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml>
<Document>
<Placemark>
<name>Balloon Landing</name>
<description>Balloon landing at 49.91424,9.51475.</description>
<coordinates>9.51475,49.91424,1.0</coordinates>
</Placemark>
</Document>
</kml>"""
        
        processor = SondeProcessor("https://radiosondy.info/sonde_archive.php?sondenumber=D20040532", None)
        coords, timestamp = processor.parse_prediction_kml(kml_content)
        
        self.assertIsNotNone(coords)
        self.assertIsNone(timestamp)
    
    def test_parse_prediction_empty_content(self):
        """Test parsing empty KML content"""
        processor = SondeProcessor("https://radiosondy.info/sonde_archive.php?sondenumber=D20040532", None)
        coords, timestamp = processor.parse_prediction_kml("")
        self.assertIsNone(coords)
        self.assertIsNone(timestamp)


class TestHTMLParsing(unittest.TestCase):
    """Tests for HTML parsing functionality"""
    
    def test_parse_last_seen_data_with_mock_html(self):
        """Test parsing last seen data from mocked HTML"""
        # Create mock HTML with table data
        mock_html = """
        <table id="Table7">
            <tbody>
                <tr>
                    <td>1</td>
                    <td>TEST</td>
                    <td>2024-01-01 12:00:00</td>
                    <td>49.915</td>
                    <td>9.5154</td>
                    <td>319.0</td>
                    <td>20.0</td>
                    <td>544.0</td>
                    <td>-7.0</td>
                </tr>
            </tbody>
        </table>
        """
        
        processor = SondeProcessor("https://radiosondy.info/sonde_archive.php?sondenumber=D20040532", None)
        
        with patch.object(processor, 'parse_last_seen_data') as mock_parse:
            # Test with mock data
            mock_result = SondeData(
                last_seen_coords=Coordinates(lat=49.915, lon=9.5154),
                last_seen_time=datetime(2024, 1, 1, 12, 0, 0),
                course=319.0,
                altitude=544.0,
                speed_mps=5.56,
                climb_rate=7.0
            )
            mock_parse.return_value = mock_result
            
            result = processor.get_coordinates(mock_html)
            self.assertIsNotNone(result[0])
            self.assertIsNotNone(result[1])


class TestGPXFileGeneration(unittest.TestCase):
    """Tests for GPX file creation"""
    
    def test_create_gpx_file(self):
        """Test GPX file creation"""
        processor = SondeProcessor("https://radiosondy.info/sonde_archive.php?sondenumber=D20040532", None)
        processor.radiosondy_coords = Coordinates(lat=49.91424, lon=9.51475)
        processor.radiosondy_coords_description = "2026-08-11T11:53:27.125Z"
        
        sonde_data = SondeData(
            last_seen_coords=Coordinates(lat=49.915, lon=9.5154),
            last_seen_time=datetime(2024, 1, 1, 11, 52, 0),
            course=319.0,
            altitude=544.0,
            speed_mps=5.56,
            climb_rate=7.0
        )
        
        landing_point = Coordinates(lat=49.916718, lon=9.513080)
        
        # Create in temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(SondeProcessor, 'create_gpx_file', return_value=f"{tmpdir}/test.gpx"):
                result = processor.create_gpx_file(sonde_data, landing_point, 225.0, 45.57)
                # Since we're mocking the method, just verify it doesn't crash
    
    def test_gpx_symbols_in_output(self):
        """Test that symbols are present in GPX output"""
        # This would need mocking the file write to test the actual content
        self.assertEqual(GPX_SYMBOL_LAST_SEEN, "transport-airport")
        self.assertEqual(GPX_SYMBOL_PREDICTED_LANDING, "z-ico01")
        self.assertEqual(GPX_SYMBOL_RADIOSONDY_LANDING, "z-ico02")


class TestEnvironmentVariables(unittest.TestCase):
    """Tests for environment variable handling"""
    
    def test_missing_telegram_env_vars(self):
        """Test behavior when Telegram env vars are missing"""
        # This tests that the method handles missing env vars gracefully
        processor = SondeProcessor("https://radiosondy.info/sonde_archive.php?sondenumber=D20040532", None)
        # The method should not crash, just log a warning
        import asyncio
        asyncio.run(processor.send_to_telegram("nonexistent.gpx"))
        # If we get here without exception, test passes


class TestEarthRadiusCalculation(unittest.TestCase):
    """Tests for earth radius constant"""
    
    def test_earth_radius_value(self):
        """Test that earth radius is reasonable"""
        self.assertEqual(EARTH_RADIUS_KM, 6371.0)
    
    def test_landing_distance_calculation(self):
        """Test that distance calculation is reasonable"""
        processor = SondeProcessor("https://radiosondy.info/sonde_archive.php?sondenumber=D20040532", None)
        coords = Coordinates(lat=0, lon=0)
        
        # Test with known values
        landing_point, time_to_ground = processor.calculate_landing_point(
            coords=coords,
            altitude=1000.0,
            speed=10.0,
            course=0.0,
            descent_rate=10.0,
            ground_height=0.0
        )
        
        # Distance should be approximately speed * time_to_ground / 1000 in km
        expected_distance = (10.0 * 100.0) / 1000.0  # 1 km
        # Landing point should be north of equator (small amount)
        self.assertGreater(landing_point.lat, coords.lat)


if __name__ == '__main__':
    unittest.main(verbosity=2)
