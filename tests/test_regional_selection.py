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


if __name__ == "__main__":
    unittest.main()