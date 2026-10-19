---
name: grilling
description: Resolve material product or task ambiguity with evidence-first questions and focused traveler scenarios, without creating another workflow.
---

# Grilling

Use this capability when the user asks to be grilled, or when discovery is blocked by broad, branching, decision-heavy, or baseline-blocking ambiguity.

`grilling` resolves only ambiguity that blocks a safe or useful next step. It must not turn a clear task into an interview or expand Product Discovery into an unbounded questionnaire.

## Evidence first

Before asking a question, inspect the available evidence relevant to the uncertainty, including as applicable:

```txt
AGENTS.md
docs/product-blueprint.md
current Task Baseline or accepted Task Decisions
current target-owned research
provided user context
relevant community evidence
```

Do not ask the user for an answer that existing evidence can provide.

If the uncertainty depends on an external factual claim, apply `docs-first-research` before asking the user to decide around an unverified premise.

## Real-scenario grilling

When ambiguity concerns product behavior, a user workflow, confidence, information boundaries, or what advice should mean, test it against the smallest representative real traveler scenario that exposes the actual decision.

Examples of useful scenario pressure include:

- limited carry-on space;
- warm daytime sun with a cold evening;
- wind or rain changing the value of an outer layer;
- a trip too far away for a reliable daily forecast;
- multi-city conditions that make a simple average misleading;
- a recommendation that may cause either unnecessary bulk or costly underpacking.

Do not invent a large synthetic persona system when one concrete case is enough.

## Clarification discipline

Order questions by dependency. Ask the potentially invalidating parent question before lower-level choices.

For each material question:

- give the recommended direction when evidence supports one;
- explain why the answer changes the product boundary or next step;
- state the consequence of the alternative;
- stop opening dependent branches once the blocker is resolved.

Ask one question at a time for dependent or high-impact decisions. A small group is acceptable when questions are independent and at the same decision level.

## Task Baseline impact

When grilling clarifies or challenges a Task Baseline, report:

```txt
Task Baseline impact:
- Fields clarified:
- Clarified conclusions:
- Remaining blocker:
- Amendment required: yes | no
```

Do not silently rewrite an established Task Baseline. Verified contradiction or explicit user correction should return to Task Alignment.

## Stop and return

Return control when:

- the blocking ambiguity is resolved;
- the owning discovery/research workflow can continue safely;
- further questions are no longer high-leverage; or
- progress genuinely requires user input.

Grilling does not authorize implementation, planning, publication, repository settings changes, or acceptance of a product decision by itself.

## Adoption provenance

Adapted for this repository from `pengcc/badminton-club-app` `.codex/skills/meta/grilling/SKILL.md` at revision `56d6251bda1d9a63799267f2300f24e9ac192c50`. Role-routing and Project Memory dependencies were intentionally removed because they are not installed here.
