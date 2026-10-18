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