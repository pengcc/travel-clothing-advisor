# Task Alignment

Task Alignment establishes the task-wide meaning that later discovery, research, design, or implementation stages must preserve. Use it for complex, cross-stage, or capability-level work. Keep a small, clear, single-stage task direct rather than manufacturing persisted state or ceremony.

## Establish or reuse

If a current Task Baseline exists for the exact task, read and reuse it. Do not reconstruct it because the actor or stage changed.

If no baseline exists and durable cross-stage alignment is useful, establish one from the user's real travel/product scenario and verified evidence. Clarify only uncertainty that could materially change intent, outcome, scope, risk, or acceptance.

## Task Baseline

Keep the baseline concise, solution-independent, and proportionate:

```md
# Task Baseline

## Intent
Who uses or depends on the result, in what real context, what need exists, and why it matters.

## Expected Outcome
The high-level result that should exist when the task is complete.

## Scope
What the current task covers.

## Non-goals
What is intentionally excluded.

## Key Boundaries
Material uncertainty, authority, external effects, reversibility, user harm, and other constraints later stages must preserve.

## Value and Risk
Expected benefit and cost, the credible loss boundary, and the proportionate level of control.

## Success Boundary
The high-level evidence that the real need is met without unsupported scope or complexity.
```

Add `Open Blocker` only while an unresolved issue prevents safe continuation.

The Task Baseline is not a plan. Do not place solution design, work items, files, commands, tests, sequencing, or delivery mechanics in it.

When establishing or refreshing the baseline, judge its Success Boundary in a representative real traveler or product scenario. If every stated success condition could pass while the real need and scope the task claims to own remain materially unresolved, shaping is not ready. Internal consistency or proof of one mechanism is insufficient. A deliberately bounded subtask remains valid when it fully satisfies its own bounded end state and leaves broader residual work explicitly outside its completion claim with a real owner; it need not solve that separately owned parent problem.

## Task Decisions

When functional or product choices must persist across stages, record them as Task Decisions. Accepted Task Decisions are subordinate to the Task Baseline and authoritative only for the choices they settle. Candidate ideas, reviewer preferences, current hypotheses, and existing implementation behavior do not become Task Decisions without acceptance.

## Freshness and evidence

Before relying on a baseline:

1. resolve the current canonical artifact or conversation state;
2. compare it with verified current facts that could affect its fields; and
3. check the current stage artifact or action for conformance.

Distinguish user intent, accepted decisions, current evidence, historical material, candidate solutions, and unresolved claims. State only what the evidence proves. Historical implementation, compatibility behavior, tests, scenario fixtures, stronger proof strategies, and other mechanisms remain evidence unless accepted authority, a current consumer, or a demonstrated loss boundary makes them requirements. Their presence in an artifact does not by itself justify preserving them as requirements.

## Baseline amendment

Amend a baseline only when explicit user correction or verified contradictory evidence invalidates or materially completes it. A preferred solution, broader optimization, wording improvement, or implementation convenience is not amendment evidence.

This includes verified evidence or explicit user correction showing that a historical mechanism or proof proxy was mistaken for the requirement and thereby invalidates the baseline's meaning. Downstream consumers should stop affected work and return to Task Alignment rather than silently preserving an invalidated proxy.

A discovering stage should stop affected downstream work and report:

```txt
Baseline Amendment Required:
- Evidence or user correction:
- Invalidated field(s):
- Downstream artifacts affected:
- Reset point:
```

Amendment does not itself authorize implementation or external action.

## Cross-stage use

Later stages should read the current Task Baseline and applicable accepted Task Decisions, confirm freshness, and evaluate their work against them without redefining the task.

Plans, prompts, implementation artifacts, reviews, and status records are consumers or stage outputs. None is a competing task-wide baseline.

## Adoption provenance

Adapted for this repository from `pengcc/badminton-club-app` Task Alignment semantics, initially from revision `56d6251bda1d9a63799267f2300f24e9ac192c50` and refreshed for real-outcome convergence from revision `a7e4743e471209c294214ff6617bb7980606f263`. This target-owned version intentionally omits dependencies that are not installed here.
