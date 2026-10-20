---
name: implementation-review
description: Independently review a Travel implementation PR at exact current base/head against its Issue, execution authority and delivered behavior; re-review fixes on the same PR.
---

# Travel Implementation Review

Use only for a request to review or **re-review delivered implementation** (normally an exact GitHub PR), not Plan Review, a code fix, automatic Merge or deployment. This Skill is adapted from Badminton implementation-review without its Project Memory, persisted Task State, transport automation or nested code-review workflow.

Read current AGENTS.md, docs/collaboration.md and .codex/project-collaboration/contracts/implementation-review.md. Resolve the exact current PR base/head, complete diff, linked Issue, relevant current Plan version/review/Approval when required, and actual available test/CI evidence. Read affected product or design decisions when relevant. Missing authority makes only the affected conclusion provisional; do not infer Approval from a PR number or a skill invocation.

Judge the entire delivery in the **six dimensions** of the target review-quality contract, including implementation quality directly. Separate actionable defects from optional suggestions and evidence limitations. State one verdict bound to the exact reviewed revision; each actionable finding includes evidence, impact and the required end state. Do not fabricate executed tests or assume green checks prove user behavior.

For a re-review, re-resolve the updated PR base/head, earlier findings and their required end states, and any introduced regressions. Fixes must be separately authorized and made on the **same PR**; this Review does not edit implementation, approve, merge, release, deploy, create another PR or emit machine-readable clean markers.

Follow **docs/collaboration.md, “Exact PR review, fixes and merge”**, for result publication authority and shared handoff completion. A Review request normally authorizes publishing actionable findings to the exact reviewed PR unless explicitly prohibited. Publish the complete review result required by that contract, verify publication and link the shared record in chat; keep the chat review useful on its own. If publication is unavailable or disallowed, return the complete review in chat and disclose why the shared handoff remains incomplete. With no actionable findings, give a concise revision-bound clean verdict and evidence limitations without requiring an external comment or marker.

Review completion **ends this requested task**; it does not automatically trigger remediation or merge.
