# Docs-First Research

Use this capability when a project conclusion depends on externally variable, authoritative, provider-specific, scientific, meteorological, legal, licensing, compatibility, or other facts that current repository evidence does not establish.

For this project's Product Discovery phase, also use it when competitor or market claims require current verification rather than memory.

## Purpose

Verify consequential external facts, expose uncertainty, and keep product hypotheses separate from evidence.

## Evidence order

Apply `.codex/rules/docs-first-policy.md`.

Before external research, inspect the relevant current project evidence, normally including as applicable:

```txt
AGENTS.md
docs/product-blueprint.md
current target-owned research or decision artifacts
provided context
```

Do not research externally merely because a task is technical. If current project evidence already establishes the material fact, use it and say so.

## Discovery-specific source handling

For claims about what travelers ask, fear, misunderstand, or need, direct community/user evidence is valid primary observational evidence.

For claims about weather behavior, forecast horizons, climatology, thermal comfort, APIs, licensing, safety, or provider behavior, prefer authoritative primary sources.

Never treat a Reddit, Xiaohongshu, forum, travel blog, competitor marketing page, or isolated anecdote as meteorological or technical authority merely because it describes the same scenario.

## Workflow

1. State the exact claim or decision that requires external evidence.
2. Identify the strongest relevant source class under the docs-first policy.
3. Check current authoritative sources when they exist.
4. Use community or secondary evidence only for the claims it can actually support.
5. Compare findings with current repository assumptions and product hypotheses.
6. Report conflicts, weak evidence, and unresolved uncertainty explicitly.
7. Recommend the smallest safe next discovery step; do not silently convert research into an accepted product decision.

## Competitor research

When researching competitors or adjacent products, distinguish:

```txt
Verified current capability
Marketing claim
Observed product behavior
Community/user reaction
Inference about differentiation
```

Do not infer product-market fit, user satisfaction, adoption, or commercial success from feature presence alone.

## Degraded research mode

If authoritative sources cannot be accessed, state the limitation and identify what was actually checked. Weak evidence may support a provisional discovery hypothesis, but it must not be presented as a verified high-impact fact.

## Output

Keep output proportional, but include:

```txt
Research depth:
Claim / decision being verified:
Project files checked:
Sources checked:
Findings:
Impact on current hypothesis:
Recommendation:
Uncertainty / conflicting evidence:
Durable artifact candidate: yes | no
```

`Durable artifact candidate` means the finding may deserve a target-owned research or decision document. This repository currently has no Project Memory system; do not pretend one is installed.

## Boundaries

This capability does not authorize implementation, dependency installation, deployment, repository settings changes, publication, or acceptance of a product decision. It does not create a long-lived source of truth by itself.

## Adoption provenance

Adapted for this repository from `pengcc/badminton-club-app` `.codex/skills/meta/docs-first-research/SKILL.md` at revision `56d6251bda1d9a63799267f2300f24e9ac192c50`. Role-routing and Project Memory dependencies were intentionally removed because they are not installed here.
