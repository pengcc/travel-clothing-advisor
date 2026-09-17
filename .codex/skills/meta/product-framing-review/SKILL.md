# Product Framing

Use this capability when end-user product behavior needs focused framing during Product Discovery or later product work.

Product Framing describes the user's problem, question, goal, decision, workflow, and smallest useful outcome. UI components, fields, tabs, APIs, data models, frameworks, and styling are implementation mechanics and must not substitute for product meaning.

## Authority boundary

Current `docs/product-blueprint.md`, an applicable current Task Baseline, explicit user corrections, and accepted Task Decisions outrank this workflow's provisional conclusions.

Product Framing does not establish or amend a Task Baseline, accept product decisions, create an implementation plan, execute changes, or authorize publication.

## Required context

Inspect only the relevant current evidence, normally including:

```txt
AGENTS.md
docs/product-blueprint.md
applicable Task Baseline / Task Decisions
current target-owned research and scenario evidence
provided user context
```

Separate verified evidence, current hypotheses, accepted decisions, and open questions.

Use `docs-first-research` when framing depends on an unverified external fact. Use `grilling` when product ambiguity is broad, branching, or decision-heavy.

## Focused framing check

For one behavior, output, or workflow, answer first:

> What real problem, question, risk, or decision brings the traveler here?

Then use a concise check:

```txt
Product Framing Check:
- Purpose statement:
- Target traveler / context:
- User decision or anxiety:
- Evidence supporting the need:
- Valid answer meaning:
- Invalid / unsupported / uncertain states:
- Smallest useful outcome:
- Non-goals:
- Acceptance boundary:
- Open questions:
- Readiness: ready for further discovery | blocked | exploratory-only
```

Do not manufacture a full PRD for a narrow question.

## Broader product review

When reviewing the overall product hypothesis or a major product area, use:

```txt
Product Framing Review:
- Product purpose summary:
- Target users / segments under validation:
- Core user anxieties / decisions:
- Core workflows or moments:
- Evidence established:
- Hypotheses still under validation:
- Invalid / partial / unsupported states:
- Product principles:
- Non-goals / out of scope:
- Acceptance boundary:
- Open questions:
- Readiness: continue discovery | ready for prototype framing | blocked
```

## Discovery rules

1. Start from the real travel decision, not a proposed feature.
2. Prefer evidence of costly mistakes or uncertainty over generic interest in a feature.
3. Separate `what to pack`, `what to wear now`, and `what to carry for later` when the real scenario distinguishes them.
4. Treat confidence and forecast/climate uncertainty as product meaning, not decoration.
5. Test attractive ideas against representative scenarios before promoting them into scope.
6. Do not infer that an existing competitor feature proves users need it.
7. Do not treat a long checklist as useful merely because it is comprehensive.

## Completion check

Before finishing, confirm that the output:

- states the user's real problem or decision rather than a mechanism;
- distinguishes evidence from hypotheses;
- identifies unsupported or uncertain answer states;
- defines a smallest useful acceptance boundary; and
- does not silently move Product Discovery into implementation.

## Adoption provenance

Adapted for this repository from `pengcc/badminton-club-app` `.codex/skills/meta/product-framing-review/SKILL.md` at revision `56d6251bda1d9a63799267f2300f24e9ac192c50`. Role-routing, Project Memory, planning, and implementation dependencies were intentionally removed because they are not installed here.
