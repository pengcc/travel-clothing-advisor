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

Provide clear, sufficient, and reviewable substantive results centered on the user's current goal, including the key information needed to understand the result, make a judgment, or take action.

For consequential decisions or approvals, explain what is being decided, the main rationale, key trade-offs, and practical implications before asking the user to decide.

When indicating a concrete next task for another agent or actor, provide a directly usable instruction rather than only a workflow label or sequence. Include the exact target or result reference, intended outcome, and material scope or authority boundaries in proportion to the task. Do not invent a next task, handoff artifact, or permission for work that still requires separate authorization.

Use an installed discovery capability only when material new alignment, product framing, research, or clarification is actually required. Adequate completed research and prior discovery are reusable evidence. If the current request can be answered directly from that evidence and no material formal discovery work remains, answer it directly rather than manufacturing another workflow, stage, handoff, or investigation.

Evidence boundaries, uncertainty, process state, validation, and next workflow are supporting information rather than default report structure. Surface them when they materially affect the current answer, trust, risk, decision, or requested action. Internal checks do not become user-visible merely because they ran.

A narrow follow-up during unfinished required discovery does not cancel that still-required work. Preserve consequential uncertainty, user decisions, safety or external-effect boundaries, and exact-target constraints where they remain material.

## Installed discovery capabilities

This repository currently owns a deliberately small, discovery-only agent capability set:

- **Task Alignment** — `.codex/project-collaboration/task-alignment.md`
  - use for complex or cross-stage work that needs a stable solution-independent Task Baseline or accepted Task Decisions;
  - do not manufacture a baseline for small direct work.
- **Product Framing** — `.agents/skills/product-framing-review/SKILL.md`
  - use when the meaning of an end-user problem, decision, workflow, answer state, or acceptance boundary needs focused clarification.
- **Grilling** — `.agents/skills/grilling/SKILL.md`
  - use only for broad, branching, or blocking ambiguity;
  - test ambiguity against the smallest representative real traveler scenario.
- **Docs-First Research** — `.agents/skills/docs-first-research/SKILL.md`
  - use when a material conclusion depends on externally variable or authoritative facts;
  - apply `.codex/rules/docs-first-policy.md` for source precedence and claim boundaries.

These discovery capabilities remain available for genuinely unresolved product or external-fact questions. They do not own delivery stage or authorization.

## Delivery capability adapters

The following target-adapted repository Skills may be called for the **specific task requested**. They consume the **existing sole Workflow Contract** in docs/collaboration.md; they do not install another Issue lifecycle or automatically chain stages:

- **Plan Authoring / Formal Plan Review** — .agents/skills/plan-with-context/SKILL.md. Author a versioned Issue plan and stop, or independently review an existing version when asked. Plan quality is supported by .codex/project-collaboration/contracts/implementation-planning.md.
- **Execute Plan / direct bounded delivery** — .agents/skills/execute-plan/SKILL.md. Distinguish a current reviewed-and-approved Plan from a directly authorized bounded task; use the relevant input reference, target validation and one authorized change PR.
- **Implementation Review / Re-review** — .agents/skills/implementation-review/SKILL.md. Review the exact actual PR with .codex/project-collaboration/contracts/implementation-review.md; actionable fixes belong to the same PR and require a separate implementation request.

For engineering changes, apply the focused target-owned quality principles in .codex/rules/engineering-quality-principles.md; actual validation commands and stage permissions still come from the target repository and its Workflow Contract.

The three discovery Skills and three delivery Skills live directly under `.agents/skills/`, the repository discovery location documented in [OpenAI Build skills](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills) (checked 2026-10-18). Each has Skill discovery metadata. The explicit routing above retains task triggers and boundaries. No installer or registration framework is required.

Skill file presence does **not** prove they were loaded or exercised by a fresh Codex session. Do not claim an unrun invocation or validation passed. Do not require the full Skill set for a single small task. No role router, Project Memory, Task State, publication scripts, hooks or dedicated CI is added by this adoption.

**Selected donor provenance:** Badminton main cf90c34d3b62c66cfc8865e861c11d2481cd1185, adapted under Travel ownership for Issue #48. Donor files and the open donor adoption guide are not Travel runtime authorities.

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
