# Local Phase 2A web UI

Python 3.9+ with `Europe/Berlin` zone data; standard library only:

```sh
python3 -m web.server
# http://127.0.0.1:8000
```

Personal trips now use real Open-Meteo temperature forecasts and server-resolved German GeoNames locations. Choose dates wholly within Germany-today…today+13 and cold/normal/hot sensitivity. Chinese names for the existing cities remain available; other German places use their provider names and federal states. A numeric location ID in a shared URL is resolved through Open-Meteo `/v1/get`; client coordinates are rejected. Search results are filtered to German populated places. Individually incomplete/invalid candidates are skipped; usable matches retain their verified state and coordinates. A nonempty response with no usable candidate returns 503, while a genuinely empty search returns an empty list. Direct ID resolution still rejects incomplete metadata. Requests go to fixed provider URLs with an eight-second timeout per call and no automatic retries. No trip URLs, headers or provider errors are logged.

This is a loopback-only local development server, not a production server. No deployment, accounts, storage service, new dependencies or scheduler is included. Closing the process stops it.

## Live and demo boundaries

- **Personal trip, default:** live temperature-only data. `weather_fetched_at` is when this process received the weather response; `advice_generated_at` is when it computed this recommendation. Neither is a provider model update time. The UI and copied advice identify live results and attribute Open-Meteo / GeoNames.
- **Featured cities:** always explicitly simulated, including their independent result pages. Cards never imply a live shared snapshot. They keep their own Germany-today…today+13 dates and normal sensitivity, without reading or changing the personal form.
- **15–30-day live trips:** return 503 with a clear Phase 2B deferral and no clothing result. The live date controls end at +13; direct later URLs also fail clearly. Historical fixture examples remain available only through the explicit demo path.
- **Demo control:** expand 模拟状态测试 and check 个人行程使用演示数据, or select a fixture scenario. Uncheck to restore live personal queries. `fixture=default|stable|colder|warmer|split|loading|stale|unavailable` explicitly selects authored API fixtures. Fixture weather acquisition time is null. Fixture overrides are never included in share links; ordinary live mode reopens personal links against real data. A demo result never claims to be real weather.
- **Phase 1 regression mode:** `python3 -m web.server --fixtures --port 8001` explicitly disables live advice/search for the existing offline browser suite. The response still identifies itself as a fixture even if the client asks otherwise. Do not use this runner to test provider integration.

Loading, stale and unavailable states hide clothing results. Stale presentation retains the trip dates and acquisition time. Browser history retains form values only within that entry; no cookies, local storage, server sessions or analytics are added. Independent trip and city share URLs remain unchanged. The additional read-only `/api/city?city_id=` route resolves non-featured direct-link locations for return-to-form editing.

## Computation and coverage

`live.py` reuses `level()` from the existing clothing experiment without changing CLI behavior or parsing its stdout. It requests only hourly `temperature_2m`, Celsius, `forecast_days=14`, `timezone=Europe/Berlin`, `timeformat=unixtime`. Each epoch is converted through `ZoneInfo`, rather than applying the provider's single fixed offset over a DST change.

The adapter validates timezone, Celsius units, original strictly consecutive hourly order, finite numeric temperatures, current Germany start date, and every required future 06–22 hour throughout the 14-day window (daytime 09–18; morning 06–08/evening 19–22). Missing, duplicate, reordered, null, stale or error data is refused. Elapsed hours today are excluded. A trip containing only this evening can receive an evening-only answer with no daytime temperature/indicator; after the final usable hour, a today-only query is unavailable.

Each day's remaining daytime median feeds the six-level model. A majority observed level can be the main indicator; a meaningful split without a majority returns null, rather than inventing the median's unobserved level. Its headline, variation notice/summary and inner-layer advice cover the actual coldest observed clothing requirement, with lighter options for warmer days; a null indicator never means winter layers may be omitted. Independent variation detection considers level changes and temperature differences greater than the existing candidate 1.5°C noise tolerance. The 13°C ±0.75°C outerwear copy tolerance remains. These are experimental clothing heuristics, not validated thermal-comfort guarantees. Reminders name a supported colder/warmer date and the layer to add/remove. Early/evening layers are compared with that same day's daytime conditions to avoid repeating a cross-day change. Day 8–14 uncertainty appears separately. Sensitivity changes clothing copy, not weather samples or the weather version.

