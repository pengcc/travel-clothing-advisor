---
name: execute-plan
description: Implement a directly authorized bounded Travel change or an explicitly approved current Issue Plan, validate the affected behavior and deliver one code PR without re-planning.
---

# Travel Execute Plan

Use for **authorized implementation** or same-PR remediation, not a request merely to discuss, author a Plan, review, merge or deploy. Adapted from Badminton execute-plan. docs/collaboration.md is the sole stage/approval/publication authority.

## Select exactly one execution input

Read current AGENTS.md, docs/collaboration.md, .codex/project-collaboration/task-alignment.md when applicable and actual target code/README/tests. Then use one matching local reference:
- **Direct bounded request:** references/inputs/direct-bounded-delivery-request.md.
- **Reviewed and explicitly approved Plan or other accepted execution contract:** references/inputs/approved-execution-contract.md.

Verify the current Issue/task, source authority, goals, scope/non-goals, target revision, accepted decisions, validation need and material STOP conditions. A Plan's existence, green review, Issue label or a previous PR does not itself grant execution authority. Reuse adequate planning; do not automatically create a Plan/Task State for directly authorized small work.

## Execute, validate and deliver

Inspect affected modules and focused tests; implement the smallest complete behavior. For the Python application, use relevant targeted tests and **make test** when needed and supported; choose actual necessary checks from the current Makefile. Data prefetch, cache writes, external provider calls, make dev, deployment and release are separate effects, never implicit tests. Preserve accepted weather/history product and freshness semantics.

Stop if work would require unapproved product/architecture scope, destructive data changes, a materially changed approved Plan, unsafe secrets, external effects or a different validation boundary. Report the exact blocker instead of silently rewriting the Plan.

After a coherent authorized change, record actual checks and outcomes; commit on a dedicated delivery branch and create/update **one code PR** linked to the Issue, as already governed by docs/collaboration.md. A normal authorized implementation includes that PR under the target convention unless the user requests local-only/no PR. No Plan-only PR, duplicate review PR, publication helper, donor Task Workspace or second approval prompt for the same bounded PR delivery.

Provide a concise result, exact PR and evidence limitations. Do not self-perform the independent Implementation Review, merge, deploy, or close the Issue without applicable separate authority. If required local or remote validation is unavailable, distinguish unverified from failed; do not claim review readiness from a blocked required check.
