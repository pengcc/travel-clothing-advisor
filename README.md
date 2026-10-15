# Travel Clothing Advisor

A product-discovery project exploring how to help travelers who are unfamiliar with a destination's climate avoid costly clothing-packing mistakes.

The initial market focus is Germany. The current hypothesis is that the main user need is not another weather forecast or fashion recommendation, but a clear translation from weather/climate variability into practical packing risk guidance: what must be covered, what can safely be left at home, and what should be carried as a removable layer during the day.

## Current phase

**Product Discovery / Problem Validation**, with a runnable command-line prototype (not a released service).

Current work should focus on:

- real community evidence;
- product framing and problem boundaries;
- competitor research;
- representative travel scenarios and failure cases;
- validating whether risk-oriented packing guidance is meaningfully better than ordinary weather or packing-list tools.

## Prototype now available

The Python standard-library CLI at `experiments/clothing-rules/trip_advisor.py` accepts German cities, trip dates, and optional cold/hot preference. Fully forecast-covered trips within 14 calendar days use Open-Meteo forecasts, with two past-year references. Trips with any day outside that horizon but wholly within 30 calendar days use eight years of fixed-model historical reanalysis as a **packing reference**, not a day-by-day forecast. See `experiments/clothing-rules/README.md` for commands and constraints.

The recommendation quality remains experimental. A local, fixture-only Phase 1 web UI is now available; it does not call the CLI or any weather service. There is no deployed daily-update service, final production framework, AI architecture, or validated weather/clothing accuracy.

## Run the Phase 1 web UI

Requires Python 3.9+ with Europe/Berlin timezone data; no runtime packages to install.

```sh
python3 -m web.server
```

Open http://127.0.0.1:8000. All advice is clearly labelled simulation. See [web/README.md](web/README.md) for fixture controls, tests, contracts and Phase 2 integration points. See [visual verification](docs/verification/phase1/README.md) for actual screenshots and V5 comparison.

See [`docs/product-blueprint.md`](docs/product-blueprint.md) for the current product-discovery boundary.
