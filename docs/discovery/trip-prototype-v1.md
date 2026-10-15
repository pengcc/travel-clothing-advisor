# Trip-selectable clothing advice + two-year same-period reference (prototype)

**Status:** engineering experiment; not a released app or completed product validation. Extends the merged six-tier weather-to-clothing CLI, without a new framework or database.

## Why

The user chooses **a German city, travel start/end dates, and optional cold/normal/hot preference**. Current forecast advice should consider **only their travel dates**. The same period **one and two calendar years earlier** is shown as a separate comparison, rather than silently overriding the forecast or presenting past weather as a forecast.

## Run

Python 3.10+ with local timezone support; no Python packages needed.

```bash
python3 experiments/clothing-rules/trip_advisor.py --city Berlin --start 2026-10-20 --end 2026-10-23
python3 experiments/clothing-rules/trip_advisor.py --city München --start 2026-10-20 --end 2026-10-23 --preference cold
python3 experiments/clothing-rules/trip_advisor.py --city Berlin --start 2026-10-20 --end 2026-10-23 --details
python3 -m unittest discover -s experiments/clothing-rules -p 'test_*.py' -v
```

Dates in examples are illustrative and must be within the upcoming 14 calendar days at the time of running. In a fresh run replace them with dates relative to the current local date. The original `forecast_advice.py` no-argument Berlin demonstration is unchanged.

## Data & rules

