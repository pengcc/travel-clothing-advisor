# Docs-First Policy

This policy owns source priority, conflict handling, and external-source safety for this repository's discovery and later technical work. `docs-first-research` owns the concrete research workflow that applies it.

## Core principle

Use the source that is authoritative for the kind of claim being made. Model memory may support reasoning and search direction, but it must not override current project reality or stronger evidence.

## Claim-sensitive source priority

### External technical, meteorological, scientific, legal, provider, or platform facts

Prefer, in order:

1. official or primary sources;
2. current target-repository evidence;
3. high-quality secondary sources;
4. model knowledge only as hypothesis or search direction.

Examples of primary sources include official documentation, API references, datasets, methodology papers, release notes, licensing terms, government or meteorological-agency material, and maintainer-owned repositories.

### User-need, language, anxiety, workflow, and behavior claims

Direct user/community evidence may be the primary observation source. Examples include traveler questions, comments, interviews, support discussions, and community posts.

Treat these sources as evidence of what people ask, misunderstand, fear, or do. Do not use them as authority for meteorological, medical, technical, legal, or safety facts.

### Project product and decision facts

Current `pengcc/travel-clothing-advisor` repository artifacts and explicit user decisions outrank donor repositories, historical conversations, competitor behavior, and model memory.

## Conflict handling

- If stronger authoritative evidence conflicts with model memory, the stronger evidence wins.
- If authoritative external evidence conflicts with current project assumptions, report the conflict rather than silently rewriting project intent.
- If community anecdotes disagree, preserve the disagreement and avoid presenting one anecdote as a population-wide fact.
- If evidence is too weak for a material recommendation, state the uncertainty and narrow the claim.

## Research boundaries

Use `docs-first-research` when a conclusion materially depends on externally variable or authoritative facts.

For product discovery, distinguish at least:

```txt
Observed user evidence
Authoritative external fact
Project hypothesis
Accepted project decision
Inference / open question
```

Do not blend these categories into one confidence claim.

## External tooling and skill references

Donor repositories and external skills are reference candidates only. Before adapting a pattern, check:

- provenance and exact source revision when available;
- trigger and boundary fit;
- duplication with current target-owned capabilities;
- assumptions about other skills, Project Memory, hooks, scripts, runtimes, or tooling;
- mutation, external-action, secret, and safety implications;
- whether the capability has a real current consumer in this repository.

Do not copy a dependency tree merely because one useful skill references it. Rewrite adopted semantics for this repository and keep absent capabilities absent.

## Adoption provenance

Adapted for this repository from the docs-first policy and research boundaries in `pengcc/badminton-club-app` at revision `56d6251bda1d9a63799267f2300f24e9ac192c50`.
