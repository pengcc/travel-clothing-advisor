# Implementation Planning Quality — Travel

This is **subordinate quality guidance** adapted from Badminton's Implementation Planning Contract. The sole Travel stage, Plan location/version, Review, Approval, PR and external-action authority is docs/collaboration.md. Task Alignment and accepted decisions remain the source of task meaning. This document creates no additional lifecycle, Plan PR or Task State.

## When a Plan earns its cost

Use a formal Plan for a material cross-layer interaction, unresolved consequential implementation trade-off, complex risk, or a user request explicitly to plan. For a small fully specified change, directly authorized implementation may proceed without a new Plan. Reuse adequate current work instead of restating it.

## An executable Plan

In proportion to the actual task, identify:
- current Issue, accepted goal and boundaries (reference rather than rewrite product decisions);
- chosen approach and concrete trade-offs versus simpler alternatives;
- affected files or bounded discovery areas and the work/order/dependencies;
- observable acceptance and negative/failure behavior at the relevant user or API boundary;
- target-owned meaningful test/check commands and any evidence not available yet;
- material risk, rollback/recovery, scope drift and explicit STOP conditions;
- what the independent implementer and reviewer need without access to this chat.

Do not invent a tool, environment, retained state, general framework, or test just to complete a template. The actual repository and Makefile determine validation; for application work use targeted Python tests and make test as appropriate, not Badminton pnpm scripts. Prefer tests for meaningful regression signals, not prose or internal implementation trivia. Research externally only for a consequential fact that current target evidence cannot establish.

## Plan authoring versus independent review

Apply the Issue versioned-comment and current-pointer rules in docs/collaboration.md. A **Plan-only request ends with the Plan**, not Review, Approval, implementation or a PR. Formal Plan Review is a distinct, inspectable invocation against the exact current Issue Plan version and target evidence. Examine goal alignment, authority, completeness, smallest sufficient solution, regressions, validation realism, rollback and executability. Return one review verdict and actionable corrections. Corrections and material version/review/approval freshness follow docs/collaboration.md, never an unrelated donor Task Workspace.

A clean review is **not** user approval or execution authorization. Preserve explicit Approval, publication and merge boundaries owned by Travel.
