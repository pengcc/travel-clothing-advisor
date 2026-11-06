# Issue #27 UI and copy verification

Verified 2026-10-17 from main `4e2572b`. This is a presentation-only follow-up. Python production changes are limited to advice presentation: historical wording/placement and a compact clipboard plan derived from already-selected clothing levels and triggered risk events. The plan does not read temperatures or fetch weather. Usual outerwear stays in the headline; additional historical cold inner layers move into the existing risk notice. Forecast acquisition, cache, sample selection, six clothing thresholds, variation/risk triggers and elapsed-hour exclusion are unchanged.

## Reproduce

```sh
python3 -m unittest discover -s tests/web -q
python3 -m unittest discover -s experiments/clothing-rules -q
python3 -m web.server --fixtures --port 8001
# In another terminal:
python3 tests/web/serve_forecasts.py --port 8002
```

With the Playwright install from "Browser test setup" in `web/README.md` (`(cd tests/web && npm ci)`, shared with `capture.cjs`) and local Chrome:

```sh
UI_BASE_URL=http://127.0.0.1:8001 node tests/web/browser.cjs --check-only
UI_BASE_URL=http://127.0.0.1:8001 node tests/web/featured-regressions.cjs
UI_BASE_URL=http://127.0.0.1:8001 node tests/web/review-regressions.cjs --check-only
UI_BASE_URL=http://127.0.0.1:8001 node tests/web/history-browser.cjs
UI_BASE_URL=http://127.0.0.1:8002 node tests/web/live-browser.cjs --check-only
UI_BASE_URL=http://127.0.0.1:8002 node tests/web/copy-regressions.cjs
node docs/verification/issue27/capture.cjs
```

Results: 60 web tests and 122 clothing-rule tests pass; browser suites pass 63, 10, 35, 27, 33 and 57 checks/cases respectively at the F1–F3 checkpoint; see the clipboard follow-up below for current totals. Restricted execution requires loopback/Chrome permission. All provider data is synthetic and injected: these results establish no live-weather acquisition, actual forecast accuracy or garment-science validity. No live weather calls, production data mutation, deployment or merge.

## Output comparison

Deterministic forecast example (Berlin, 2026-10-16 through 2026-10-29, normal preference):

- Main: “轻薄即可，不必带厚外套”.
- Separate dated risk: “2026-10-17偏冷：建议带适中外套，里面可叠穿薄毛衣，按时段增减保暖层。”
- City explanation appears once below inner layers: “默认按正常冷热偏好推荐。每个人对冷热的感受不同，怕冷可多备一层，怕热可适当减薄。”
- Forecast uncertainty, including days 8–14, remains visible; acquisition time and Open-Meteo / CC BY 4.0 / GeoNames attribution are accessible in data details.

Historical example (November 2–5; four yearly samples at 8°C and one at 0°C):

- Before: the headline combined the common L5 coat and extra L6 cold-risk coat; cold inner-layer text repeated in the main layers.
- Now headline: “建议带保暖夹克或轻羽绒”.
- Separate risk: “过去五年同期曾出现较冷情况：建议带冬季保暖外套，搭配保暖内搭、毛衣或抓绒；较暖时内搭减薄、外层方便脱下。不是本次旅行预报。” Each cold garment is named once within the risk block. Typical inner layers remain long sleeves with a sweater/fleece.
- Mode prominently says “过去五年同期参考，不是本次旅行预报”. No future cold date is invented. No acquisition is repeated when preference changes.

Meaningful early-evening coverage remains explicit when supported by the existing notices. General thickness-boundary guidance uses a neutral heading rather than an evening-risk heading. Separate cold/warm coverage in genuinely split results remains explicit; the L5/L6 risk block no longer repeats its own garment recommendations. No frontend temperature inference or trigger changes were introduced. Near-13°C boundary advice and no-representative-level cold/warm coverage remain covered by existing regression tests.

## Browser scope and visual inspection

Tests cover exact 怕冷 / 正常 / 怕热 labels and default selection; all personal preference displays; city-only default explanation; hidden normal-mode fixture controls with `--fixtures` retained; source details accessible by native summary; copy retains historical L6 risk and attribution; independent city/trip links and back/forward/reload; all ten cities over three pages; single cold/warm outliers, split/null and minor boundary noise; no successful answer after network failure; retry recovery; historical missing blocks still return 503.

Automated mobile overflow checks cover 320/375/390px (existing suites also cover 430/1280 and enlarged text). Visually inspected the three synthetic 375px captures below, preserving the existing warm palette and warmth bars. Device Safari/WeChat, actual live provider data and hosted deployment are not part of this verification.

- [Homepage](home-375.png)
- [Forecast city detail](forecast-375.png)
- [Historical L5 usual / L6 risk](history-375.png)

## Review #5557370663 follow-up

Addressed all three P2 findings on the same delivery branch:

