# Phase 2C offline acceptance

Implemented for Issue #25 from `main` / `0441c82`, verified 2026-10-17. This record covers **local implementation and deterministic offline acceptance**. Every weather response and city record used in tests is synthetic provider-injected data, not live weather or real GeoNames seeding. Normal-mode labels in screenshots exercise the real service path against that injected provider. No live forecast/geocoding/archive API downloads, hosted storage, credentials, cron, deployment or merge were performed.

## Reproduce

From repository root, Python 3.9+ with Berlin zone data:

```sh
python3 -m unittest discover -s tests/web -q
python3 -m unittest discover -s experiments/clothing-rules -q
python3 -m web.prefetch_forecasts --help
```

Results: **59 web tests**, **122 clothing-rule tests** pass. The new `test_forecasts.py` covers source identity, publication, admission, HTTP paths, persistence, independent-process reuse and locking. Loopback HTTP tests need permission to bind local sockets in a restricted sandbox. No test contacts an upstream provider.

Using the repository's existing optional, ignored Playwright installation and local Chrome, start two terminals:

```sh
python3 -m web.server --fixtures --port 8001
python3 tests/web/serve_forecasts.py --port 8002
```

Then:

```sh
UI_BASE_URL=http://127.0.0.1:8001 node tests/web/browser.cjs --check-only
UI_BASE_URL=http://127.0.0.1:8001 node tests/web/featured-regressions.cjs
UI_BASE_URL=http://127.0.0.1:8001 node tests/web/review-regressions.cjs --check-only
UI_BASE_URL=http://127.0.0.1:8001 node tests/web/history-browser.cjs
UI_BASE_URL=http://127.0.0.1:8002 node tests/web/live-browser.cjs
```

Results: **63** general browser checks, **10** featured regression cases, **35** packing-review checks, **27** historical checks and **34** Phase 2C real-path browser checks pass. The historical suite also regenerates its existing Phase 2B screenshot; this PR preserves earlier-phase evidence files. The synthetic server freezes the Berlin clock at 2026-10-16 10:30, prepares ten full source objects, then reruns with 10 hits / 0 requests. Fixture and normal APIs both use the injected clock; the ordinary server defaults to the actual Berlin clock.

## Request-count and reuse evidence

`test_forecasts.py` asserts the following counts directly; geocoding is counted separately:

| Scenario | Forecast attempts | Hits / result |
| --- | ---: | --- |
| One verified synthetic city/day through worker load primitive | 1 | Source persisted; first personal query adds 0 |
| Same source, different dates/preferences, new service/store instance | 0 extra | Same data version and acquisition; new generation timestamp |
| Complete ten-city worker on empty store | 10 | 10 validated sources, one complete manifest |
| Same-day complete worker rerun | 0 | 10 hits |
| Nine personal date/preference variants after prefetch | 0 extra | 9 distinct geocoding resolutions, consistent weather version/acquisition |
| Cards, city detail, reload | 0 extra | Full block validated; card/detail advice and variation agree at frozen clock |
| Separate Python process after directory-store restart | 0 | 10 worker hits, cards/detail read successfully; provider function forbids outbound calls |
| Fourth fetch fails | 4 attempts including failure | 3 sources retained; no featured manifest; featured/detail unavailable; Berlin personal query still works |
| Immediate failed-worker rerun | 0 | Cooldown blocks missing downloads; completed sources remain hits |
| Recovery after cooldown | 7 | 3 hits, complete ten-city publication; ledger retains all 11 attempts including failure |
| Final manifest write fails after sources finish | 10 | No partial featured block; retry has 10 hits / 0 requests and publishes complete manifest |
| Non-featured city, two preferences | 1 total | Controlled on-demand miss then hit, independent of featured readiness |
| One-attempt injected daily limit, another city after restart | 0 additional | Refused; reserved attempt survives restart |

The worker's public manual command accepts exactly ten distinct featured provider records and never geocodes. Operator files belong in ignored `.forecast-local/`; the intentionally synthetic test records must not initialize real data. Actual invocation contract, limits, exit codes and recovery are in [web/README.md](../../../web/README.md#phase-2c-shared-daily-forecast-sources-local-only).

## Cache, date and failure behavior

