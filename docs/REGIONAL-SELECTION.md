# Regional facility selection — initial RC3 module

The `linux-pi/installers/common/regional_selection.py` module ranks **nearby
ports and airports** by great-circle distance from coordinates explicitly
provided by the user. It makes **no network requests**, does not infer an IP
address, and does not retune SDRs, change maps, or write configuration.

Example using a facility catalog you supply (a JSON array containing
`name`, `category` [`port` or `airport`], `latitude`, and `longitude`):

```shell
python linux-pi/installers/common/regional_selection.py --latitude 45.27 --longitude -66.06 --catalog YOUR_FACILITIES.json
```

**Limitations:** There is no bundled comprehensive global port/airport catalog
yet. Results depend on your catalog accuracy and coverage; an empty result does
not imply no facility exists. The installer is **not yet wired to these
suggestions**. This is the tested selection engine, not finished automatic setup.

AIS reception normally uses 161.975/162.025 MHz and ADS-B commonly 1090 MHz;
local facility selection must not override these receiver frequencies.
## RC3 wizard integration (early preview)

The interactive setup wizard now offers an **optional**, default-No question
for selecting nearby facilities. It needs a valid latitude/longitude already
entered by the operator, and reads a **small bundled demonstration catalog**
or a JSON catalog chosen by the user. This bundled catalog covers only Saint
John and Halifax; it is **not** a global airport/port database.

It records chosen facility suggestions in the configuration preview and does
not select radio frequencies, control receivers, or change the running Pi.
An expanded, licensed/verified facility catalog and real end-to-end wizard
validation remain required before claiming automatic regional setup.

## Offline browser preview

The new \`web-console/regional-preview.html\` page accepts a locally selected
setup JSON configuration with \`station.region_preview\` and displays map centre,
selected port and airport. It processes the file within the browser; there is no
upload, no external map tile request, and no connection to a running receiver.
This is deliberately a standalone **read-only** preview, not the integrated
marine/aircraft tracking map yet.

## Expanded global airport catalog

The bundled \`regional_facilities.json\` catalog now includes airport entries
imported from **OurAirports** (https://ourairports.com/data/), which publishes
its airport dataset in the public domain (provided without an accuracy
guarantee). The snapshot was downloaded on 2026-10-18. The importer is
\`linux-pi/installers/common/import_ourairports.py\`, which takes a locally
downloaded \`airports.csv\` file; it does **not** make network requests.

The import covers OurAirports large, medium and small airports. Heliports,
seaplane bases, closed facilities, and balloon ports are excluded. A small
set of curated port examples remains: **this is not a complete global
seaport catalog**. Verify facilities and regional VHF frequencies before use.
The installer still needs manual station coordinates and explicit opt-in.

## Performance prototype

\`build_spatial_index\` and \`suggest_indexed\` provide an optional in-memory
grid-based facility lookup. It reduces the number of distance calculations for
repeated regional searches, including locations near the date line.
Use \`python tests/benchmark_regional_selection.py\` to compare results
against exhaustive search on the bundled global airport catalog.
The interactive wizard still uses the simple exhaustive lookup for now.
