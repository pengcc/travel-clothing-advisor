---
name: plan-with-context
description: Author or independently review an executable implementation Plan for a Travel GitHub Issue, storing and reviewing the exact Issue version without creating a Plan PR.
---

# Travel Plan With Context

Use when the user **explicitly asks to draft/revise an Implementation Plan** or to **independently review an existing Plan**. These are separately selected tasks. This Skill is adapted from Badminton's plan-with-context; it deliberately has **no** terminal-closeout, Task Workspace, persisted-plan, Project Memory or automatic next-stage owner.

## Sources, authority and output location

Read current AGENTS.md, docs/collaboration.md, .codex/project-collaboration/task-alignment.md and .codex/project-collaboration/contracts/implementation-planning.md. Resolve the exact GitHub Issue and actual current repository evidence. Read accepted target product/Task Decisions only when relevant; treat historical PRs, earlier Plan versions and proposals as evidence unless current authority selects them. Do not copy Badminton's plan location or modify legacy PR #46 merely because Issue #41 is under discussion.

### Author Plan — finish here

Confirm the task intent, current state, accepted scope and whether material questions truly need clarification. Draft one executable, proportionate Plan using the planning-quality contract. Follow docs/collaboration.md to write one full **Implementation Plan vN** comment to the **same Issue** and update its current Plan pointer; preserve prior version comments. If write authority or access is missing, provide the complete draft and explicitly mark it unsaved; do **not** silently substitute a repository Markdown file or a Plan-only PR.

Report the canonical Plan link, decisive approach, material risks/questions and any unavailable evidence. **Stop when this authoring result is delivered.** Do not automatically perform Formal Plan Review, Approval, implementation, branch or PR publication. A private self-check is not a Formal Review.

### Formal Plan Review — distinct request

Resolve the exact current Issue Plan permalink, version, source alignment, applicable approved decisions and current repository evidence. Independently assess the plan using the planning-quality contract; identify specific actionable gaps and one clean/changes-requested/provisional verdict. Publish the review to the **same Issue**, referencing the exact version, if the requested review has the appropriate authority. Apply only explicitly authorized Plan correction rules; material changes create a new version and require a new review. Do not invent an approval or edit production files.

Report the verdict and complete required correction end state, then **stop**. This does not authorize implementation, merge, or a second PR.

## Safeguards

Missing Issue identity, conflicting current Plan pointer, unverified authority, outdated product direction or inaccessible required evidence must be surfaced instead of guessed. Reuse already completed current review. A request for execution belongs to the execution owner, not an implicit planning loop.
