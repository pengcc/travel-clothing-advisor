# Issue #27 UI and copy verification

Verified 2026-10-17 from main `4e2572b`. This is a presentation-only follow-up. The sole Python production change is historical advice wording/placement: usual outerwear stays in the headline; additional historical cold inner layers move into the existing risk notice. Forecast acquisition, cache, sample selection, six clothing thresholds, variation/risk triggers and elapsed-hour exclusion are unchanged.

## Reproduce

```sh
python3 -m unittest discover -s tests/web -q
python3 -m unittest discover -s experiments/clothing-rules -q
python3 -m web.server --fixtures --port 8001
# In another terminal:
python3 tests/web/serve_forecasts.py --port 8002
```

With the existing optional `.local-tools` Playwright installation and local Chrome:

```sh
UI_BASE_URL=http://127.0.0.1:8001 node tests/web/browser.cjs --check-only
UI_BASE_URL=http://127.0.0.1:8001 node tests/web/featured-regressions.cjs
UI_BASE_URL=http://127.0.0.1:8001 node tests/web/review-regressions.cjs --check-only
UI_BASE_URL=http://127.0.0.1:8001 node tests/web/history-browser.cjs
UI_BASE_URL=http://127.0.0.1:8002 node tests/web/live-browser.cjs --check-only
UI_BASE_URL=http://127.0.0.1:8002 node tests/web/copy-regressions.cjs
node docs/verification/issue27/capture.cjs
```

Results: 60 web tests and 122 clothing-rule tests pass; browser suites pass 63, 10, 35, 27, 33 and 32 checks/cases respectively. Restricted execution requires loopback/Chrome permission. All provider data is synthetic and injected: these results establish no live-weather acquisition, actual forecast accuracy or garment-science validity. No live weather calls, production data mutation, deployment or merge.

## Output comparison

Deterministic forecast example (Berlin, 2026-10-16 through 2026-10-29, normal preference):

- Main: “轻薄即可，不必带厚外套”.
- Separate dated risk: “2026-10-17偏冷：建议带适中外套，里面可叠穿薄毛衣，按时段增减保暖层。”
- City explanation appears once below inner layers: “默认按正常冷热偏好推荐。每个人对冷热的感受不同，怕冷可多备一层，怕热可适当减薄。”
- Forecast uncertainty, including days 8–14, remains visible; acquisition time and Open-Meteo / CC BY 4.0 / GeoNames attribution are accessible in data details.

Historical example (November 2–5; four yearly samples at 8°C and one at 0°C):

- Before: the headline combined the common L5 coat and extra L6 cold-risk coat; cold inner-layer text repeated in the main layers.
- Now headline: “建议带保暖夹克或轻羽绒”.
- Separate risk retains “冬季保暖外套和保暖内搭” plus “保暖内搭搭配毛衣或抓绒”. Typical inner layers remain long sleeves with a sweater/fleece.
- Mode prominently says “过去五年同期参考，不是本次旅行预报”. No future cold date is invented. No acquisition is repeated when preference changes.

Some cold outer/inner and meaningful early-evening coverage remains explicit in overlapping notices. This intentionally preserves safety information where the existing API does not distinguish an already-covered garment from an independent colder-hours need. No frontend temperature inference or trigger changes were introduced. Near-13°C boundary advice and no-representative-level cold/warm coverage remain covered by existing regression tests.

## Browser scope and visual inspection

Tests cover exact 怕冷 / 正常 / 怕热 labels and default selection; all personal preference displays; city-only default explanation; hidden normal-mode fixture controls with `--fixtures` retained; source details accessible by native summary; copy retains historical L6 risk and attribution; independent city/trip links and back/forward/reload; all ten cities over three pages; single cold/warm outliers, split/null and minor boundary noise; no successful answer after network failure; retry recovery; historical missing blocks still return 503.

Automated mobile overflow checks cover 320/375/390px (existing suites also cover 430/1280 and enlarged text). Visually inspected the three synthetic 375px captures below, preserving the existing warm palette and warmth bars. Device Safari/WeChat, actual live provider data and hosted deployment are not part of this verification.

- [Homepage](home-375.png)
- [Forecast city detail](forecast-375.png)
- [Historical L5 usual / L6 risk](history-375.png)
