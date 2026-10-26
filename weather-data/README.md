# Read-only deployment weather data

This directory is tracked in Git and read by `api/index.py` from the Vercel
Python deployment package. It contains verified GeoNames city records,
checksummed same-day Open-Meteo temperature forecasts and checksummed compressed
ERA5 historical months. Sources: [Open-Meteo](https://open-meteo.com/)
([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)); city metadata from
GeoNames through Open-Meteo. Original acquisition times remain in each object.
No credentials, personal trips, generated advice, usage ledgers or locks belong here.

First ten-city forecast batch prepared 2026-10-22: Berlin, Munich, Hamburg,
Frankfurt am Main, Cologne, Dresden, Heidelberg, Nuremberg, Düsseldorf and Leipzig.
All ten contain same-day Open-Meteo forecasts; Berlin/Munich retain their complete
historical windows (20 validated monthly objects, unchanged).
Forecasts expire at German midnight;
complete five-year history may remain usable. History is a packing reference,
never a prediction of specific future weather. Cities without a current forecast
or complete historical coverage show
“数据暂缺” until manually prepared.

Manual update commands are in [web/README.md](../web/README.md#git-weather-bundle).
Once Git auto-deployment is active, a separately authorized merge to `main` triggers a Production build automatically; Preview remains manual. A running deployment never
refreshes or writes data. Roll back by deploying the prior reviewed Git revision
(subject to the same date/coverage validation).

Production now selects this Git path before legacy readers and rejects old
P1/Preview namespace configuration collisions. No automatic refresh, duty roster
or midnight release is introduced. Correct historical/unavailable fallback does
not prove first-launch freshness: all ten real same-day forecasts must pass the
[final directory checks](../web/README.md#issue-38-publication-checks).
The 2026-10-22 batch above is a dated acquisition record, not a claim of current
forecast validity. City attribution: [GeoNames](https://www.geonames.org/).


## Forecast-only automation (#79; disabled until separately authorized)

The twice-daily Git updater is documented in [web/README.md](../web/README.md#git-forecast-data-pr-automation-79).
It acquires a fresh complete ten-city batch per slot, preserves every existing
history path and raw byte, and only proposes `weather-data/forecast/**` changes
in one bot data PR. It never repairs history, merges or deploys. Corrupt history,
city-manifest drift, partial/expired sources or newer existing acquisition times
stop publication. The fixed city-manifest hash is reviewed implementation policy;
metadata edits require separate trust-anchor review, even if only formatting.

Data PR review must revalidate P1/P2 and history against the then-current exact
main/head; a base or head change invalidates older evidence. Each merge and its
possible automatic Production deployment needs explicit authorization. Default-off
workflow code and offline fixtures do not establish live weather completeness,
free quota, PR permissions, enabled scheduling or deployed freshness. Original
source attribution and historical acquisition records above remain in force.
