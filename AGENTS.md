# AGENTS.md

This repository owns its own product context, research evidence, decisions, and future implementation choices.

## Current phase

Product discovery and problem validation continue where needed. The repository also has an **implemented local MVP and active MVP delivery work**; implementation experiments do not establish product-validation success.

For Issue, Plan, Review, Approval, Implementation, PR Review, Fix and Merge requests, read [the Workflow Contract](docs/collaboration.md) first. It is the sole workflow authority. Resolve the current task stage and its authority before acting; approved implementation does not require repeating completed discovery. For unresolved product questions, prioritize:

- evidence-first community research;
- focused product framing;
- representative real-scenario grilling;
- competitor and adjacent-product research;
- explicit separation of verified facts, current hypotheses, accepted decisions, and open questions.

Do not select an application framework, weather provider, AI/ML approach, persistence layer, deployment platform, or other implementation architecture unless a target-owned decision establishes the need and scope; verify current accepted decisions and implementation before changing them.

## Required repository context

For repository-aware work:

1. read this file from current `main`;
2. read `.codex/chatgpt/project-instructions.md` when ChatGPT is the acting environment, and `docs/collaboration.md` for workflow-stage requests;
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

These capabilities are target-owned adaptations for discovery and intent. `docs/collaboration.md` governs the mandatory collaboration workflow; it is not a Skill or a second Task Baseline. Planning, Execution and Review Skills, a role router, Project Memory, hooks and dedicated workflow tooling remain deferred. Do not infer their installation from donor repositories or historical terminology.

## Donor repository boundary

`pengcc/badminton-club-app`, `pengcc/large-file-upload`, and other projects may be inspected as evidence for reusable working methods or tooling patterns.

They are **not** authorities for this project's product requirements, runtime, architecture, deployment, repository workflow, Project Memory, or implementation choices. Any adopted capability must become target-owned and must justify its own current consumer here.

The initial discovery capability set was adapted from `pengcc/badminton-club-app` revision `56d6251bda1d9a63799267f2300f24e9ac192c50`, with dependencies not installed in this repository intentionally removed. The Task Alignment real-outcome check and the current-turn outcome principle were subsequently refreshed from donor revision `a7e4743e471209c294214ff6617bb7980606f263` without adopting its role router or operating-contract system.

## Research boundary

When conclusions depend on external facts that can change or require authority—such as weather-data behavior, forecast horizons, climatology, licensing, provider capabilities, thermal-comfort science, or platform constraints—verify them against current authoritative sources through the installed docs-first boundary.

Community posts and user discussions are evidence of user questions, language, anxieties, and workflows; they are not authoritative evidence for meteorological or technical facts.

For product ambiguity, test the smallest representative real travel scenario that exposes the decision. Do not expand clear questions into an unbounded questionnaire or speculative feature list.

## Current product direction

The working hypothesis is that travelers unfamiliar with German weather mainly need protection from packing mistakes rather than fashion styling or a more detailed weather forecast.

Current discovery should test whether useful guidance can be organized around concepts such as:

- what must be covered for the trip;
- what can safely be omitted from limited luggage;
- what should be worn versus carried as a removable layer;
- where forecast or climate uncertainty prevents a precise answer.

These are current product hypotheses, not an implementation contract.

## Change and delivery boundary

Follow [docs/collaboration.md](docs/collaboration.md) for Issue-first stage locations, planning and approval gates, one delivery branch/PR, independent exact-target review, same-PR fixes and closeout. A planning-only proposal never creates a PR; an authorized documentation implementation does. Small bounded changes may skip formal planning, never independent PR review or separate merge authority.

Ordinary requested repository changes normally include one review-ready delivery PR once coherently implemented. An explicit `keep local`, `no push`, `no PR`, or equivalent constraint opts out of publication; it does not waive review or authorize merge. Use a dedicated branch unless the user explicitly authorizes another path. The initial root bootstrap on `main` was a historical exception.

**Merge remains a separate explicit user action.** Deployment, release, repository visibility/settings changes, retained external-data mutation and other material external effects also remain separately authorized.

The Workflow Contract is documentation, not installed publication machinery. No dedicated PR publication Skill, hooks or `.repo-tools` are installed; use available GitHub capabilities directly within the contract.

Do not create application code, dependencies, CI, deployment, release machinery, repository publication tooling, worktree automation, hooks, Project Memory or a broader agent skill tree without a demonstrated target-owned need and the applicable execution authority.