A bounded, process-local dictionary reuses at most 32 city/Germany-date weather responses; a lock prevents duplicate forecast fetches within this single process. Acquisition time stays attached to the reused weather, while effective hours and advice are recalculated. Cross-midnight acquisition/calculation is rejected, and tomorrow uses a new key. This is a local development optimization, not a shared or persistent cache. City resolution still verifies the provider ID per advice request.

Examples with injected complete hourly data:

| Daytime temperatures | Main level | Packing reminder |
| --- | --- | --- |
| 24, 14, 24°C | 2 | Middle date colder; pack an appropriate outerwear layer |
| 14, 24, 14°C | 4 | Middle date warmer; light inner layer and removable coat |
| Seven 24°C + seven 14°C days | null | Both ranges need coverage; no fabricated 19°C representative |
| Stable 14°C or 12.9/13.1/13.2°C | observed level | No extra variation notice for boundary noise |

Result JSON keeps `city,start,end,preference,mode,headline,layers,notices,reference_temperature_c,warmth_indicator_level,packing_variation_notice,packing_variation_summary,weather_fetched_at,advice_generated_at,source,data_status,data_version,caveat`. Nulls are explicit. Both variation fields come from the same service decision. The UI never computes temperatures or levels; `WarmthIndicator` remains replaceable. Featured cards continue using their authored fixture contract until Phase 2C.

## Verification

```sh
python3 -m unittest discover -s tests/web -v
python3 -m unittest discover -s experiments/clothing-rules -q
# Start --fixtures --port 8001 separately, then use existing optional Playwright/Chrome:
UI_BASE_URL=http://127.0.0.1:8001 node tests/web/browser.cjs --check-only
UI_BASE_URL=http://127.0.0.1:8001 node tests/web/featured-regressions.cjs
# Review #5545508096: full service JSON with offline provider, rendered in browser:
UI_BASE_URL=http://127.0.0.1:8001 node tests/web/review-regressions.cjs
```

For deterministic full live-path browser testing, start the injected provider (no external weather network):

```sh
python3 -c "import sys; sys.path.insert(0,'tests/web'); from test_live import Fake, NOW; from web.live import Service; from web.server import Handler, ThreadingHTTPServer; Handler.service=Service(Fake(),lambda:NOW); ThreadingHTTPServer(('127.0.0.1',8002),Handler).serve_forever()"
node tests/web/live-browser.cjs
```

The test writes `docs/verification/phase2a/live-injected-mobile.png`. The screenshot's live-path labels are exercised with **injected synthetic weather**, not a captured real forecast. Test dependencies remain optional and ignored in `.local-tools/`; see the original [Phase 1 record](../docs/verification/phase1/README.md).

Optional public Berlin provider smoke test (requires network; no personal data needed):

```sh
python3 - <<'PY'
from datetime import datetime, timedelta
from web.live import Service, BERLIN
now = datetime.now(BERLIN).date()
d = Service().advice(dict(view='trip', city_id='berlin',
    start=(now+timedelta(days=1)).isoformat(),
    end=(now+timedelta(days=3)).isoformat(), preference='normal'))
print({k:d[k] for k in ('mode','headline','weather_fetched_at','advice_generated_at','data_status')})
PY
```

See [Phase 2A results](../docs/verification/phase2a/README.md) for actual runs and limits.

## Deferred work and provider references

Phase **2B**: eight-year temperature-only historical reference for trips ending after +13 and within +29. Existing CLI history remains an experiment, not a live web fallback. Phase **2C**: featured-city daily prefetch, shared cache/snapshots, budgets and scheduling. This PR adds none of those production facilities or deployment machinery.

Provider contract checked 2026-10-16 against official [forecast documentation](https://open-meteo.com/en/docs) (`timeformat`, DST-aware conversion, `forecast_days`) and [geocoding documentation](https://open-meteo.com/en/docs/geocoding-api) (`countryCode`, GeoNames IDs and `/v1/get`). These establish API behavior, not clothing accuracy. The narrower Issue #19 local scope takes precedence over the target spec's later historical, shared-cache and deployment goals.
