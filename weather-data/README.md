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
A Git update needs a new deployment to reach Preview; a running deployment never
refreshes or writes data. Roll back by deploying the prior reviewed Git revision
(subject to the same date/coverage validation).
