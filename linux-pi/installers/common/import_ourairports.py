"""Import OurAirports CSV into the regional catalog, preserving curated ports.

Source data: https://ourairports.com/data/ (public domain).
Run manually; this script makes no network request and never configures receivers.
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path

TYPES = {"large_airport", "medium_airport", "small_airport"}
def build(csv_path: Path, catalog_path: Path) -> tuple[int,int]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    existing_ports = [x for x in catalog if x.get("category") == "port"]
    airports = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            if row["type"] not in TYPES:
                continue
            try:
                latitude, longitude = float(row["latitude_deg"]), float(row["longitude_deg"])
            except (TypeError, ValueError):
                continue
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                continue
            code = row.get("ident", "").strip()
            name = row.get("name", "").strip()
            if not code or not name:
                continue
            airports[code] = {
                "name": f"{name} ({code})",
                "category": "airport",
                "latitude": latitude,
                "longitude": longitude,
                "country": row.get("iso_country", ""),
                "source": "OurAirports",
            }
    result = existing_ports + sorted(airports.values(), key=lambda x: x["name"])
    catalog_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(existing_ports), len(airports)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("catalog", type=Path)
    args = parser.parse_args()
    ports, airports = build(args.csv, args.catalog)
    print(f"PASS: CURATED_PORTS={ports} AIRPORTS_IMPORTED={airports}")