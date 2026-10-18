"""Compare indexed versus exhaustive search against bundled catalog."""
import importlib.util
import json
from pathlib import Path
from time import perf_counter

folder=Path(__file__).resolve().parents[1]/"linux-pi"/"installers"/"common"
spec=importlib.util.spec_from_file_location("region", folder/"regional_selection.py")
region=importlib.util.module_from_spec(spec)
spec.loader.exec_module(region)
catalog=json.loads((folder/"regional_facilities.json").read_text(encoding="utf-8"))
start=perf_counter()
index=region.build_spatial_index(catalog)
build_ms=(perf_counter()-start)*1000
locations=[(45.27,-66.06),(49.2,-123.2),(51.5,-0.12),(-33.9,151.2),(35.7,139.7),(0,179.9),(89.1,3.3)]
linear_ms=0
indexed_ms=0
for lat,lon in locations:
    a=perf_counter()
    linear=region.suggest(lat,lon,catalog,"airport")
    linear_ms+=(perf_counter()-a)*1000
    a=perf_counter()
    fast=region.suggest_indexed(lat,lon,index,"airport")
    indexed_ms+=(perf_counter()-a)*1000
    if linear!=fast:
        raise AssertionError(f"Mismatch at {lat},{lon}")
print(f"PASS: FACILITIES={len(catalog)} QUERIES={len(locations)} RESULTS_MATCH")
print(f"RESULT: INDEX_BUILD_MS={build_ms:.1f}")
print(f"RESULT: LINEAR_QUERY_TOTAL_MS={linear_ms:.1f}")
print(f"RESULT: INDEXED_QUERY_TOTAL_MS={indexed_ms:.1f}")