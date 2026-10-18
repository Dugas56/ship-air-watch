import unittest
import importlib.util
from pathlib import Path

source = Path(__file__).resolve().parents[1] / "linux-pi" / "installers" / "common" / "regional_selection.py"
spec = importlib.util.spec_from_file_location("regional_selection", source)
region = importlib.util.module_from_spec(spec)
spec.loader.exec_module(region)


class RegionalTests(unittest.TestCase):
    def test_zero_distance(self):
        self.assertAlmostEqual(region.distance_km(45, -66, 45, -66), 0)

    def test_ranges_and_nan(self):
        for lat, lon in [(91, 0), (0, -181), (float("nan"), 0)]:
            with self.assertRaises(ValueError):
                region.validate_coordinate(lat, lon)

    def test_sorted_and_filtered(self):
        places = [
            dict(name="Far", category="port", latitude=47, longitude=-66),
            dict(name="Near", category="port", latitude=45.25, longitude=-66),
            dict(name="Airport", category="airport", latitude=45.2, longitude=-66),
        ]
        results = region.suggest(45.2, -66, places, "port", radius_km=300)
        self.assertEqual(results[0]["name"], "Near")
        self.assertEqual(len(region.suggest(45.2, -66, places, "airport", radius_km=100)), 1)
        self.assertFalse(region.suggest(0, 0, places, "port", radius_km=20))

    def test_no_invalid_request(self):
        with self.assertRaises(ValueError):
            region.suggest(45, -66, [], "heliport")
        with self.assertRaises(ValueError):
            region.suggest(45, -66, [], "port", limit=0)


    def test_regional_preview(self):
        result = region.regional_preview(45.27, -66.06, [])
        self.assertEqual(result["map"]["center"]["latitude"], 45.27)
        self.assertEqual(result["standard_receive_mhz"]["adsb"], 1090.0)
        self.assertFalse(result["applies_changes"])

    def test_override_map_center(self):
        result = region.map_view_suggestion(45, -66, {"latitude": 44.65, "longitude": -63.57})
        self.assertEqual(result["center"]["longitude"], -63.57)
    def test_station_region(self):
        chosen = {"port": {"name": "Sample Port", "latitude": 45.25, "longitude": -66.06}}
        result = region.build_station_region(45.27, -66.05, chosen)
        self.assertEqual(result["selected_facilities"]["port"]["name"], "Sample Port")
        self.assertEqual(result["map"]["center"]["latitude"], 45.27)
        self.assertNotIn("airport", result["selected_facilities"])

    def test_station_region_rejects_bad_facility(self):
        with self.assertRaises(ValueError):
            region.build_station_region(45.27, -66.05, {"port": {"name": "", "latitude": 45, "longitude": -66}})
if __name__ == "__main__":
    unittest.main()