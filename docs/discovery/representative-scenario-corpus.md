# Representative Scenario Corpus — Product Validation

## Status

Discovery test corpus derived from current community evidence.

These scenarios are **synthetic test cases**, not claims that a specific traveler or weather event occurred exactly as written. They exist to pressure-test product meaning, uncertainty, and failure boundaries.

Community evidence source: `docs/discovery/community-evidence-corpus.md`.

## How to use this corpus

A scenario is useful when it can expose whether a candidate answer:

- resolves a real packing decision;
- causes overpacking or underpacking;
- hides uncertainty;
- asks for personalization that does not change the decision;
- confuses `pack`, `wear now`, and `carry for later`;
- or relies on a single temperature number when the trip decision depends on a wider exposure range.

Do not turn every scenario field into a mandatory onboarding question. Inputs should earn their place by changing the answer or confidence.

## Scenario set

### S01 — Warm-climate traveler in early spring

**Evidence anchors:** E03, E04

**Context**
- Traveler comes from a warm / tropical climate.
- Germany trip spans late March into April.
- Two cities; normal sightseeing; limited desire to buy dedicated cold-weather gear.

**Real decision**
- Is a heavy winter / down jacket necessary, or can a lighter weatherproof outer layer plus removable insulation cover the trip?

**Pressure**
- The answer must acknowledge uncertainty without defaulting to “bring everything.”
- Cold sensitivity may matter, but should not automatically justify the bulkiest garment.

**Failure signals**
- Recommends leaving all warm layers at home.
- Recommends a heavy winter coat solely because “Germany is cold.”
- Gives a long generic checklist without resolving the outerwear decision.

---

### S02 — June exchange stay with luggage-choice pressure

**Evidence anchors:** E02

**Context**
- Several-week stay in Hamburg in June.
- Laundry is available with a host family.
- Traveler can choose between a small 8 kg suitcase and adding a 23 kg checked bag.

**Real decision**
- Does clothing uncertainty actually justify another checked suitcase?
- Are boots necessary, or can comfortable everyday shoes cover the likely trip use?

**Pressure**
- Duration alone should not force more clothes when laundry reduces quantity needs.
- The system must distinguish “possible useful item” from “worth paying / carrying an extra bag for.”

**Failure signals**
- Produces a large quantity list that ignores laundry.
- Treats footwear fashion as equivalent to weather capability.
- Cannot say what is safe to leave out.

---

### S03 — Summer trip where averages did not answer the question

**Evidence anchors:** E10, E13

**Context**
- One-week to multi-city summer trip.
- Traveler has already checked average temperatures.
- Traveler prefers light luggage and is anxious about forgetting something.

**Real decision**
- Which small set covers plausible warm, cool, wet, and indoor/outdoor situations without turning into a four-season suitcase?

**Pressure**
- “Summer” must not collapse the answer to shorts and T-shirts.
- “Variable weather” must not collapse the answer to pack everything.

**Failure signals**
- Repeats average temperatures.
- Gives exhaustive categories without a minimum set.
- Cannot identify the single most costly omission.

---

### S04 — Early September, packed list already exists

**Evidence anchors:** E01

**Context**
- Berlin + Munich.
- Traveler already has pants / skirts, mixed tops, cardigan and a light jacket.
- Concern is whether the season feels like late summer, chilly autumn, or both.

**Real decision**
- Is the current set already sufficient?
- What should be worn in the morning versus carried for later?
- Is another heavier layer actually justified?

**Pressure**
- The useful answer may be “your current set is enough, but carry X,” not another shopping list.

**Failure signals**
- Ignores the clothes already owned / packed.
- Adds redundant outerwear without identifying the risk it covers.
- Does not distinguish wear from carry.

---

### S05 — September travel-light decision

**Evidence anchors:** E08, E09

**Context**
- Short Berlin / Germany trip in September.
- Traveler explicitly wants to travel light.
- Average temperatures have already been checked.

**Real decision**
- Which clothing categories are non-negotiable, and which bulky items can reasonably stay home?

**Pressure**
- This is a direct test of `Must bring` vs `Safe to omit`.
- A `Safe to omit` statement needs a stronger confidence basis than “probably unnecessary.”

**Failure signals**
- “Bring a bit of everything.”
- Lists every possible season.
- Uses false precision to justify leaving a critical capability behind.

---

### S06 — Early October city trip with delayed laundry

**Evidence anchors:** E06

**Context**
- Munich + Berlin.
- Family sightseeing, mostly urban.
- No laundry access for about a week.
- Traveler is choosing between mesh running shoes and less-comfortable leather shoes.

**Real decision**
- How many repeatable clothing pieces are justified before laundry?
- Does wet-weather footwear capability outweigh walking comfort enough to change the shoe choice?

**Pressure**
- Quantity and footwear are separate decisions.
- The answer should identify when one pair is sufficient and when a second pair earns the space.

**Failure signals**
- Solves footwear by brand or style rather than capability and use.
- Ignores walking volume.
- Treats no-laundry as justification for an unlimited clothing count.

---

