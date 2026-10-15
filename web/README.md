# Phase 1 fixture web UI

Run from the repository root with Python 3.9+ (including `Europe/Berlin` zone data):

```sh
python3 -m web.server
# optional: python3 -m web.server --port 8001
```

Open http://127.0.0.1:8000. No runtime dependencies, weather calls, storage or accounts. The standard-library HTTP server binds only loopback and is a local development runner, not a production server or deployment choice. Stop with Ctrl-C.

## Journeys and fixtures

Personal trips select a controlled city, dates within Germany's current 30-calendar-day window, and cold/normal/hot sensitivity. The entire trip becomes historical-reference presentation when its end exceeds today +13. Featured cities always resolve their own today…today+13 window and normal sensitivity. Cards paginate 4/4/2. Search includes two extra cities to demonstrate a non-featured city and Frankfurt name disambiguation; this finite fixture catalog does not claim nationwide search coverage.

The collapsed **模拟状态测试** control switches authored responses for both pages. Default cards deliberately include stable, one colder day, one warmer day, and split-distribution fixtures. Stable = L4; colder = L2 → L4 → L2; warmer = L4 → L2 → L4; split = seven L2 days and seven L4 days with a null main indicator. These are authored examples, not calculated daily weather. Explicit colder/warmer fixtures require at least three trip days; split requires fourteen. Default short trips use the stable fixture instead of referring to a nonexistent second day. Historical-reference dates always use historical copy without invented future cold/warm dates.

Loading, unavailable, stale and invalid-input states show no clothing recommendation. Select `持续加载` to keep the loading panel visible, then change the fixture to recover. Invalid dates and unknown city IDs can be tested through direct links or form input. Weather acquisition time is null and shown as **未获取**. The timestamp is only the time the simulated response was assembled. `data_status=fresh` means the fixture response is available, never that live weather is fresh. The stale fixture is refused rather than represented as current weather.

Form values live only in the page and that browser history entry (`history.state`) so returning/reloading the tab retains the form. No cookies, local/session storage, server sessions or analytics. Share links contain only the specified query parameters and never contain fixture overrides. They reopen simulated results, not saved weather conclusions.

## Structure and Phase 2 handoff

- `server.py`: small local HTTP adapter, shell/static assets and JSON routes. Does not log request URLs or headers.
- `fixtures.py`: controlled catalog, server-owned input validation, Germany date windows, and authored response objects. No temperature classification algorithm; existing experiments remain unchanged.
- `templates/index.html`, `static/style.css`: application shell and V5-derived visual styles, with specification corrections. No external fonts, imagery or scripts.
- `static/components.js`: replaceable `WarmthIndicator` and city-card presentation. Receives explicit six-level/null values; maps L1/L2 to the same lightweight label. Null renders text without bars.
- `static/app.js`: in-tab form state, independent URL routing, async results, keyboard city selection, sharing and Germany-day revalidation on focus/visibility and a 30-second date check. Request versions prevent a departed result request from replacing a newer screen.

Phase 2 should replace the fixture producers behind `GET /api/cities?q=`, `GET /api/featured` and `GET /api/advice?view=&city_id=&start=&end=&preference=`. `/api/context` exposes current server-owned Germany date bounds. These endpoints are local fixture contracts, not live-weather endpoints. Invalid input returns 400; unavailable fixture data returns 503. City mode deliberately ignores trip date/preference parameters. Static paths are allowlisted; arbitrary repository paths are never served.

Preserve required nullable fields, card/detail variation consistency, data version, separate weather/advice timestamps and explicit historical mode. Python weather/recommendation services must own classification, daily coverage, current-day valid hours, historical completeness and actual recommendations. UI fixtures do not verify those computations. Remove fixture controls/parameters from any eventual production adapter. Real weather, eight-year calculations, caching, prefetch, hosting, production security and any choice of a production server remain Phase 2 work requiring its own scope.

## Verification

```sh
python3 -m unittest discover -s tests/web -v
python3 -m unittest discover -s experiments/clothing-rules -q
```

Optional local browser test dependency (not an application dependency):

```sh
npm install --prefix .local-tools --no-save --package-lock=false playwright
# Requires installed Google Chrome. Start the Python server separately.
node tests/web/browser.cjs
```

`.local-tools/` is ignored. The browser test uses an isolated headless Chrome profile and writes actual screenshots/results to `docs/verification/phase1/`. It exercises navigation, reload, sharing, fixtures, API failures, mobile widths, enlarged text and a simulated server-date rollover, without changing machine time. On a different port, set `UI_BASE_URL=http://127.0.0.1:8001`.

See [the visual verification record](../docs/verification/phase1/README.md). Browser testing here does not establish Safari, WeChat or physical-device compatibility; no screen-reader run or actual meteorological validation was performed.
