# AGENTS.md

This repository owns its own product context, research evidence, decisions, and future implementation choices.

## Current phase

The project is currently in **Product Discovery / Problem Validation**.

The default work boundary is research and product clarification, not implementation. Prioritize:

- evidence-first community research;
- focused product framing;
- representative real-scenario grilling;
- competitor and adjacent-product research;
- explicit separation of verified facts, current hypotheses, accepted decisions, and open questions.

Do not select an application framework, weather provider, AI/ML approach, persistence layer, deployment platform, or other implementation architecture unless a later target-owned decision establishes the need and scope.

## Required repository context

For repository-aware work:

1. read this file from current `main`;
2. read `.codex/chatgpt/project-instructions.md` when ChatGPT is the acting environment;
3. read `docs/product-blueprint.md` when product purpose, scope, users, success, or non-goals matter;
4. inspect any newer target-owned research or decision artifact that is directly relevant to the task;
5. verify current repository reality before relying on historical conversation, donor-repository behavior, or remembered project state.

Load only the context needed for the current task. Do not create lifecycle ceremony, persisted task state, or tooling merely because another repository has it.

## Donor repository boundary

`pengcc/badminton-club-app`, `pengcc/large-file-upload`, and other projects may be inspected as evidence for reusable working methods or tooling patterns.

They are **not** authorities for this project's product requirements, runtime, architecture, deployment, repository workflow, Project Memory, or implementation choices. Any adopted capability must become target-owned and must justify its own current consumer here.

## Research boundary

When conclusions depend on external facts that can change or require authority—such as weather-data behavior, forecast horizons, climatology, licensing, provider capabilities, thermal-comfort science, or platform constraints—verify them against current authoritative sources.

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

This initial bootstrap may establish the repository directly on `main`. After bootstrap, ordinary Git-visible product, research, tooling, or implementation changes should use a dedicated branch unless the user explicitly authorizes another path.

Do not create application code, dependencies, CI, deployment, release machinery, repository publication tooling, worktree automation, hooks, or a full agent skill tree without a demonstrated target-owned need.

Repository settings, visibility changes, deployment, publication, retained external data mutation, and other material external effects require explicit authority.
