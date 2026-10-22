# Read-only deployment weather data

This directory is tracked in Git and read by `api/index.py` from the Vercel
Python deployment package. It contains verified GeoNames city records,
checksummed same-day Open-Meteo temperature forecasts and checksummed compressed
ERA5 historical months. Sources: [Open-Meteo](https://open-meteo.com/)
([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)); city metadata from
GeoNames through Open-Meteo. Original acquisition times remain in each object.
No credentials, personal trips, generated advice, usage ledgers or locks belong here.

Initial sample prepared 2026-10-22: Berlin forecast, Berlin/Munich complete
historical windows, no Hamburg weather. Forecasts expire at German midnight;
complete five-year history may remain usable. History is a packing reference,
never a prediction of specific future weather. Other cities remain visible with
“数据暂缺” until manually prepared.

Manual update commands are in [web/README.md](../web/README.md#git-weather-bundle).
A Git update needs a new deployment to reach Preview; a running deployment never
refreshes or writes data. Roll back by deploying the prior reviewed Git revision
(subject to the same date/coverage validation).
