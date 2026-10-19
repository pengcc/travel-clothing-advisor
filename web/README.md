# Local Python web UI — Phases 2A–2C

Python 3.9+ with `Europe/Berlin` zone data; standard library only:

From the repository root:

```sh
make dev    # Prepare today's featured forecast when configured, then serve http://127.0.0.1:8000
make check-dev # Optional read-only data readiness diagnostic (may exit 1)
make test   # Existing offline web unittest suite; no provider requests
make demo   # Fixture advice/search/featured; /api/city may use GeoNames
```

`make dev` attaches **both** `.history-local` and `.forecast-local` without
requiring prepared data. If `.forecast-local/cities.json` exists (or the matching
`FORECAST_DIR/cities.json` override), it first runs the existing bounded
`web.prefetch_forecasts` worker once: today's valid sources are cache hits with
**zero provider downloads**, while missing/stale/incomplete sources may trigger
real Open-Meteo requests and update the local forecast cache/usage ledger.
This local auto-prepare action is intentional; it does not fetch history or
initialize city metadata. Keep the cities file as a trusted operator-provided
list of exactly ten real GeoNames records (Phase 2C below). If it is missing
or prefetch fails, `make dev` warns and still starts; unavailable featured
data remains an explicit 503 without fixture defaults. Missing local directories
are created by the existing development store adapter. Empty or stale caches
do not prevent `/` and `/api/context` from loading. No fake publication, quota
reset, uncontrolled retry, scheduler or hosted operation is added.
Before listening, explicitly configured stores are checked for directory listing
and traversal access. Invalid paths (for example, a file instead of a directory),
denied directory creation, inaccessible existing directories and other actual
startup configuration errors fail explicitly. This is an access check, not a
weather completeness check.
Existing valid cache objects and quota counts are reused.

`make check-dev` separately checks directory access, history block presence and
the complete Germany-today featured forecast publication. It exits nonzero for
unprepared data, but is not a prerequisite of `make dev`. This diagnostic is
read-only: it creates no directories, locks or ledgers and calls no providers.
Its observations can change before the server reads the data.

History block presence does **not** certify validity or coverage for a specific
city/trip. Use the existing read-only exact-trip check described below:

```sh
python3 -m web.prefetch_history --check --city-id berlin --store .history-local \
  --cities-file .history-local/cities.json --start YYYY-MM-DD --end YYYY-MM-DD
```

Replace `berlin` with the chosen supported city alias and use the same city,
verified manifest, history store and exact dates as the serving environment.
Without `--city-id`, the command checks **every city in the manifest**; missing
Hamburg months can then fail a check even when Berlin's trip is complete.

