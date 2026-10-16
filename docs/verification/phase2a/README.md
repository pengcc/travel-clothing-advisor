# Phase 2A verification — 2026-10-16

Issue #19, based on current main `c68dffb` (merged PR #18). Local development only; no merge or deployment.

Actual results:

- 23 Python web tests passed: existing 11 fixture tests plus 12 service/HTTP tests. Fake provider and injected clock; no required provider network. Covers outliers in both directions, split/stable/boundary noise, independent variation summary, early/evening layers, sensitivity without changed weather, retained acquisition time, unknown IDs/foreign locations, Frankfurt namesakes, invalid/duplicate/coordinate params, missing/null/non-finite/empty/reordered/duplicate hours, wrong dates, units/timezone, spring/fall DST, German midnight including acquisition rollover, today after daylight and after usable evening hours, timeout/429/5xx without retries, forecast-only requests and unavailable historical live responses.
- 122 existing clothing-rule experiment tests passed. No experimental CLI files or tests were changed; the web adapter imports only the pure level function and does not make the CLI's historical calls.
- 63 existing Phase 1 browser assertions passed against explicit `--fixtures` mode, with `--check-only` preserving the original screenshots. Includes routing/return/reload/share, independent inputs, loading/stale/unavailable, widths and 200% text.
- All 10 `featured-regressions.cjs` tests passed, including inverted response order, stale/off-page entries and simulated German midnight.
- 25 new browser checks passed against the actual Python service/HTTP adapter using injected complete hourly weather and geocoding. Includes live default, German namesakes, real-path versus demo labels, separate acquisition/generation labels, dated outlier before layers, copy/share/reload/return, featured isolation, deferred history, demo-only history, remote-period uncertainty, 320/375/390/430/1280px overflow checks and upstream failure. No browser JS errors.
- Optional **real provider smoke passed** for Berlin, 2026-10-17…19, normal sensitivity: forecast mode, fresh same-day acquisition, temperature-derived保暖夹克/轻羽绒 conclusion. Weather was acquired at 2026-10-16 10:22:07 Europe/Berlin. This was a public example, not a saved personal query. Success confirms connectivity and parsing at that time; it does not establish forecast or clothing accuracy.
- `git diff --check` passed.

[Mobile live-path capture with injected synthetic weather](live-injected-mobile.png) was inspected for V5 layout, readable wrapping, outerwear → variation → inner layers ordering, uncertainty and source timestamps. It is a deterministic test capture, **not real observed/provider forecast evidence**. Existing V5 assets and Phase 1 verification images remain unchanged. System-font rendering and Chrome responsive viewports were used; no physical-device, Safari/WeChat or screen-reader claim is made.

Run commands and the optional live smoke are documented in [web/README.md](../../../web/README.md). The heuristics remain experimental. Process-local reuse is not distributed/persistent storage. Live eight-year temperature-only historical reference (2B) and featured-city shared prefetch/cache (2C) remain deferred; featured data is visibly simulated throughout.


## Review #5545508096 follow-up

Both actionable findings were reproduced against reviewed head `c5fdca5` before the implementation fix. The new full-service split regressions failed to find required winter/appropriate outerwear in the headline, and mixed valid/incomplete geocoding results raised `Unavailable` / returned HTTP 503.

- **P1:** No-majority recommendations now name the actual coldest observed outerwear requirement in the headline and variation notice/summary, and provide both colder-day and warmer-day inner-layer options. Seven L2 + seven L6 and seven L4 + seven L6 days explicitly require **冬季保暖外套、保暖内搭、毛衣或抓绒**. Seven L2 + seven L4 days require **适中外套、薄毛衣**, without upgrading to winter clothing. The indicator and representative temperature stay null. Full-service JSON tests cover all three distributions under normal/cold/hot sensitivity; the visible browser answer covers all three, dated reminders, null marker/no bars, ordering and 320/390px wrapping.
- **P2:** Candidate validation failures are isolated within search. A valid match survives incomplete state, name, ID or coordinate metadata in either result order; no fields are invented. A nonempty wholly unusable list returns 503, an empty list remains a successful no-match result, and direct ID lookup continues to reject incomplete locations. Service and real local HTTP regression tests verify these boundaries; the browser verifies a valid suggestion remains visible and selectable.
- **Actual rerun results:** 26 Python web/service/HTTP tests, 122 existing experiment tests, 63 Phase 1 browser assertions, all 10 featured regressions, 25 existing live-path browser checks and 35 new review browser checks passed. `git diff --check` passed. The new browser script computes full service JSON with injected hourly/geocoding data in Python and renders that JSON through intercepted local API responses; it does not contact a live provider or prove meteorological accuracy.

[Winter-split mobile capture](winter-split-injected-mobile.png) uses injected synthetic 24°C/0°C weather, with the existing V5 UI. Inspected for explicit winter clothing in the primary answer, lighter warmer-day layers, null warmth indicator, readable wrapping and honest timestamps. Run `tests/web/review-regressions.cjs` against the explicit fixture server as documented in `web/README.md`.

No Phase 2B history, Phase 2C featured prefetch/cache, deployment or merge was added. The original provider smoke above was not repeated for these deterministic rule/candidate fixes.
