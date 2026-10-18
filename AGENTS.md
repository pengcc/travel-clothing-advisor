# AGENTS.md

This repository owns its own product context, research evidence, decisions, and future implementation choices.

## Current phase

Product discovery and problem validation continue where needed. The repository also has an **implemented local MVP and active MVP delivery work**; implementation experiments do not establish product-validation success.

For repository workflow requests, follow [the Workflow Contract](docs/collaboration.md) for stage ownership and authorization. Do not repeat completed discovery before authorized implementation. For unresolved product questions, prioritize:

- evidence-first community research;
- focused product framing;
- representative real-scenario grilling;
- competitor and adjacent-product research;
- explicit separation of verified facts, current hypotheses, accepted decisions, and open questions.

Do not select an application framework, weather provider, AI/ML approach, persistence layer, deployment platform, or other implementation architecture unless a target-owned decision establishes the need and scope; verify current accepted decisions and implementation before changing them.

## Required repository context

For repository-aware work:

1. read this file from current `main`;
2. read `.codex/chatgpt/project-instructions.md` when ChatGPT is the acting environment;
3. read `docs/product-blueprint.md` when product purpose, scope, users, success, or non-goals matter;
4. inspect any newer target-owned research or decision artifact that is directly relevant to the task;
5. verify current repository reality before relying on historical conversation, donor-repository behavior, or remembered project state.

Load only the context needed for the current task. Do not create lifecycle ceremony, persisted task state, or tooling merely because another repository has it.

## Current-turn outcome

Interpret each request by what the current turn should help the user newly understand, decide, validate, or move closer to resolving.

Use an installed discovery capability only when material new alignment, product framing, research, or clarification is actually required. Adequate completed research and prior discovery are reusable evidence. If the current request can be answered directly from that evidence and no material formal discovery work remains, answer it directly rather than manufacturing another workflow, stage, handoff, or investigation.

Evidence boundaries, uncertainty, process state, validation, and next workflow are supporting information rather than default report structure. Surface them when they materially affect the current answer, trust, risk, decision, or requested action. Internal checks do not become user-visible merely because they ran.

A narrow follow-up during unfinished required discovery does not cancel that still-required work. Preserve consequential uncertainty, user decisions, safety or external-effect boundaries, and exact-target constraints where they remain material.

## Installed discovery capabilities

This repository currently owns a deliberately small, discovery-only agent capability set:

- **Task Alignment** — `.codex/project-collaboration/task-alignment.md`
  - use for complex or cross-stage work that needs a stable solution-independent Task Baseline or accepted Task Decisions;
  - do not manufacture a baseline for small direct work.
- **Product Framing** — `.codex/skills/meta/product-framing-review/SKILL.md`
  - use when the meaning of an end-user problem, decision, workflow, answer state, or acceptance boundary needs focused clarification.
- **Grilling** — `.codex/skills/meta/grilling/SKILL.md`
  - use only for broad, branching, or blocking ambiguity;
  - test ambiguity against the smallest representative real traveler scenario.
- **Docs-First Research** — `.codex/skills/meta/docs-first-research/SKILL.md`
  - use when a material conclusion depends on externally variable or authoritative facts;
  - apply `.codex/rules/docs-first-policy.md` for source precedence and claim boundaries.

These capabilities serve discovery and Task Alignment, not implementation-stage routing. Planning/Execution/Review Skills, role router, Project Memory, hooks and dedicated workflow tooling are not installed.

## Donor repository boundary

`pengcc/badminton-club-app`, `pengcc/large-file-upload`, and other projects may be inspected as evidence for reusable working methods or tooling patterns.

They are **not** authorities for this project's product requirements, runtime, architecture, deployment, repository workflow, Project Memory, or implementation choices. Any adopted capability must become target-owned and must justify its own current consumer here.

## Research boundary

When conclusions depend on external facts that can change or require authority—such as weather-data behavior, forecast horizons, climatology, licensing, provider capabilities, thermal-comfort science, or platform constraints—verify them against current authoritative sources through the installed docs-first boundary.

Community posts and user discussions are evidence of user questions, language, anxieties, and workflows; they are not authoritative evidence for meteorological or technical facts.

For product ambiguity, test the smallest representative real travel scenario that exposes the decision. Do not expand clear questions into an unbounded questionnaire or speculative feature list.

## Change and delivery boundary

An explicit `keep local`, `no push`, or `no PR` instruction limits publication; it does not waive independent review or grant merge permission. **Merge, deployment, release, repository visibility/settings changes, retained external-data mutation and other material external effects require separate explicit user authorization.**

Do not add application code, dependencies, CI, deployment/release machinery, repository publication tooling, worktree automation, hooks, Project Memory or a broader Skill tree without demonstrated target-owned need and execution authority.
