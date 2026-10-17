# Issue #34 verification

Implemented from main `b7bc742`, using Issue #34 as the requirements boundary.

Personal results retain validated city identity, input dates, preference and the forecast/history label during loading and failures. Direct live links resolve city metadata rather than trusting the built-in city list. Unresolved cities remain explicitly unknown. `history_incomplete` selects 修改行程; transient errors select 重试查询; invalid requests have no retry. The existing back action restores the editable trip. The focused result heading uses the theme's visible focus treatment instead of the default blue outline; buttons/inputs retain keyboard focus styling.

## Read-only local coverage observation (2026-10-17)

The ignored `.history-local` directory exists. A read-only adapter called the existing `Library.read` validation without constructing a writable directory adapter, taking a worker lock, invoking a downloader, or changing the store. Only aggregate coverage was emitted; raw source records and acquisition artifacts remain ignored.

For an **illustrative** 2026-11-02 through 2026-11-05 trip, `months(windows(start,end))` requires November 2021, 2022, 2023, 2024 and 2025. All five Berlin blocks validate using the available verified city metadata. There are zero München month objects under its provider ID, and the local metadata input has no München record. Thus this local library cannot currently serve that illustrative München trip. Exact coordinate-aware validation for München cannot be performed without verified metadata; no coordinates were invented.

Issue #34 does not specify the actual failing trip dates. Its exact required months and the deployed library state remain **unverified**. The local observation does not establish deployed coverage or explain deployment configuration. No history data was downloaded or filled.

Existing diagnostics: `web.prefetch_history` without `--download` computes the priority jobs and reports aggregate missing-block and equivalent-call counts for supplied validated cities. It does not list individual missing months, and only covers supplied cities. `windows` + `months` identify a specific trip's required blocks; `Library.read` identifies missing/invalid blocks when verified metadata and the actual store are accessible. An outage raises rather than proving missing data. Actual repair remains the existing explicit, bounded prefetch process with validated metadata and normal quotas; no download/cache/quota policy changed.

## Offline validation

- `python3 -m unittest discover -s tests/web -q`: 72 tests pass, including stable HTTP error categories and missing-history behavior.
- Synthetic local server: `python3 tests/web/serve_forecasts.py --port 8002`.
- `node tests/web/error-regressions.cjs`: loading/error context, München history 503, edit restoration, transient forecast retry, unknown city and duplicate links pass.
- `UI_BASE_URL=http://127.0.0.1:8002 node tests/web/history-browser.cjs`: 27 checks pass.
- `UI_BASE_URL=http://127.0.0.1:8002 node tests/web/live-browser.cjs --check-only`: 33 checks pass.
- Featured and review browser regressions: 10 and 35 checks pass.

All browser weather responses are synthetic. No live historical download, merge or deployment.
