"""Import port-designated rows from locally supplied UN/LOCODE CSV extracts.

UN/LOCODE source and redistribution terms must be checked by the distributor.
Input must have columns Country, Location, Name, Function, Coordinates.
Function position 1 is the seaport indicator; blank coordinates are skipped.
No download, radio control, or live configuration occurs.
"""
from __future__ import annotations
import argparse
import csv
import json
import re
from pathlib import Path

POSITION = re.compile(r"^(\d{2})(\d{2})([NS])\s+(\d{3})(\d{2})([EW])$")


def parse_coordinates(raw: str) -> tuple[float, float]:
    match = POSITION.fullmatch(raw.strip().upper())
    if not match:
        raise ValueError("Invalid UN/LOCODE coordinates")
    lat_deg, lat_min, ns, lon_deg, lon_min, ew = match.groups()
    if int(lat_min) >= 60 or int(lon_min) >= 60:
        raise ValueError("Invalid coordinate minutes")
    lat = int(lat_deg) + int(lat_min) / 60
    lon = int(lon_deg) + int(lon_min) / 60
    if lat > 90 or lon > 180:
        raise ValueError("Invalid coordinate range")
    return (-lat if ns == "S" else lat), (-lon if ew == "W" else lon)


def import_ports(csv_path: Path, catalog_path: Path, output_path: Path) -> int:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    airports = [item for item in catalog if item.get("category") == "airport"]
    original_ports = [item for item in catalog if item.get("category") == "port"]
    ports = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        expected = {"Country", "Location", "Name", "Function", "Coordinates"}
        if not expected.issubset(reader.fieldnames or []):
            raise ValueError("Missing required UN/LOCODE CSV columns")
        for row in reader:
            function = (row.get("Function") or "").strip()
            if not function.startswith("1"):
                continue
            name = (row.get("Name") or "").strip()
            country = (row.get("Country") or "").strip()
            location = (row.get("Location") or "").strip()
            if not name or not country or not location:
                continue
            try:
                lat, lon = parse_coordinates(row.get("Coordinates") or "")
            except ValueError:
                continue
            key = f"{country}{location}"
            ports[key] = dict(name=f"{name} ({key})", category="port",
                              latitude=lat, longitude=lon, country=country,
                              source="UN/LOCODE", locode=key)
    # Preserve curated demo ports, but do not silently remove any airports.
    all_records = original_ports + sorted(ports.values(), key=lambda x: x["name"]) + airports
    output_path.write_text(json.dumps(all_records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(ports)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source_csv", type=Path)
    parser.add_argument("catalog_json", type=Path)
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args()
    count = import_ports(args.source_csv, args.catalog_json, args.output_json)
    print(f"PASS: IMPORTED_PORT_ROWS={count}; OUTPUT={args.output_json}")