- Source identity: verified GeoNames ID, exact validated coordinates, request/model/format version and Germany-local date. Raw source response + observed acquisition metadata is checksummed; source-derived `data_version` stays consistent across personal ranges/preferences and featured representations. No per-user recommendation, trip or preference is stored.
- Reads revalidate identity, checksum, acquisition date/not-in-future, Celsius units, finite temperatures, consecutive original UTC hours and every 06–22 slot throughout 14 local days. Existing parser tests also exercise missing, duplicate, reordered, null, error, wrong-unit and stale responses. Changed model/format/coordinates cannot hit the old source.
- Source objects and the final all-ten manifest use atomic replacement. Every featured read validates all sources against manifest versions; incomplete/corrupt/missing/outage/contended reads return 503, never fixtures or fabricated clothes. Explicit `fixture=` and `--fixtures` remain simulated. HTTP tests assert real default success after preparation and unavailable after corruption, plus explicit fixture success.
- Frozen UTC instants cover spring/fall DST and Berlin midnight. Both autumn folds are retained without duplicating UTC epochs. Yesterday's publication is unavailable after midnight until a complete new-day prefetch; a fetch crossing midnight cannot publish as current. Personal advice retains Phase 2A elapsed-hour filtering and rejects cross-date acquisition/generation.
- Concurrent worker/reader/personal access fails quickly while a store is locked; no duplicate downloads occur. Two directory adapters and a **separate Python process** verify the filesystem lock boundary. These are single-host cooperative locks, not distributed coordination.
- Deadlines, storage failures, corrupt admission ledger, reserved failed attempts and cooldown are tested. An injected slow provider crossing the total deadline cannot publish a source. Real transport is reused from Phase 2B (bounded bytes and socket/wall-time waits); existing transport tests use loopback only. An injected provider must honor its timeout; tests additionally reject late results before publication.
- The local 42-attempt daily ceiling is an internal forecast HTTP budget, not an account-wide quota or provider equivalent-call measurement. No live latency, provider quota, hosted object consistency or production scheduling claim is made.

## Packing and mobile evidence

The six-level rule and variation function are reused, without changed garment thresholds or historical calculations. L2→L4→L2 and L4→L2→L4 single outliers still produce notices with representative L2/L4 respectively. Seven L2 plus seven L4 days retain a null representative and meaningful variation. Near-13°C minor noise produces no false variation alert. Existing five-year historical regression retains L6 winter outerwear and inner layers without claiming a future cold date.

The backend supplies card summaries and detail notices from the same decision. There are no frontend temperature or clothing calculations. Advice is recomputed from stored sources and remaining hours, so a later calculation can legitimately change after hours elapse while its source version stays unchanged. Each featured response uses a single calculation instant for all ten cities.

Mobile Chrome verifies real-path card provenance, city tap → today…+13/normal, independent city copy/share URL, reload, personal dates and hot preference preserved through city navigation and browser back/restore, explicit demo switching, unavailable responses without clothing, no JavaScript errors and no horizontal overflow at 320, 375, 390, 430 and 1280px. Existing suites cover stale entries, late reversed responses and day rollover. Android/iOS/WeChat devices, live provider latency, accessibility audit and hosted Preview remain outside this local evidence.

Visually inspected, synthetic provider screenshots:

- [Featured cards](featured-injected-mobile.png)
- [City detail](city-injected-mobile.png)
- [Personal trip](live-injected-mobile.png)

## Provider contract check and review

Repository Phase 2A/2B contracts were reused. A narrow Docs-First check on 2026-10-17 of the official [Open-Meteo forecast documentation](https://open-meteo.com/en/docs) confirmed the existing Celsius, `forecast_days`, `timezone`, Unix-time options and Best Match/default model selection. The cache now names `best_match` explicitly in request identity and outbound parameters. UTC epochs are converted through `ZoneInfo` for local DST, rather than applying one fixed provider offset. This documentation check is not a live forecast test or clothing-science validation.

Review scope: published PR source, source/manifest consistency, zero-provider featured reads, fail-closed admission/date boundaries, fixture separation, unchanged history/garment algorithms and verification reproducibility. Main remains untouched; merge and Phase 2D hosted work require separate authorization.
