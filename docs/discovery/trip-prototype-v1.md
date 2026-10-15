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

## Integration with merged PR #12 (2026-10-15)

This prototype was originally branched before PR #12, which added trip-date scoping, a 13°C threshold copy fix, and correct forecast lead-time warnings. The current PR's reconciliation uses the latest `main` implementation of `forecast_advice.py`; the changes in that file are limited to optional coordinates, a city label argument, and location-specific headings. The `trip_advisor.py` caller now uses the canonical `start_date`/`end_date` interface rather than the superseded `trip_start`/`trip_end` parameters.

Existing PR #12 regressions must keep passing. New trip-advisor regression cases check the 13°C wording, second-week uncertainty, and city headings. The original 54-test count is superseded by the integrated test suite. The new Geocoding + Historical APIs still need a real connected smoke run before their live data are trusted.

Related discovery evidence: [Accommodation and transit indoor-climate findings](./indoor-temperature-transit-accommodation-2026-10.md). No automatic sleepwear recommendation has been added to the engine.
