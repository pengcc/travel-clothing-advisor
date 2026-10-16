# Travel Clothing Advisor — Product Blueprint

## Status

Current phase: **Product Discovery / Problem Validation**

This document captures the current product problem and validation boundary. It is not an implementation plan or architecture specification.

## Working product intent

Help travelers who are unfamiliar with a destination's climate avoid significant clothing-packing mistakes while keeping luggage practical.

The initial market focus is **Germany**.

## Target users

Primary discovery target:

- travelers coming to Germany who do not already have reliable intuition for local weather and seasonal variation;
- especially travelers whose normal climate differs materially from the destination;
- travelers with limited luggage capacity or a strong desire to avoid unnecessary clothing;
- short-term or occasional users who are unlikely to install and maintain a dedicated wardrobe app.

This target remains a discovery hypothesis and may narrow or expand with evidence.

## Problem / need

A conventional forecast can show temperatures, rain, wind, and daily highs/lows while still leaving a traveler unsure what those conditions mean for packing.

The current hypothesis is that the important anxiety is not primarily fashion or choosing one exact outfit. It is avoiding two asymmetric travel mistakes:

1. **Underpacking risk** — omitting a layer or protection that becomes important during colder, windier, wetter, or later parts of the trip, leading to discomfort or an unplanned purchase.
2. **Overpacking risk** — filling limited luggage with heavy or redundant items that are unnecessary for the likely range of conditions.

Daily variation matters as well. A traveler may leave accommodation in a cool morning, spend a warm sunny afternoon walking outdoors, and return after temperatures fall again. A useful answer must therefore distinguish what is worn from what should simply be carried as a removable layer.

## Current product hypothesis

The product should translate destination weather and climate uncertainty into a small set of practical travel decisions rather than produce a generic weather screen or long packing checklist.

Promising decision outputs to validate include:

- **Must bring** — capabilities or clothing layers that should not be omitted for the credible trip conditions;
- **Safe to omit** — bulky or redundant items that do not appear justified by the credible range;
- **Wear vs carry** — how to handle intra-day changes with removable layers;
- **Main packing risk** — the one or two ways a traveler is most likely to misread the conditions;
- **Confidence / uncertainty** — whether the trip is close enough for a forecast-based answer or still requires a climate-range / packing-envelope answer.

These concepts are product hypotheses, not accepted UI labels or implementation contracts.

## Core user questions to validate

A successful product should help a traveler answer questions such as:

1. What clothing capability would be costly to forget?
2. What bulky clothing can I reasonably leave at home?
3. Will the main difficulty be cold, heat, wind, rain, sun, or day/night variation?
4. What should I wear when leaving, and what should I carry for later?
5. How much can I trust the answer given the time remaining before the trip?

## Product principles under validation

### Risk translation over fashion styling

The primary value hypothesis is reducing packing mistakes, not generating fashionable combinations.

### Whole-trip coverage over one-temperature rules

The relevant unit is the credible range across the trip and across the day, not a fixed mapping such as `15°C -> jacket`.

### Minimal useful coverage

Advice should help cover realistic conditions with a compact clothing set rather than encourage packing for every imaginable edge case.

### Honest uncertainty

A long-range trip should not receive false hourly precision. The output should shift from climate-range planning to forecast-based daily guidance only when the evidence supports that precision.

### Explain the reason

Users should understand why a layer matters—for example wind exposure, a cool evening, rain, or strong daytime warming—rather than receive unexplained clothing labels.

## Discovery evidence to establish

Before committing to an implementation direction, the project should build and review:

- a community-evidence corpus of real traveler questions and recurring anxieties;
- competitor and adjacent-product evidence;
- a representative Germany scenario corpus covering seasons, day/night swings, wind/rain, sunshine, limited luggage, multi-city trips, and relevant exceptions;
- failure examples showing advice that would plausibly cause underpacking, overpacking, or false confidence;
- manual or low-fidelity answer tests demonstrating whether risk-oriented guidance is genuinely more useful than a normal forecast or packing-list generator.

## Current non-goals

During Product Discovery, do not assume the product needs:

- a native mobile app;
- a digital wardrobe;
- fashion or style recommendations;
- AI-generated outfit imagery;
- a general travel packing checklist;
- exact outfit prediction for every user;
- a machine-learning model;
- a specific weather provider;
- a specific application framework, backend, database, hosting provider, or deployment architecture;
- coverage beyond Germany before the initial problem is validated.

## Success boundary for discovery

Product Discovery is strong enough to justify a prototype/engine stage when evidence supports all of the following:

1. the underlying question recurs across meaningful real traveler scenarios rather than being an isolated social-media pattern;
2. the costly mistake is clearer than a generic desire for more weather information;
3. a concise risk-oriented answer changes a packing decision or materially increases confidence;
4. representative scenarios can distinguish useful guidance from unsafe or low-value guidance;
5. the value remains differentiated enough from ordinary weather apps and weather-aware packing-list products to merit further validation.

Failure to establish these conditions is a valid discovery outcome and should prevent premature implementation.

## Open discovery questions

- Which traveler segment experiences the strongest problem: first-time visitors, travelers from warmer climates, carry-on-only travelers, families, long-stay visitors, or another group?
- How much personalization materially improves the answer without creating onboarding cost?
- Which weather/climate variables actually change packing decisions enough to justify inclusion?
- What is the right boundary between destination-wide packing guidance and day-of-trip wear/carry guidance?
- What evidence standard is sufficient to label an item `safe to omit` without creating false confidence?
- What distribution channel best matches this low-frequency, travel-triggered need?

## Implementation state

A **command-line experiment** now exists at `experiments/clothing-rules/trip_advisor.py` using Python's standard library and Open-Meteo. The prototype supports German-city trip dates with a live forecast within 14 calendar days (plus two prior-year references), and a historical ERA5 packing-outlook reference for trips extending beyond that forecast horizon but completely within 30 calendar days. The eight-year history is *not* a 15–30 day forecast, calibrated probability model, or proven garment-packing recommendation.

A local web UI now exists at `web/`. Under Issue #19’s Phase 2A scope, personal trips fully within the next 14 German calendar days use real temperature-only forecasts and the experimental six-level clothing model. Featured-city journeys remain explicitly simulated; live 15–30-day historical reference and shared daily snapshots remain deferred. There is no published product, automated daily update, deployment, database, dedicated CI, selected AI/ML architecture, or demonstrated product-validation success. Implementation experiments do not change this document's discovery success boundary.
