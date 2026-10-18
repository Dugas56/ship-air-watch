"""Offline regional facility suggestions for opt-in Shipwatch station setup.

No IP geolocation, network requests, or automatic radio retuning.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def validate_coordinate(latitude: float, longitude: float) -> tuple[float, float]:
    latitude, longitude = float(latitude), float(longitude)
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        raise ValueError("Coordinates must be finite")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Coordinates out of range")
    return latitude, longitude


def distance_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    a_lat, a_lon = validate_coordinate(a_lat, a_lon)
    b_lat, b_lon = validate_coordinate(b_lat, b_lon)
    radius = 6371.0088
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lon - a_lon)
    s = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(min(1, math.sqrt(s)))


def suggest(latitude: float, longitude: float, catalog: list[dict],
            category: str, limit: int = 5, radius_km: float = 250) -> list[dict]:
    validate_coordinate(latitude, longitude)
    if category not in ("port", "airport"):
        raise ValueError("Invalid category")
    if limit < 1 or radius_km <= 0:
        raise ValueError("Invalid limit or radius")
    found = []
    for item in catalog:
        if item.get("category") != category:
            continue
        km = distance_km(latitude, longitude, item["latitude"], item["longitude"])
        if km <= radius_km:
            found.append({**item, "distance_km": round(km, 1)})
    return sorted(found, key=lambda v: (v["distance_km"], v["name"]))[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description="Local-only suggestions. Coordinates must be supplied explicitly.")
    parser.add_argument("--latitude", type=float, required=True)
    parser.add_argument("--longitude", type=float, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--radius-km", type=float, default=250)
    args = parser.parse_args()
    lat, lon = validate_coordinate(args.latitude, args.longitude)
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    for category in ("port", "airport"):
        print(category.upper())
        for item in suggest(lat, lon, catalog, category, radius_km=args.radius_km):
            print(f"  {item['name']} ({item['distance_km']} km)")
    print("RESULT: suggestions only; no tuner, map, or service configuration changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())