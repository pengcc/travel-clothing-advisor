# Direct bounded delivery request — Travel

Select only when the **current user request** gives explicit implementation authority for a concrete limited task and docs/collaboration.md does not require a reviewed Plan first.

Before mutation verify:
- the exact target repository/Issue/request and up-to-date base/source state;
- desired actor-visible result, scope, non-goals, key current decisions and affected owners;
- concrete validation/acceptance and any genuine external or destructive boundaries;
- no unresolved material product, architecture, privacy or risk decision that requires planning or the user.

When these are sufficient, **implement directly**; do not create a formal Plan, Task Workspace, execution-input registry or extra publication approval step. Respect separate merge/deployment authority. On a material scope change or missing authority, STOP and return to the user's actual decision, not an invented planning loop.

This input covers authorized documentation and Skills changes as well as application code. For initial implementation, use a dedicated delivery branch and deliver one change PR linked to the Issue. For authorized remediation of an existing PR, resolve its current base/head and continue on the same delivery branch and PR; do not create a replacement branch or another PR. Deliver truthful validation through the execution owner, unless publication is explicitly constrained to local-only/no push/no PR. Retain independent Implementation Review/re-review regardless of publication constraints; Plan Approval and separate merge authority remain governed by docs/collaboration.md.
