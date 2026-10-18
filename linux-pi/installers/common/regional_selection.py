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



def map_view_suggestion(latitude: float, longitude: float, selection: dict | None = None) -> dict:
    """Preview map centering only; does not modify a running web console."""
    latitude, longitude = validate_coordinate(latitude, longitude)
    if selection:
        latitude, longitude = validate_coordinate(selection["latitude"], selection["longitude"])
    return {"center": {"latitude": latitude, "longitude": longitude}, "zoom": 10}


# Internationally common receive frequencies; not location-specific voice presets.
STANDARD_RECEIVE_MHZ = {"ais_a": 161.975, "ais_b": 162.025, "adsb": 1090.0}


def regional_preview(latitude: float, longitude: float, catalog: list[dict]) -> dict:
    """Suggest map location and candidate facilities without controlling a receiver."""
    latitude, longitude = validate_coordinate(latitude, longitude)
    return {
        "map": map_view_suggestion(latitude, longitude),
        "nearby_ports": suggest(latitude, longitude, catalog, "port"),
        "nearby_airports": suggest(latitude, longitude, catalog, "airport"),
        "standard_receive_mhz": dict(STANDARD_RECEIVE_MHZ),
        "applies_changes": False,
    }

def build_station_region(latitude: float, longitude: float, selections: dict) -> dict:
    """Create a data-only station region suitable for a config preview."""
    lat, lon = validate_coordinate(latitude, longitude)
    if not isinstance(selections, dict):
        raise ValueError("Selections must be a dictionary")
    result = {"map": map_view_suggestion(lat, lon), "selected_facilities": {}}
    for category in ("port", "airport"):
        facility = selections.get(category)
        if facility is None:
            continue
        if not isinstance(facility, dict):
            raise ValueError("Facility must be an object")
        fac_lat, fac_lon = validate_coordinate(facility["latitude"], facility["longitude"])
        name = facility["name"]
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Facility needs a name")
        result["selected_facilities"][category] = {
            "name": name,
            "latitude": fac_lat,
            "longitude": fac_lon,
        }
    return result


def build_spatial_index(catalog: list[dict], cell_degrees: int = 2) -> dict:
    """Pre-bucket facilities for repeated queries (in-memory only)."""
    if cell_degrees < 1 or cell_degrees > 30:
        raise ValueError("Cell size outside supported range")
    cells = {}
    for item in catalog:
        lat, lon = validate_coordinate(item["latitude"], item["longitude"])
        key = (math.floor(lat / cell_degrees), math.floor(lon / cell_degrees))
        cells.setdefault(key, []).append(item)
    return {"cell_degrees": cell_degrees, "cells": cells}


def suggest_indexed(latitude: float, longitude: float, index: dict,
                    category: str, limit: int = 5, radius_km: float = 250) -> list[dict]:
    """Exact distance ranking after a conservative latitude/longitude prefilter."""
    lat, lon = validate_coordinate(latitude, longitude)
    if not 0 < radius_km <= 1000:
        raise ValueError("Radius must be between 0 and 1000 km")
    degrees = index["cell_degrees"]
    lat_delta = min(180.0, radius_km / 110.5 + 0.1)
    latitude_end = min(90.0, abs(lat) + lat_delta)
    cos_bound = math.cos(math.radians(latitude_end))
    lon_delta = 180.0 if cos_bound < 0.001 else min(180.0, radius_km / (110.5 * cos_bound) + 0.1)
    candidate = []
    start_lat = math.floor(max(-90, lat - lat_delta) / degrees)
    end_lat = math.floor(min(90, lat + lat_delta) / degrees)
    start_lon = math.floor(-180 / degrees)
    end_lon = math.floor(180 / degrees)
    lon_ranges = []
    if lon_delta >= 180:
        lon_ranges = [(start_lon, end_lon)]
    else:
        low, high = lon - lon_delta, lon + lon_delta
        for shift in (-360, 0, 360):
            left = max(-180, low + shift)
            right = min(180, high + shift)
            if left <= right:
                lon_ranges.append((math.floor(left / degrees), math.floor(right / degrees)))
    visited = set()
    for a in range(start_lat, end_lat + 1):
        for left, right in lon_ranges:
            for b in range(left, right + 1):
                if (a, b) not in visited:
                    candidate.extend(index["cells"].get((a, b), ()))
                    visited.add((a, b))
    return suggest(lat, lon, candidate, category, limit, radius_km)

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