# Phase 1 browser and visual verification

Verified locally on 2026-10-15 with isolated headless Google Chrome 155.0.8059.79 against `python3 -m web.server`. The application is a fixture-only UI, not a real weather service. Screenshots are actual browser captures, not modified reference assets. Browser screenshots use reduced motion and a single content-height viewport capture, avoiding repeated-tile artifacts seen with this Chrome build’s full-page capture. Layout assertions run at the listed width and 844px height before capture; screenshot heights reflect complete content length.

## Results

- **63 browser assertions passed**, no page JavaScript errors: [machine-readable results](browser-results.json), [reproducible browser test](../../../tests/web/browser.cjs).
- **11 Python fixture/contract tests passed**, including one clock instant per snapshot, forecast/historical boundary, Berlin midnight and DST, invalid dates, city input isolation, variation/card consistency and missing weather timestamps.
- **122 existing clothing-rule experiment tests passed**; experiments were not changed.
- Checked homepage and stable/colder/warmer/split results at **320, 375, 390, 430 and 1280px** without horizontal overflow. Checked 200% text enlargement at 320px with complete Chinese copy; text wraps and no critical sentence is ellipsized.
- Exercised both complete journeys; keyboard city search/selection (ArrowDown/Enter); Frankfurt disambiguation by federal state; all ten cities through pagination; form preservation through city navigation/reload; trip back/forward/reload; canonical direct links; copy suggestion/link; bad dates and duplicate parameters; loading/unavailable/stale panels; HTTP 400/503.
- Date checks cover the Python server's Berlin day boundary including DST. A browser route mock simulates the server observing midnight, then focus triggers a city-reference request with the new fourteen-day window. Machine time was not changed. Actual past-daytime weather coverage is Phase 2, not verified by fixtures.
- Actual computed button/white-text and body/source/page colors pass the 4.5:1 normal-text contrast threshold. Native controls have visible focus, and the city chooser provides labelled keyboard-operable suggestion buttons. This is not a full accessibility audit or screen-reader test.

## V5 comparison

Each of the five reference screenshots was opened and visually compared with its implementation counterpart. The original `design/reference/v5/` assets are unchanged. This is a human visual comparison by the agent, not a pixel-identical claim or automated screenshot-baseline pass.

| V5 reference | Actual implementation | Assessment / intentional differences |
| --- | --- | --- |
| [Mobile home](../../../design/reference/v5/screenshots/01-home-mobile.png) | [01-home-mobile.png](01-home-mobile.png) | Same warm cream canvas, terracotta action, white form, two-column cards and independent featured section. Dates stack on narrow phones to retain 16px input text. Full year/date labels and honest “未获取真实天气数据” increase height. Cards use authored scenario summaries instead of copying prototype conclusions. |
| [City result](../../../design/reference/v5/screenshots/02-city-result-mobile.png) | [02-city-result-mobile.png](02-city-result-mobile.png) | Same return/header/answer/variation/inner-layer/context/actions order. Correct spec mapping makes L2 “轻薄”; V5's marker mapping was inconsistent with the six-level contract. Variation remains visible with a non-null marker. Adds explicit inner-layer heading and separates simulated generation time from unacquired weather time. |
| [Trip result](../../../design/reference/v5/screenshots/03-trip-result-mobile.png) | [03-trip-result-mobile.png](03-trip-result-mobile.png) | Same result component and personal return action. Uses Munich and cold sensitivity to demonstrate personal-state isolation. Stable fixture correctly has no variation panel; optional colder fixture demonstrates the alternative. |
| [Historical result](../../../design/reference/v5/screenshots/04-historical-result-mobile.png) | [04-historical-result-mobile.png](04-historical-result-mobile.png) | Same result structure, historical mode tag and sand-colored uncertainty panel. Explicitly says historical data was not queried and is not a forecast; no invented future-day variation. Source block and inner-layer label add height. |
| [Desktop home](../../../design/reference/v5/screenshots/05-home-desktop.png) | [05-home-desktop.png](05-home-desktop.png) | Retains V5 two-column hero/form, roughly 1040px content area, four-card grid and pagination. Longer complete fixture copy increases card height. No unrelated graphics or legend added. |

The collapsed fixture selector is an intentional Phase 1 testing aid below the main content; it is not part of a future production flow. System fonts, native date rendering and Chrome locale can cause small line-wrap/control differences. Programmatic heading focus can display the browser's focus ring in some captures; keyboard focus styling is retained.

## Additional captures

- Home widths: [320](home-320.png), [375](home-375.png), [390](home-390.png), [430](home-430.png), [desktop](home-1280.png).
- Variation states: [stable](fixture-stable.png), [one colder day](fixture-colder.png), [one warmer day](fixture-warmer.png), [seven/seven split](fixture-split.png).
- Failure states: [loading](fixture-loading.png), [unavailable](fixture-unavailable.png), [stale](fixture-stale.png), [invalid input](fixture-invalid.png).
- [320px enlarged text](large-text-320.png).

## Limits and handoff

Only desktop Chrome with responsive viewports was exercised; physical Android/iOS, Safari and WeChat remain unverified. No live forecast, eight-year history, real temperature-to-clothing calculations, weather timestamps, current-day effective-hour validation, cache, scheduled refresh, deployment or production service is claimed. The fixtures demonstrate presentation and routing only. See [web/README.md](../../../web/README.md) for run/test commands and Phase 2 API handoff boundaries.