### S07 — Mid-October capsule that may be too winter-heavy

**Evidence anchors:** E07

**Context**
- Traveler has already assembled an autumn capsule.
- Concern is whether it is too winter-like or not warm / weatherproof enough.

**Real decision**
- Which heavy item is actually doing unique work?
- Can one layer be removed without creating a credible cold / wet failure?

**Pressure**
- Direct overpacking test.
- The system should explain redundancy between layers rather than simply score each item individually.

**Failure signals**
- Keeps every warm item “just in case.”
- Removes the only layer covering a credible exposure.
- Cannot explain why two garments are redundant.

---

### S08 — January week: known cold, unknown minimum set

**Evidence anchors:** E05

**Context**
- One week in Frankfurt in January.
- Traveler already knows the trip will be cold.
- Main uncertainty is which specific clothing capabilities matter.

**Real decision**
- What is the minimum cold-weather set that should not be omitted?
- Which extra winter items are optional rather than necessary?

**Pressure**
- This scenario tests whether the product adds value when season-level weather knowledge is already obvious.

**Failure signals**
- Merely says “dress warmly.”
- Creates a full winter wardrobe instead of a minimal coverage set.
- Cannot explain the role of each required layer.

---

### S09 — First-ever winter exposure

**Evidence anchors:** E14

**Context**
- Traveler has never experienced winter.
- Unsure what makes footwear suitable and what outerwear properties matter.
- Destination city is not yet fixed.

**Real decision**
- Which **capabilities** should the traveler seek in shoes and outerwear, independent of brand?

**Pressure**
- Product language must work for someone who lacks garment-category intuition.
- Brand shopping advice is secondary to explaining functional needs.

**Failure signals**
- Assumes the user understands winter-shoe terminology.
- Recommends brands without explaining capability.
- Gives a city-specific answer despite city uncertainty.

---

### S10 — Four-week trip with periodic laundry

**Evidence anchors:** E11

**Context**
- Multi-week Germany trip by train.
- Laundry roughly weekly.
- Traveler wants practical luggage, not a fresh outfit for every day.

**Real decision**
- How many repeatable base pieces are sufficient between laundry cycles?
- Which outer layers serve the whole trip rather than multiplying by day count?

**Pressure**
- Tests quantity logic separately from weather capability.
- A four-week trip should not mechanically generate four weeks of clothing.

**Failure signals**
- Scales garment quantity linearly with trip length.
- Ignores laundry cadence.
- Recommends bulky duplicates that perform the same function.

---

### S11 — Multi-city trip with mixed exposure

**Evidence anchors:** E01, E03, E08

**Context**
- Traveler visits more than one German city.
- Some days are long outdoor sightseeing days; others are mostly indoor / transit.
- Conditions differ enough that one “trip average” is misleading.

**Real decision**
- What compact set covers the credible range across cities?
- Which item should be carried only on higher-exposure days?

**Pressure**
- Tests whole-trip coverage without packing independently for each city.

**Failure signals**
- Averages away the coldest / wettest meaningful exposure.
- Creates separate wardrobes per city.
- Cannot identify when one removable layer bridges the variation.

---

### S12 — Same weather, different cold tolerance

**Evidence anchors:** E07, E09

**Context**
- Two travelers share the same itinerary and weather.
- One tends to feel cold easily; the other runs warm.

**Real decision**
- Which recommendation changes because of sensitivity, and which capabilities remain trip-level requirements for both?

**Pressure**
- Personalization should alter only the decisions it materially affects.

**Failure signals**
- Duplicates the entire packing list based on a single preference.
- Ignores sensitivity when it changes the need for insulation.
- Treats subjective comfort as authority to ignore rain / wind exposure.

## Coverage matrix

| Dimension | Covered scenarios |
| --- | --- |
| Warm-origin / unfamiliar climate | S01, S02, S09 |
| Spring transition | S01 |
| Summer | S02, S03 |
| Early autumn | S04, S05 |
| Mid / late autumn | S06, S07 |
| Winter | S08, S09 |
| Carry-on / luggage pressure | S02, S03, S05, S07 |
| Laundry / duration | S02, S06, S10 |
| Footwear | S02, S06, S09 |
| Wear vs carry | S04, S11 |
| Multi-city | S04, S06, S11 |
| Cold sensitivity | S01, S12 |
| Overpacking pressure | S02, S05, S07, S10 |
| Underpacking pressure | S01, S03, S08, S09 |
| Uncertainty / unsupported state | S01, S05, S09, S11 |

## Corpus acceptance boundary

This is a **seed validation corpus**, not a fixed regression suite or product requirement.

It is adequate for the next discovery step if it can:

1. expose materially different packing decisions rather than cosmetic variations;
2. pressure both overpacking and underpacking failure modes;
3. include cases where the right answer may be to narrow or withhold a recommendation;
4. test whether personalization changes the decision enough to justify collecting that input; and
5. prevent a candidate answer format from looking good only on one easy transitional-weather example.

New evidence may add, merge, split, or retire scenarios. The scenario IDs and exact fixtures are evidence instruments, not permanent product requirements.
