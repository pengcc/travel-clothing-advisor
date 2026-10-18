# Collaboration Workflow Contract

This is the mandatory, sole workflow authority for `pengcc/travel-clothing-advisor`, across ChatGPT and Codex sessions and regardless of which Skill runs. [AGENTS.md](../AGENTS.md) routes work here. This contract governs stage mechanics; [Task Alignment](../.codex/project-collaboration/task-alignment.md) governs intent, Task Baseline and accepted Task Decisions; [product documents](product-blueprint.md) govern product meaning. Reuse established alignment and evidence. This is neither a second Task Baseline nor an installed Skill, role router, memory system or automation framework.

## Canonical lifecycle

| Stage | Canonical location | New PR? | Authority / completion |
| --- | --- | --- | --- |
| Issue / requirements | GitHub Issue | No | Outcome, scope, acceptance and risks sufficiently clear |
| Implementation Plan, when required | Full versioned comment in the same Issue; Issue body links to current version | No | Executable proposal, not execution permission |
| Formal Plan Review | Comment in the same Issue citing exact Plan permalink/version and current evidence | No | Independent clean review or findings; not user approval |
| Approval | Separate record in the same Issue of explicit user authorization of the clean-reviewed Plan version | No | Source and scope verifiable by next executor |
| Implementation | Dedicated branch and one review-ready change PR tied to the Issue | Yes | Authorized task implemented with truthful validation |
| Implementation Review / Fix / Re-review | Same PR and delivery branch, current exact base/head | No new PR | Independent review; actionable findings remedied and re-reviewed |
| Merge / Closeout | Same delivery PR plus Issue completion check | No new PR | Separate explicit user merge instruction; acceptance satisfied before Issue closeout |

A planning-only documentation proposal **never creates a PR**. Actual authorized documentation implementation uses the ordinary delivery PR. Clean review, approved Plan, published PR, merged change and deployed product are distinct states and authorities.

## Planning, version identity and approval

Use a formal Plan when consequential product, cross-layer, scope, risk or acceptance choices require review before execution. A small, clearly bounded Issue with direct explicit execution authorization may skip a formal Plan and Formal Plan Review. It still requires real validation, one delivery PR, independent Implementation Review and separate merge authority. Issue existence, a posted Plan, clean review or a bare “next step” does not authorize gated implementation.

For every formal revision:

1. Publish one full `Implementation Plan vN` comment in the same Issue. Keep the Issue body to a brief task/status and a single current Plan pointer; do not maintain a competing full Plan in the body or repository.
2. Treat version comments as append-only by procedure. GitHub comments are technically editable; never overwrite a reviewed version. A material correction requires a new `vN+1` comment and updated body pointer; retain prior versions for audit. If a reviewed comment unexpectedly changes, **STOP** and re-establish exact content, review and approval before execution.
3. Obtain independent Formal Plan Review in that Issue. Identify repository/Issue, exact Plan permalink and version, relevant current repository refs/baseline, evidence, findings and verdict. Resolve actionable findings before claiming clean review.
4. Obtain explicit user approval of that exact clean-reviewed version. Record it in a separate Issue comment linking the Plan, clean Review and approval source/context. For GitHub authorization, link the actual user source. For ChatGPT/Codex authorization without a link, accurately record the user's actual wording and conversation context; do not invent a GitHub approval or agent self-authorization. **STOP** if source or scope is materially ambiguous.

Material changes after review or approval require a new version, fresh independent review and renewed explicit approval. Prior approval cannot authorize changed requirements. Pure editorial clarification may be logged without re-review only when executable requirements, boundaries, risks and validation remain unchanged; preserve the reviewed version.

## Implementation handoff

An actionable handoff identifies the exact repository and Issue; Plan version/permalink, clean Review and approval record when required; delivery branch or base; desired behavior; scope/non-goals; required validation/tests; known gaps; STOP conditions; and expected output. It points to canonical artifacts rather than becoming another Plan or a separate PR.

Resolve current repository reality and authority, then implement on one dedicated branch and publish one review-ready PR linked to the Issue. Describe what changed and why, actual validation and remaining limitations. Do not claim tests, CI or scenarios passed unless checked. Local-only/no-push/no-PR instructions constrain publication without granting merge or waiving independent review.

## Exact PR review, fixes and merge

Independent Implementation Review examines the published PR's current exact base and head, complete implemented diff, Issue, approved Plan where required and verification evidence. Record both revisions and evidence boundaries. Findings identify evidence, impact and required fix end state. Review-only work performs no edits, merge or deployment; the implementer must not self-approve an independent review.

Fix actionable findings on the **same delivery branch and PR**. Re-review resolves the new exact base/head, checks earlier findings and examines regressions and scope drift. A changed target requires renewed review of affected evidence; an old clean verdict does not establish freshness. Do not create parallel fix PRs for the same delivery.

A clean review never authorizes merge. Require a separate, current explicit user merge instruction, then recheck target freshness, required checks and intended scope before merging. Close the Issue only after its acceptance and closeout are actually satisfied; PR creation or review must not close it automatically. Deployment, release and other material external effects require separate authorization.

## Legacy transition and STOP boundaries

Apply this contract prospectively. [Issue #41](https://github.com/pengcc/travel-clothing-advisor/issues/41)'s calendar Plan belongs in that Issue. Legacy planning [PR #46](https://github.com/pengcc/travel-clothing-advisor/pull/46) must not be automatically closed, converted, modified or merged by this migration. A separately authorized transition may copy its proposal into #41 for proper review and decide how to close the legacy PR without merging. Historical work, including merged [PR #29](https://github.com/pengcc/travel-clothing-advisor/pull/29), is evidence, not a target for retroactive rewriting.

STOP affected work on conflicting canonical instructions, unverified approval/source content, unexpected reviewed-Plan edits, a need for files or authority outside approved scope, pressure to retain a donor-owned contract, or unapproved external effects. Resolve material Plan deviations through a new reviewed and approved version in the same Issue. Donor repositories are optional method evidence, never workflow authorities or runtime dependencies. Planning/Execution/Review Skills, role router, Project Memory, Task State, hooks, scripts and CI are not installed by this documentation contract.
