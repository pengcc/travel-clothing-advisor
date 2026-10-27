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
| Merge / Closeout | Same delivery PR plus Issue completion check | No new PR | Separate explicit user merge instruction for ordinary PRs; only a separately approved, narrowly bounded operational data-PR exception may use standing authority; acceptance satisfied before Issue closeout |

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

Independent Implementation Review examines the published PR's current exact base and head, complete implemented diff, Issue, approved Plan where required and verification evidence. Record both revisions and evidence boundaries. Findings identify evidence, impact and required fix end state. Review-only work performs no implementation edits, merge or deployment; the implementer must not self-approve an independent review.

An Implementation Review request normally authorizes bounded publication of its actionable findings to the **exact reviewed PR** using an available suitable repository mechanism (a PR comment or review). Explicit no-post/read-only or other publication prohibitions override this authority. This permission covers the review result only; it does not authorize implementation edits, approval, merge, deployment or product-data mutation.

When actionable findings exist, publish a complete, directly usable review result on that PR: repository/PR and linked Issue, exact reviewed base/head, verdict and evidence boundaries, and **every actionable finding** with priority, location/evidence, impact and required end state. The record must let another authorized ChatGPT or Codex actor retrieve the findings, remediate them and associate re-review with the original findings without the user relaying chat content. A summary that omits findings or points only to private chat is insufficient. Verify successful publication and return its permalink alongside a useful, self-contained chat review. If publication is unavailable, fails or is disallowed, provide the complete review in chat and explicitly state that the shared handoff is incomplete and why; do not claim the findings were recorded. With no actionable findings, return a concise clean verdict bound to the reviewed revisions and evidence limitations; no ceremonial PR comment or marker is required.

Fix actionable findings only under a **separate authorized implementation request**, on the **same delivery branch and PR**. Re-review resolves the new exact base/head, checks earlier findings and examines regressions and scope drift. A changed target requires renewed review of affected evidence; an old clean verdict does not establish freshness. Published findings remain bound to their recorded revisions. Do not create parallel fix PRs for the same delivery.

A clean review never authorizes merge. For ordinary implementation, documentation and tooling PRs, require a separate, current explicit user merge instruction, then recheck target freshness, required checks and intended scope before merging. The only prospective exception is the strictly bounded, separately approved operational forecast-data publication described below; it never applies to a PR introducing or changing automation. Close the Issue only after its acceptance and closeout are actually satisfied; PR creation or review must not close it automatically. Deployment, release and other material external effects require separate authorization, which may be a specifically scoped standing authorization only under the exception below.

## Bounded standing authorization for routine forecast data PRs

Daily forecast refreshes are operational **data publications**, not implementation PRs. The owner may separately authorize repeated unattended merges of that one narrowly scoped data-PR class instead of approving each refresh. This is an exception to the per-PR human merge instruction **only after** explicit standing authorization is recorded for the exact reviewed implementation, with the resulting automatic Vercel Production deployment and its failure/recovery implications understood. The approval record must identify the eligible workflow, source/target refs, validation and required-check mechanism, scope, activation/pause/revocation controls, and Production deployment effect. The owner may revoke or pause that authority; any materially changed workflow, publisher, trust boundary, target or deployment behavior requires new review and authorization.

A standing-authorized forecast-data PR must satisfy **all** of these gates, enforced by the approved automation immediately before each merge:

- Source is the trusted `main` run of `.github/workflows/weather-refresh.yml`, produced by `github-actions[bot]` on the dedicated `codex/weather-forecast-data` branch, targeting `main`. Verify provenance and the exact current base/head; reject unexpected ownership, branch drift, duplicate PRs, manual pause/close or a replaced head.
- The PR diff contains **only** `weather-data/forecast/**` objects. No application code, workflow, docs, city manifest/trust-anchor change, history, cache/ledger or other data path is eligible.
- Independent of the PR author's claims, the current base/head data passes the approved complete ten-city, same-Germany-day, source/identity, acquisition freshness/no-regression, DST and lossless history/non-forecast-byte gates. A main/head change invalidates prior evidence and requires revalidation; stale or incomplete data must not merge.
- Applicable required checks must actually complete successfully and the approved pre-merge verification must succeed; missing, pending, skipped or failing evidence is not a pass. A `GITHUB_TOKEN`-created PR may not trigger ordinary PR workflows, so unattended publication must have a verified, non-bypassing validation path before activation. Never auto-approve code, bypass branch protection or treat a self-authored success statement as independent validation.
- A failed gate, permission problem, publication/deployment uncertainty or operator pause stops automatic merge, retains diagnosable status and leaves the decision to the operator. No unattended rollback, retries that circumvent limits, settings changes or extra provider collections are implied.

All **implementation**, documentation, tooling, security and automation changes—including the change that adds automated merging—continue through the ordinary Issue/Plan (when needed), independent Implementation Review, and per-PR human merge/deployment authorization. This exception does not expand the approved [Issue #79 Plan v2](https://github.com/pengcc/travel-clothing-advisor/issues/79#issuecomment-6411741200): its delivered [PR #80](https://github.com/pengcc/travel-clothing-advisor/pull/80) only creates/updates data PRs, and does not implement, authorize or activate unattended merge. **Merging this documentation change alone grants no standing permission, enables no automated merge and authorizes no Production deployment.**

## Legacy transition and STOP boundaries

Apply this contract prospectively. [Issue #41](https://github.com/pengcc/travel-clothing-advisor/issues/41)'s calendar Plan belongs in that Issue. Legacy planning [PR #46](https://github.com/pengcc/travel-clothing-advisor/pull/46) must not be automatically closed, converted, modified or merged by this migration. A separately authorized transition may copy its proposal into #41 for proper review and decide how to close the legacy PR without merging. Historical work, including merged [PR #29](https://github.com/pengcc/travel-clothing-advisor/pull/29), is evidence, not a target for retroactive rewriting.

STOP affected work on conflicting canonical instructions, unverified approval/source content, unexpected reviewed-Plan edits, a need for files or authority outside approved scope, pressure to retain a donor-owned contract, or unapproved external effects. Resolve material Plan deviations through a new reviewed and approved version in the same Issue. Donor repositories are optional method evidence, never workflow authorities or runtime dependencies. Planning/Execution/Review Skills, role router, Project Memory, Task State, hooks, scripts and CI are not installed by this documentation contract.