1. [Geocoding API](https://open-meteo.com/en/docs/geocoding-api): `countryCode=DE`, return German city coordinates and timezone. Exact, unique place-name matches only; ambiguous or fuzzy matches produce a validation error rather than a guess. Berlin timezone applies across Germany.
2. [Forecast API](https://open-meteo.com/en/docs): existing 14-day hourly temperature and precipitation + daily weather fields, using selected city coordinates. For the main recommendation, process **only selected trip days**. Relative uncertainty (days 8–14) is anchored to *query day*, not the first day of travel.
3. [Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api): two requests for exactly the chosen date range in previous calendar years, requesting hourly `temperature_2m` and daily `precipitation_sum`, `snowfall_sum`. Compute past daytime 09–18 local median temperatures, as done for the forecast, plus a conservative past precipitation/snow day count. This is **reanalysis**, not verified readings from a weather station.
4. In the traveler output, historical comparisons are visibly labeled as **past years, not a prediction**. A large difference from past cool days adds a caution about removable layers, **without changing** the main forecast-derived warmth level.

## Explicit boundaries

- **Only dates within the next 14 calendar days**. Reject out-of-range trips before making network requests. Trips 15–30 days away require additional multi-year seasonal/context work, not an invented forecast.
- Two years is a useful recent comparison but **not a reliable climate normal or statistical probability**. No claims of forecast accuracy, personalized comfort, or sufficient evidence that an item is universally safe to leave out.
- Historical data is reanalysis with spatial and seasonal uncertainty. Around leap days, `29 Feb` is aligned to `28 Feb` where the prior year lacks leap day, and this is a pragmatic approximation.
- Dates covering the current evening without a remaining outdoor daytime period may not produce a useful current-day recommendation, and the CLI rejects empty future daytime inputs.
- Online integration with the new geocoding and historical requests **has not been exercised in this environment**. Offline fixtures test request parameters, date alignment, validation, and text output; API availability and example live outputs still need an actual connected run.
- Geocoding data derives from GeoNames; display attribution. Open-Meteo free endpoints have non-commercial limits and require attribution: review licensing before any commercial release.
- **No web UI, no automatic scheduler, no generalized climate horizon, no framework or deployment.** This PR addresses the data/logic end of the agreed user flow. A thin user-facing web form can be scoped separately after review.

## Follow-up: Berlin namesake geocoding regression (2026-10-15)

The first **real, networked** run of `--city Berlin --start 2026-10-17 --end 2026-10-20` stopped at geocoding: Open-Meteo returned two exact-name German results, in **Land Berlin** and **Schleswig-Holstein**. The initial code rejected any duplicate spelling, so it did not reach the weather or historical API. The user-observed failure does not mean those later APIs were validated or failed.

The corrected resolver:
- keeps exact-name and Germany-only matching;
- selects a **unique** `feature_code=PPLC` result (a national capital) without depending on API result order. Open-Meteo's documented Berlin capital is GeoNames ID `2950159`;
- for other duplicate names, selects the sole clearly dominant large city only when every result has a valid population (largest population at least 100,000 and at least 10 times the runner-up); this is an **experiment-stage product heuristic**, not a legal city-classification rule;
- otherwise refuses to guess and requests a precise `City, Federal State` name, e.g. `Berlin, Schleswig-Holstein`. The optional qualifier is matched against the returned administrative area, accepting `Land Berlin` and `Berlin` as aliases;
- does not choose the first fuzzy/prefix result and never silently selects a different country.

This is validated with deterministic synthetic geocoding fixtures, including a small namesake appearing **before** the capital and a complete city → forecast/history URL coordinate propagation check. **A real Berlin CLI invocation subsequently succeeded (see end-to-end smoke run below)**. The original geocoding error is a confirmed real-world input and a regression case.

## Live München lookup regression (2026-10-15)

After the Berlin geocoding fix, the user's **first real München run** failed before any forecast/history requests with `城市名称不唯一：München（Bayern, Brandenburg）`. The previous algorithm preferred only a **national** capital (`PPLC`) or required a valid `population` field for *every* exact-name result, but München (GeoNames ID `2867714`) has feature code **`PPLA`** because it is the seat of Bavaria. A smaller namesake may lack `population` entirely, which makes that fallback unusable. This is a **city resolver bug**, not a failure of the Forecast/Historical APIs.

Revised algorithm: a unique **national capital (PPLC)** or **first-order administrative seat (PPLA)** takes precedence among exact German-name candidates. These are verifiable GeoNames feature classifications. If there is more than one record at either of those top levels, reject as ambiguous even if reported populations differ. For other place types, keep the conservative population-dominance fallback and request a federal-state qualifier when data are insufficient. Lower-level `PPLA2` county/district seats are **not automatically promoted** over other locations. Explicit `München, Brandenburg` or `München, Bayern` still disambiguates by requested state.

This avoids a one-city hardcode and keeps the original strict safeguards on true ambiguity. Five synthetic regression tests cover a missing-population village, both ordering variants, explicit state qualifiers, duplicate state-capital classification, non-capital safety and coordinate propagation through the forecast and both archive URLs. **No claim is made that the corrected München live API request has succeeded yet**; a renewed real run and the latest complete suite are needed.

Sources: [GeoNames München (2867714)](https://www.geonames.org/2867714/munich.html), [GeoNames feature codes](https://www.geonames.org/export/codes.html), [Open-Meteo Geocoding API](https://open-meteo.com/en/docs/geocoding-api).

## Real end-to-end Berlin smoke run (2026-10-15)

A user ran the updated branch locally with an internet connection:

```bash
python3 experiments/clothing-rules/trip_advisor.py --city Berlin --start 2026-10-17 --end 2026-10-20
```

Their displayed output at **2026-10-15 12:16 Europe/Berlin** confirms the once-failing Berlin name selection now proceeds through forecast and **both** historical archive queries:

- 2026-10-17 to 2026-10-20: representative daytime **12.8°C**, traveler-facing output uses the retained near-13°C advice rather than a compulsory light-down coat.
- Prior corresponding interval 2025-10-17 to 2025-10-20: historical reanalysis representative daytime **10.1°C**, coolest daytime **8.5°C**, 0 days of significant precipitation and 0 snow days in the displayed output.
- Prior interval 2024-10-17 to 2024-10-20: historical reanalysis representative daytime **15.2°C**, coolest daytime **14.5°C**, likewise 0 displayed significant-precipitation/snow days.
- The historical section is explicitly labeled as past reanalysis and is *not* presented as a forecast or statistically robust climate baseline.

**Evidence limits:** This is a successful user-reported real API **integration smoke test**. Neither the raw Geocoding JSON nor the weather/archive JSON was stored; an independent data-quality verification or forecast-accuracy assessment has **not** occurred. The historical figures should not be hard-coded as future rules. A second-city live run and the full new regression suite remain to be checked.

Follow-up code review identified one related bug: a user-specified qualifier such as `Berlin, Schleswig-Holstein` was previously passed wholesale to the Geocoding `name` parameter, even though the solver parsed the qualifier only after receiving the response. The current version now searches by the settlement part `Berlin` and applies the provided federal-state qualifier **locally** to its returned records. Two new offline regressions cover search URL and correct coordinates used for forecast and both archive endpoints.

## Integration with merged PR #12 (2026-10-15)

This prototype was originally branched before PR #12, which added trip-date scoping, a 13°C threshold copy fix, and correct forecast lead-time warnings. The current PR's reconciliation uses the latest `main` implementation of `forecast_advice.py`; the changes in that file are limited to optional coordinates, a city label argument, and location-specific headings. The `trip_advisor.py` caller now uses the canonical `start_date`/`end_date` interface rather than the superseded `trip_start`/`trip_end` parameters.

Existing PR #12 regressions must keep passing. New trip-advisor regression cases check the 13°C wording, second-week uncertainty, and city headings. The original 54-test count is superseded by the integrated test suite. A user-reported real Berlin end-to-end API smoke run has now succeeded (see preceding section). That establishes integration success for this case, not independent validation of historical accuracy; the second-city run remains outstanding.

Related discovery evidence: [Accommodation and transit indoor-climate findings](./indoor-temperature-transit-accommodation-2026-10.md). No automatic sleepwear recommendation has been added to the engine.