- **F1:** Conditional heading/icon uses “分层与厚度提示” for general or mixed notes, reserving “早晚注意分层” for genuine cooler-hour guidance. Browser tests render Python-derived near-13°C forecast and historical inputs with no cooler edges, verify the general guidance is visible/copied without an evening heading/icon, and verify real 20:00 cooler-hour advice retains its evening title.
- **F2:** “通常准备的外套” requires a representative historical level. Evenly split historical samples instead use “外套建议”, retaining null bars/temperature, winter outer/inner coverage and lightweight warm alternatives. Browser tests cover both representative L5 and equal cold/warm historical samples.
- **F3:** The historical risk composes cold outerwear plus concise inner layers once and omits the usual jacket as a redundant warmer option. The 4×8°C + 1×0°C test checks each winter garment appears exactly once, warmer/removable-layer options and non-prediction remain, for all three preferences. Existing split/near-boundary safety tests continue passing.

Re-ran all six browser suites: 225 checks/cases in total, plus 60 web and 122 clothing-rule tests. The updated historical capture was visually inspected at 375px. Data acquisition, cache and clothing/risk calculations are unchanged. Tests remain entirely synthetic; no merge or deployment.

## Review #5557706623 — compact clipboard summary

The copy button now exports fields explicitly instead of serializing result/source DOM text. City, ISO date range and actual personal preference have separate lines, followed by data nature, labeled outer/inner preparation and genuine cold/warm/early-evening reminders. Typical L5 and extra L6 remain separate; shared garments appear once in the matched-backend summary. Historical split results keep their full cold/warm range without a “usual” claim. An early-evening event remains visible even when its clothing has already been listed. Minimal attribution is `Open-Meteo / ERA5（CC BY 4.0）；GeoNames` for history and `Open-Meteo（CC BY 4.0）；GeoNames` for forecasts. Acquisition, per-month and generation timestamps, model-time footnotes and history-window mechanics are excluded from clipboard, retained in on-page data details.

The new `packing_copy` API presentation field records the original branch's already-selected levels/date labels. It does not introduce thresholds, reread weather, or change any original headline, layer, notice, risk trigger, cache identity, sample window or acquisition path. Five focused Python tests check event collection preserves packing decisions, L5/L6 deduplication, cooler-hour needs, split coverage and evening-only/boundary meaning. Legacy/hand-authored fixtures retain their original safety copy with explicit simulated provenance; tests do not infer real provider data from fixture values.

A new browser suite compares **entire clipboard strings** for historical L5 + L6 and forecast advice for each of cold/normal/hot. It checks date/preference line separation, required attribution exactly once, no technical audit log, once-only winter outer/inner names, cold and warm garment coverage, early-evening risk retention, 8–14-day uncertainty, warm-only/stable forecasts, fixture provenance and continued on-page source access.

```sh
UI_BASE_URL=http://127.0.0.1:8002 node tests/web/clipboard-regressions.cjs --capture
```

Clipboard-summary checkpoint results: **65 web tests**, **122 clothing-rule tests**, and all seven browser suites pass (**273 checks/cases**: 63 + 10 + 35 + 27 + 33 + 57 + 48). [Exact copied history and forecast examples](copied-advice.txt) are synthetic, generated from the current branch's Python backend and frontend together. This does not reproduce or validate the user's mixed-version live environment, and no live provider requests were made. F1–F3 on-page fixes remain intact. No merge or deployment.

## Review #5557755794 — L1/L2 nonpositive coat conclusions

The clipboard presenter now separates positive coat items from the L1/L2 “不必带厚外套” conclusion and deduplicates coats by physical garment text rather than level ID. It never inserts a no-coat conclusion into an “另备” list. If a short sleeve is already covered, the L2 short/long-sleeve alternative adds only the uncovered thin long sleeve. A repeated light-level evening event still has an explicit lighter-clothing reminder, without inventing a warm coat or extra thermal layer.

Focused Python regressions cover L1→L2 cold and evening events, already-covered/nonpositive coat needs and physical garment deduplication across different labels. Full-string browser regressions use the current backend's actual L1→L2→L1 decisions at synthetic 29°C/24°C/29°C and a synthetic 29°C daytime/24°C 20:00 case. They check the L1 main decision and original cold/edge notice remain intact, while exported risk says `2026-10-17偏冷：另备薄长袖。` or `10月16日 20时前后较凉：另备薄长袖。`. The complete examples, including attribution, are appended to [copied-advice.txt](copied-advice.txt).

Latest results: **68 web tests**, **122 clothing-rule tests**, all seven browser suites passing (**281 checks/cases**: 63 + 10 + 35 + 27 + 33 + 57 + 56). Existing L5/L6 full-string tests continue to preserve winter outerwear and thermal inner layers exactly once. Only copy presentation and focused tests/evidence changed in this follow-up; original on-page clothing decisions, weather/cache paths, thresholds and triggers are unchanged. All inputs are synthetic. No merge or deployment.