`make demo` needs no cache directories. Its `/api/advice`, `/api/cities` search
and `/api/featured` routes use authored fixtures without provider requests;
`/api/context` also works without a provider. This is **not full offline
isolation**: `/api/city?city_id=...` still resolves via live GeoNames, including
when a shared trip link needs a city absent from client state. Such a link can
make a provider request or fail when offline. For offline demonstrations, stay
within fixture advice/search/featured flows rather than opening those links.
Full offline city resolution is a separate server change requiring authorization,
tracked as follow-up to [review #5561695127](https://github.com/pengcc/travel-clothing-advisor/pull/45#pullrequestreview-5561695127);
Issue #43 does not change `web/server.py` or this route's behavior.

Local `make dev` performs **one** bounded attempt to prepare today's featured
snapshot when a valid cities manifest is present; it never retries continuously,
and a server already running past Germany midnight will **not** refresh by itself.
The standalone manual worker remains available (Phase 2C). Reliable daily
scheduling, automatic failure recovery and hosted persistence remain Issue #42
PR-B/PR-D work, not delivered by this local Makefile shortcut. History preparation
also remains a separate explicit operator action. Successful server startup is
not proof that featured or historical data is ready. Live personal queries retain
their existing provider calls and cache behavior.

Optional overrides: `make dev PORT=8001 HISTORY_DIR=.history-local
FORECAST_DIR=.forecast-local PYTHON=python3`. `make check-dev` runs only the
read-only diagnostic. Stop a running server with Ctrl-C. If you intentionally need
to run without one of the stores, the existing direct CLI remains supported:

```sh
python3 -m web.server
python3 -m web.server --history-dir .history-local --forecast-dir .forecast-local --port 8000
```

Personal trips now use real Open-Meteo temperature forecasts and server-resolved German GeoNames locations. Choose dates wholly within Germany-today…today+13 and cold/normal/hot sensitivity. Chinese names for the existing cities remain available; other German places use their provider names and federal states. A numeric location ID in a shared URL is resolved through Open-Meteo `/v1/get`; client coordinates are rejected. Search results are filtered to German populated places. Individually incomplete/invalid candidates are skipped; usable matches retain their verified state and coordinates. A nonempty response with no usable candidate returns 503, while a genuinely empty search returns an empty list. Direct ID resolution still rejects incomplete metadata. Requests go to fixed provider URLs with an eight-second timeout per call and no automatic retries. No trip URLs, headers or provider errors are logged.

This is a loopback-only local development server, not a production server. No deployment, accounts, storage service, new dependencies or scheduler is included. Closing the process stops it.

## Live and demo boundaries

- **Personal trip, default:** live temperature-only data. `weather_fetched_at` is when this process received the weather response; `advice_generated_at` is when it computed this recommendation. Neither is a provider model update time. The UI and copied advice identify live results and attribute Open-Meteo / GeoNames.
- **Featured cities, default:** real advice derived from a complete daily forecast publication (see Phase 2C below). Missing, corrupt or yesterday-only publications return 503; no fixtures are substituted. Cards and independent city views keep their own Germany-today…today+13 dates and normal sensitivity without reading or changing the personal form. Browsing makes zero provider calls.
- **15–30-day personal trips:** use the five-year local history library when configured and complete; otherwise return 503 without clothing defaults. The form accepts the full 30-day window. Historical fixture examples remain explicitly simulated. See Phase 2B below.
- **Demo control:** expand 模拟状态测试 and check 使用演示数据, or select a fixture scenario. Uncheck to restore live personal queries. `fixture=default|stable|colder|warmer|split|loading|stale|unavailable` explicitly selects authored API fixtures. Fixture weather acquisition time is null. Fixture overrides are never included in share links; ordinary live mode reopens personal links against real data. A demo result never claims to be real weather.
- **Phase 1 regression mode:** `python3 -m web.server --fixtures --port 8001` explicitly disables live advice/search for the existing offline browser suite. The response still identifies itself as a fixture even if the client asks otherwise. The `/api/city` exception described above still applies; this flag does not block all provider access. Do not use this runner to test provider integration.

Loading, stale and unavailable states hide clothing results. Stale presentation retains the trip dates and acquisition time. Browser history retains form values only within that entry; no cookies, local storage, server sessions or analytics are added. Independent trip and city share URLs remain unchanged. The additional read-only `/api/city?city_id=` route resolves non-featured direct-link locations for return-to-form editing.

## Computation and coverage

`live.py` reuses `level()` from the existing clothing experiment without changing CLI behavior or parsing its stdout. It requests only hourly `temperature_2m`, Celsius, `forecast_days=14`, `timezone=Europe/Berlin`, `timeformat=unixtime`. Each epoch is converted through `ZoneInfo`, rather than applying the provider's single fixed offset over a DST change.

The adapter validates timezone, Celsius units, original strictly consecutive hourly order, finite numeric temperatures, current Germany start date, and every required future 06–22 hour throughout the 14-day window (daytime 09–18; morning 06–08/evening 19–22). Missing, duplicate, reordered, null, stale or error data is refused. Elapsed hours today are excluded. A trip containing only this evening can receive an evening-only answer with no daytime temperature/indicator; after the final usable hour, a today-only query is unavailable.

Each day's remaining daytime median feeds the six-level model. A majority observed level can be the main indicator; a meaningful split without a majority returns null, rather than inventing the median's unobserved level. Its headline, variation notice/summary and inner-layer advice cover the actual coldest observed clothing requirement, with lighter options for warmer days; a null indicator never means winter layers may be omitted. Independent variation detection considers level changes and temperature differences greater than the existing candidate 1.5°C noise tolerance. The 13°C ±0.75°C outerwear copy tolerance remains. These are experimental clothing heuristics, not validated thermal-comfort guarantees. Reminders name a supported colder/warmer date and the layer to add/remove. Early/evening layers are compared with that same day's daytime conditions to avoid repeating a cross-day change. Day 8–14 uncertainty appears separately. Sensitivity changes clothing copy, not weather samples or the weather version.

Phase 2C replaces the process dictionary with an injectable daily source store (memory by default; explicit local persistent directory for restart sharing). See the cache identity, admission and local-only limits below. City resolution still verifies the provider ID per personal advice request; those geocoding requests are counted separately from forecast calls.

Examples with injected complete hourly data:

| Daytime temperatures | Main level | Packing reminder |
| --- | --- | --- |
| 24, 14, 24°C | 2 | Middle date colder; pack an appropriate outerwear layer |
| 14, 24, 14°C | 4 | Middle date warmer; light inner layer and removable coat |
| Seven 24°C + seven 14°C days | null | Both ranges need coverage; no fabricated 19°C representative |
| Stable 14°C or 12.9/13.1/13.2°C | observed level | No extra variation notice for boundary noise |

Result JSON keeps `city,start,end,preference,mode,headline,layers,notices,reference_temperature_c,warmth_indicator_level,packing_variation_notice,packing_variation_summary,packing_variation_kind,weather_fetched_at,advice_generated_at,source,data_status,data_version,caveat`. Nulls are explicit. Both variation text fields come from the same service decision. `packing_variation_kind` is `cold`, `warm`, `mixed`, or `null` and is derived from those existing server-side packing events: it is `null` with no cross-day variation, and `mixed` for historical reference notices which explicitly cover both colder and warmer sample conditions. The client never parses Chinese text or treats this direction as a new warmth level. The UI never computes temperatures or levels; `WarmthIndicator` remains replaceable. Featured cards use the same backend rules; explicitly selected fixture cards keep their authored contract.

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
python3 tests/web/serve_forecasts.py
node tests/web/live-browser.cjs
```

The test writes three images under `docs/verification/phase2c/`. The screenshot's live-path labels are exercised with **injected synthetic weather**, not a captured real forecast. Test dependencies remain optional and ignored in `.local-tools/`; see the original [Phase 1 record](../docs/verification/phase1/README.md).

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

Phase **2C** implements local daily forecast preparation and shared sources; scheduling is deferred. Phase **2D** selects hosted storage and validates a separately authorized Preview. This change adds no production infrastructure or deployment machinery.

The Phase 2A provider contract was checked 2026-10-16 against official [forecast documentation](https://open-meteo.com/en/docs) and [geocoding documentation](https://open-meteo.com/en/docs/geocoding-api). These establish API behavior, not clothing accuracy.

## Phase 2B: local five-year ERA5 library

Personal trips ending after Germany-today+13 and by today+29 now use five complete analogous annual windows for the **entire** trip. The previous independent eight-year experimental CLI is unchanged. Phase 2C serves real cached featured-city references independently of this history library.

`history.py` provides `Library`, `Downloader`, `Store`, `MemoryStore` and `DirectoryStore`. The directory adapter is an explicit local-development library, **not production container storage**. Production needs a durable shared object adapter and reliable admission/quota coordination, deferred to Phase 2D. No vendor, infrastructure, credentials, scheduler or hosted store is configured here.

Start the read-only local web path with an already populated library:

```sh
python3 -m web.server --history-dir .history-local
```

The default server has no history library and returns a clear 503 for historical trips. With a library, missing/corrupt blocks or storage outages also return 503 without clothing defaults. Web requests never populate storage by default. The injectable `Service(history=..., history_downloader=..., history_max_missing=1)` permits strictly bounded admission for a resolved German city; if more than that number of blocks is missing it makes **zero** archive requests. A downloader requires its own equivalent-call and time budgets. A request still includes the existing geocoding call (8-second maximum) before historical admission (default 12-second worker maximum). Shared forecast caching and real featured snapshots are described under Phase 2C below.

### Explicit initialization and manual prefetch

The worker uses an operator-supplied JSON **list of GeoNames `/v1/get` city records** (`id,name,admin1,country_code,feature_code,latitude,longitude`); `location()` applies the same German populated-place metadata validation as the server. This is trusted local operator configuration, never client-submitted coordinates. To initialize all ten featured cities, prepare records for IDs `2950159,2867714,2911298,2925533,2886242,2935022,2907911,2861650,2934246,2879139` in `.history-local/cities.json`. Live geocoding/seeding is a separately authorized initialization step; this change does not perform it. Optional additional German city records may follow. Do not put credentials or user information in this file.

Offline planning (no provider requests):

```sh
python3 -m web.prefetch_history --cities-file .history-local/cities.json
python3 -m web.prefetch_history --cities-file .history-local/cities.json --full-years
```

**Only after separate approval for real downloads**, append `--download`. Each invocation fetches at most five missing month blocks by default, with a 30-equivalent-call batch, 60 daily, 600 monthly internal ceilings and a 30-second total network-work deadline. Use `--batch-calls`, `--daily-calls`, `--monthly-calls`, `--max-blocks`, `--timeout` to reduce/adjust limits. These ceilings deliberately leave room for forecasts/geocoding and do not represent the provider's account-wide usage. No retry loop runs. A bounded batch returns `status=paused` / exit 1 when work remains; rerun later to continue. Successful blocks survive interruptions. Never delete the usage ledger to evade quotas; a missing ledger on a restored/empty store does not recover prior account usage.

`plan()` computes the actual mapped months for **every** possible start in the next 30 local calendar days, including leap and cross-year ranges. It prioritizes these months across the supplied cities before optional full-year backfill. The supplied cities should include all ten featured IDs; the planner also supports a smaller initial subset without requiring all cities to finish before serving complete trips. Already valid blocks are revalidated and skipped. Corrupt blocks count as missing and can be repaired by the same bounded worker. Model/format/coordinates select a different namespace; they never silently reuse old blocks.

### Storage, validation and budgets

Each gzip JSON object is `history/era5/temp-v1/<GeoNames ID>/<coordinate SHA-256 prefix>/<YYYY-MM>.json.gz`. Its body contains the exact model/variable/unit/timezone/schema identity, requested coordinates, canonical continuous UTC hourly epochs and Celsius values, acquisition timestamp and source URL. An outer SHA-256 covers that entire body. Reads check identity, checksum, full-month UTC coverage, finite plausible temperature values, timezone, units and acquisition time. Compressed and expanded sizes are bounded. A manifest is the validated month object itself, avoiding a separate mutable index that could disagree with its payload. Missing objects are misses; IO outages fail closed. Month objects contain no trips, preferences, users, IPs or account data.

The archive request fixes `models=era5`, only `hourly=temperature_2m`, Celsius, `timezone=Europe/Berlin`, `timeformat=unixtime`. It pads the requested month by one date at each end because provider range boundaries use a fixed offset; normalization trims to the exact Berlin month using each UTC instant. DST months retain 23/25-hour days and both autumn folds. A conservative six-day publication guard and full validation reject incomplete recent months without substituting older years. No daily refresh or expiration is applied to valid historical blocks.

Window mapping anchors the **arrival year**, using years -1 through -5. Replace only the start's year (Feb 29 becomes Feb 28 in nonleap years), then add the original inclusive calendar duration. Never independently replace the end's year or collapse individual leap days. All five windows must be available before any answer is returned. Daytime medians (09–18) use the existing six-level rule/packing detector; morning 06–08 and evening 19–22 remain separate. Historical copy discards all dated forecast wording, covers winter outerwear/inner layers when supported, preserves the 13°C tolerance, and never assigns a historical cold day to a future trip date. Sensitivity affects clothing copy, not data identity.

Acquisition and recommendation time remain separate. `weather_fetched_at` is the **oldest contributing block acquisition**, not a claim of newly fetched weather; `history_fetched_at[]` lists distinct contributing acquisition times in chronological order. The UI explicitly labels these, identifies five-year reference, and attributes ERA5/Open-Meteo/GeoNames. `data_status=complete` means validated full historical coverage, not forecast freshness.

The downloader serializes calls (concurrency **1**, within the maximum 2). A nonblocking per-store lock admits one worker or reader at a time; concurrent requests fail quickly and cannot duplicate a block download. `DirectoryStore` uses a filesystem advisory lock and atomic `os.replace`; `MemoryStore` uses a thread lock for deterministic tests. All participating local processes must use the same directory. These mechanisms **do not implement distributed account-wide locking or quotas** across hosts, copied libraries or separately configured stores.

The control ledger atomically reserves daily/monthly equivalent-call usage **before** outbound IO. It persists failed attempts and cooldown across worker restarts; invalid ledgers stop fetching. The conservative internal estimate is `2 * ceil((days-in-month + 2 padded dates) / 14)` per HTTP request (six equivalent calls for each 28–31-day month), not a provider invoice or exact quota measurement. Worker output records HTTP attempts, equivalent calls, hits, publications and failures only. On 429/5xx, transport, validation or publication failure it stops immediately and persists a five-minute cooldown (longer numeric `Retry-After` is honored). Provider errors and headers are never printed. A provider injected for tests must honor its supplied remaining timeout; the real transport limits socket waits, response size and wall time. Optional live smoke/data seeding was **not run**.

Verified official contracts (2026-10-16): [Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) for ERA5, epoch/timezone handling and publication delay; [pricing and attribution](https://open-meteo.com/en/pricing) for weighted calls and [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Weather is transformed into experimental packing advice; this is not a validated comfort model. API noncommercial usage eligibility must be checked before release.

Additional offline checks:

```sh
python3 -m unittest discover -s tests/web -q
python3 -m unittest discover -s experiments/clothing-rules -q
# Against a loopback fixture server, all historical data is injected:
UI_BASE_URL=http://127.0.0.1:8001 node tests/web/history-browser.cjs
```


## Phase 2C: shared daily forecast sources (local only)

Issue #25 adds `web.forecasts.Cache`, using the existing `Store` protocol and atomic `MemoryStore` / `DirectoryStore` adapters. The in-memory default retains Phase 2A real personal queries; it does not imply durable sharing. Configure the **same explicit local directory** for the manual worker and all local web processes to reuse data across restarts:

```sh
python3 -m web.prefetch_forecasts --cities-file .forecast-local/cities.json --store-dir .forecast-local
python3 -m web.server --forecast-dir .forecast-local --history-dir .history-local
```

Omit `--history-dir` if no five-year library exists. Both directories are ignored. No production filesystem/shared-storage claim, hosted adapter, credentials, cron, HTTP refresh endpoint, deployment or live-data initialization is included. Phase 2D owns hosted persistence, distributed admission, protected scheduling and Preview validation.

### Operator invocation contract

Prepare a local JSON **list of actual Open-Meteo GeoNames `/v1/get` records**, retaining `id,name,admin1,country_code,feature_code,latitude,longitude`. Use the same validated provider-record boundary as history; do not invent coordinates or use the synthetic test records as real input. Exactly the ten existing featured IDs are required: `2950159,2867714,2911298,2925533,2886242,2935022,2907911,2861650,2934246,2879139`. No geocoding occurs in the command. Provisioning real metadata/downloads is a separate operator action, not performed by this PR. Keep input local/ignored and free of credentials and personal information.

The command prepares Germany-today only, serially, with at most **10 forecast attempts**, at most **4 seconds per network call**, a default **45-second total deadline** (`--timeout` may reduce it or increase it to at most 60), no automatic retries and a nonblocking per-store worker/reader lock. The real transport bounds both response bytes and wall time. A future daily scheduler should run this exact operator command with a persistent shared local directory on the same host, check exit status, and handle failure; this is a contract only, not scheduling configuration.

Success emits operational JSON and exits 0. Failure/admission/storage/date/validation/timeout emits counts with `status=unavailable, complete=false` and exits 1; no provider error payloads, records, trips or user inputs are logged. `forecast_attempts` counts attempted outbound calls; `hits` counts valid reused city sources; `published` counts source objects written, not complete featured blocks. `geocoding_attempts` is always zero for this command. Valid source objects survive partial failure. No featured manifest is published until all ten sources validate **and all ten advice results can be derived**. Recover after the five-minute failure cooldown by rerunning; completed cities are hits. A same-day complete rerun makes zero forecast requests. Other German cities need no featured publication: personal requests admit at most one missing forecast, with no retry.

A checksummed admission ledger reserves attempts **before** IO; failures remain charged. The conservative local ceiling is **42 forecast HTTP attempts per Germany day per store**, shared by the worker and personal misses, with a five-minute cooldown after failed fetch/validation/publication. This is an internal HTTP-attempt budget, not a provider equivalent-call measurement or account-wide quota. Geocoding retains its distinct 8-second timeout; on-demand weather has a 12-second service deadline with one at-most-4-second network call. Cached reads bypass download admission and cooldown. A corrupt ledger blocks downloads. Do not delete the ledger to evade limits. All local processes must use the same store; copied stores or other hosts do not share locks or usage. Admission failures return 503 without clothing defaults.

### Identity, publication and reads

Raw source keys include GeoNames ID, exact validated coordinates, request/model/format identity and Germany-local date:

`forecast/hourly-14d-v1/<GeoNames ID>/<identity SHA-256>/<YYYY-MM-DD>.json`

The checksummed object contains the raw provider response, exact identity, fixed source URL, and observed `weather_fetched_at`. Reads revalidate checksum, format/model, coordinates, acquisition day/time, Celsius units, strictly consecutive original UTC epochs, finite temperatures and **all 06–22 slots for all 14 days**, including elapsed hours today. Both DST folds survive UTC-instant parsing. The forecast explicitly requests `models=best_match`, one hourly Celsius temperature variable, `forecast_days=14`, `Europe/Berlin` and Unix instants. A version/coordinate change selects a different namespace; old objects are not silently accepted.

`forecast/featured-v1/<Germany date>.json` atomically names all ten validated source versions and verified city metadata. Every featured/card/detail read checks the whole manifest and all sources, derives advice through `Service.forecast_advice` with one calculation instant per response, and does **zero forecast or geocoding IO**. A missing/corrupt source or manifest, reader contention or storage outage returns 503. At local midnight only the new date's complete manifest is eligible. A failed refresh never advertises a partial block as complete. Individual atomic source publication plus the final manifest allow safe interruption and recovery.

Personal queries resolve a trusted city, read the same source, and recompute advice for their dates/preference and remaining hours; no per-user advice, trip, preference or user identifier is stored. Weather version/acquisition remain attached to the source while `advice_generated_at` reflects calculation, not model-update time. Cards and details use the same backend variation decision and nullable indicator/summary contract. As in Phase 2A, advice can change when elapsed hours are excluded even when its source version stays unchanged. Day 8–14 uncertainty and all historical garment rules remain unchanged.

Reproducible offline commands, counts, screenshots and evidence limits: [Phase 2C verification](../docs/verification/phase2c/README.md).


### Clothing-choice guidance

Forecast and historical results share `packing_copy.guidance` (`alternative`,
`personal_layer`, `trousers_shoes`) between the detailed page and clipboard export.
These are presentation choices from already selected levels/events and preference;
thresholds, dates, risk triggers, weather requests and caches are unchanged. L5 may
suggest an existing three-in-one plus fleece as a conditional replacement, suppressed
when L6 coverage is required. Trouser/footwear copy keeps rain, snow and ice conditional
on separately checked forecasts. Featured cards retain their short outerwear summaries.
Older/fixture responses keep their existing export fallback without invented guidance.

Offline regression commands (Chrome and local Playwright required for browser checks):

```sh
python3 tests/web/serve_forecasts.py --port 8002
# In another terminal:
node tests/web/copy-regressions.cjs
node tests/web/clipboard-regressions.cjs
UI_BASE_URL=http://127.0.0.1:8002 node tests/web/review-regressions.cjs
UI_BASE_URL=http://127.0.0.1:8002 node tests/web/history-browser.cjs
```

## Issue #36: historical operations runbook

This is preparation, not evidence that München can already answer a real trip.
Use the actual failing trip dates; the examples below are illustrative. No live
GeoNames requests, history downloads, deployment or storage migration were run
for this change. Existing local Berlin evidence is in
[Issue #34 verification](../docs/verification/issue34/README.md); deployment
configuration and coverage remain unverified.

1. Identify the **actual serving process/environment** and its `--history-dir`.
   The default `web.server` has `Service.history=None`. `--history-dir` attaches
   `Library(DirectoryStore(...))`; relative paths resolve from that process's
   working directory. `--forecast-dir` does not configure history. Use the same
   absolute history path for inspection, worker and server. Local `.history-local`
   repair does not populate a deployment. No hosted store is configured in this
   repository; an inaccessible remote store cannot be diagnosed by a local path.
   Do not start the server against a missing directory just to inspect it: its
   existing directory adapter creates directories and request lock files.

2. Obtain **separate approval** for city metadata requests and creation of a new
   ignored manifest in the chosen environment. Reuse existing verified records
   when available. After approval, for München only (one `/v1/get` request, no
   retries, existing eight-second per-request timeout):

   ```sh
   python3 -m web.prefetch_history --resolve-cities --city-id munich \
     --cities-file .history-local/munich-cities.json
   ```

   The parent directory must already exist and be approved for this operation.
   The output file must not exist. Omitting `--city-id` resolves all ten featured
   cities: Berlin 2950159, München 2867714, Hamburg 2911298, Frankfurt am Main
   2925533, Köln 2886242, Dresden 2935022, Heidelberg 2907911, Nürnberg 2861650,
   Düsseldorf 2934246, Leipzig 2879139 (at most ten requests; serial, no retries).
   To prioritize München in that initialization, pass `--city-id munich` first
   then repeat `--city-id` for each remaining alias. All records must pass the
   existing `location()` validation and requested-ID equality before publication.
   No coordinates are invented. The complete manifest is staged, flushed, synced
   and closed before atomic no-overwrite publication; write failures leave no
   partial destination and staging files are cleaned up. A destination created
   concurrently is preserved. A failed batch creates no manifest; requests
   already attempted still count. Keep provider records ignored and out of Git.
   Do not merge records by copying UI fixtures or manually supplying coordinates.

3. Run the **offline, read-only exact-trip report**, substituting the actual store
   path, verified manifest and dates. This command creates no directory, worker
   lock or ledger and makes no requests:

   ```sh
   python3 -m web.prefetch_history --check --city-id munich \
     --cities-file .history-local/munich-cities.json --store .history-local \
     --start 2026-11-02 --end 2026-11-05
   ```

   Exit 0 means all necessary blocks validate; exit 1 reports `incomplete`,
   `unreadable` or `unconfigured` (omit `--store` to represent a server with no
   history configured). Per-city months are `valid`, `missing_or_invalid`, or
   `unreadable`. Missing directories are unreadable, not empty coverage. Corrupt
   objects are misses by the existing `Library.read()` contract. Storage outages
   never prove absence. Reports observe atomic objects without locking; rerun
   after maintenance. Exact coordinates participate in identity, so the manifest
   must match server-resolved metadata. `--today` aggregate plans are not proof
   of a particular trip's coverage. Coverage alone does not validate the API's
   Germany-today…today+29 admission window.

4. Request **separate approval** naming cities, actual environment/store, dates,
   missing months and total equivalent-call estimate from the report. For the
   illustrative November trip with no München blocks: five November 2021–2025
   blocks, at most five archive HTTP attempts / 30 conservative equivalent calls.
   Ten entirely missing cities would require 50 blocks / 300 equivalent calls,
   over multiple approved batches and days under existing limits. Cross-month
   trips may need ten blocks per city; use the report rather than that example.
   Approval must also cover writes to the selected store and its quota ledger.
   After approval, use the **same exact dates** for bounded filling:

   ```sh
   python3 -m web.prefetch_history --city-id munich \
     --cities-file .history-local/munich-cities.json --store .history-local \
     --start 2026-11-02 --end 2026-11-05 --download \
     --max-blocks 5 --batch-calls 30 --daily-calls 60 --monthly-calls 600 --timeout 30
   ```

   This reuses the existing downloader, identity/checksum, six-day publication
   lag, ledger and admission lock. Hits are free; failures remain charged. Exit 1
   `paused` can mean partial progress, quota, cooldown or failure. Inspect counts,
   rerun the offline check, and continue only within the approved total budget;
   never delete the ledger or automatically loop. The ledger coordinates one
   store, not all stores/hosts or other use of the provider account.

5. Repeat step 3 as **read-back validation**. Require every mapped month valid.
   Then separately approve any needed server configuration/start or deployment
   change; attaching the store is not authorized by the data download approval.
   For an approved local serving environment, the existing launch is:

   ```sh
   python3 -m web.server --history-dir .history-local --port 8000
   ```

   After approval for the real API check (one additional city-resolution request,
   zero archive downloads in the default server), query the actual serving URL
   with dates currently accepted by `/api/context`, an end beyond `forecast_end`,
   no `fixture` parameter, and the same city/store/date coverage checked above:

   ```sh
   curl --fail --get http://127.0.0.1:8000/api/advice \
     --data-urlencode view=trip --data-urlencode city_id=munich \
     --data-urlencode start=2026-11-02 --data-urlencode end=2026-11-05 \
     --data-urlencode preference=normal
   ```

   Require HTTP 200, `mode=historical_reference`, `fixture=false`, correct city and
   dates, and five-year evidence in the response. Check acquisition/version
   fields against that environment's library. A 503 is not successful repair.
   Do not publish trip URLs or raw responses containing personal inputs. A
   successful synthetic test or merged PR is not this operational evidence.

Offline validation: `python3 -m unittest discover -s tests/web -q`. Focused tests
cover mocked GeoNames validation and ID mismatch, safe manifest publication,
read-only valid/corrupt/missing/unreadable/unconfigured stores, leap/cross-year
mapping, and exact-trip download job selection. Existing HTTP tests exercise
`/api/advice` with injected providers and a complete/incomplete history library.
