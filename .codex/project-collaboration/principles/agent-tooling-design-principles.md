# Agent Tooling Design Principles

Use these principles only when researching, reviewing, creating, expanding, simplifying, or
removing agent rules, skills, prompts, checklists, routing, validators, consumer packages, scripts,
or related tooling. They are a design and review yardstick, not an ordinary-task gate, workflow,
authorization mechanism, or required response format.

## Responsibilities

Agent tooling should help an actor:

1. understand and complete the user's real task;
2. find capabilities through clear owners, triggers, inputs, outputs, and boundaries;
3. preserve user control at meaningful safety and external-action boundaries; and
4. produce inspectable results and truthful uncertainty.

The measure is improved task outcomes, not evidence that an internal process was followed.

## Principles

### Start from the outcome

Name the observed failure, repeated friction, omission, confusion, or credible high-impact risk the
change addresses. Structural uniformity, schema completeness, or hypothetical future flexibility is
not sufficient value.

### Use the smallest sufficient solution

Before adding a concept, try clearer wording, corrected routing or ownership, removal of duplication,
a stronger completion or STOP condition, or one focused behavioral check. Add a new component only
when an existing owner cannot address the evidenced need cleanly.

### Treat runtime instruction as a behavioral delta

Start from what a capable actor can already do from the current task, repository evidence, and
canonical owners. Add or retain runtime instruction only when it contributes a project-relevant
distinction, non-obvious trigger, demonstrated recurring-failure correction, or real
safety/authority/loss protection. General desirable reasoning, engineering, writing, review, or
conversation behavior does not earn runtime presence merely because it can be stated.

This is a design baseline, not an authority source. Current repository truth, Task authority, and
consequential safety or external-effect boundaries still govern.

Keep runtime instruction, conditional mechanics, and explanation distinct. Put every-invocation
behavioral deltas and consequential boundaries in the runtime skill, branch-specific mechanics
behind conditional pointers, and rationale, tutorials, examples, history, or design explanation
outside the runtime path when they do not change execution. Useful explanation does not by itself
justify always-loaded instruction.

### Keep semantic judgment with the actor

Deterministic tooling is useful for mechanical facts and machine-consumed constraints. Keep intent,
scope, proportionality, finding correctness, solution fit, and evidence sufficiency with the actor.
Do not create a second structured task description merely because context can be encoded.

### Specify outcomes and boundaries

Normally define the objective, scope, non-goals, completion boundary, validation intent, STOP
conditions, and authorization boundaries. Leave routine execution choices to the acting
environment. Prescribe detailed procedure only when repeated failures or material destructive,
irreversible, sensitive, migration, publication, or external-system risk justifies it.

### Make complexity pay rent

A new component should remove, consolidate, shorten, or materially strengthen existing behavior.
Account for context load, cognitive load, routing, maintenance, duplicated state, validation burden,
and new failure modes. Conditional usefulness does not by itself justify always-loaded,
always-routed, or always-presented participation on the common path; retain that cost only when
the normal supported outcome depends on it. Plausible future capability, generic completeness, or
an adjacent possible use is not sufficient justification for new machinery without a demonstrated
current consumer, outcome, or loss boundary. Preserve cheap structural optionality only when it
avoids foreseeable coupling at negligible cost. The common path should become shorter, safer, or
clearer.

For existing as well as proposed machinery, connect durable/common-path value to its actual
contribution in the applicable scenario: user-visible results, task-appropriate quality, credible
loss or authority protection, meaningful information preservation, or reduced user/system burden.
Weigh that contribution against whole-path cost, including latency and the burdens above.
Implementation, tests, review history, persisted artifacts, and downstream dependencies are evidence
of implementation, coverage, history, or consumers to the extent actually demonstrated; none alone
proves that common-path retention is worth its cost. Missing value evidence alone does not require
removal: retain, narrow, replace, remove, or seek further evidence according to the actual need and
risk. Revisit the judgment when later real evidence changes it, without routinely re-proving
unchanged safeguards or demoting genuine requirements for convenience.

Apply the same rent test inside a retained skill. Ordinary low-risk procedural prose does not need
per-sentence proof of uselessness before it may be challenged or removed; when its contribution is
materially uncertain, use a discriminating scenario or compact candidate. Demonstrated
high-consequence protections remain preservation-first until a smaller mechanism establishes
equivalent protection. Subtraction-first is not delete-by-default, and preservation-first is not a
license to keep unrelated explanatory or duplicated prose around the protected boundary.

One successful real-task use supports only what that use exercised under its conditions. Making
the capability durable or common-path is a separate decision about longer-lived contribution and
cost; success alone does not establish always-loaded participation, permanent ownership, required
routing, or a project-wide standard. This distinction adds no mandatory experiment lifecycle or
evaluation artifact.

### Design for subtraction

Judge each tooling behavior by its current demonstrated justification. Retain the protection
required by a still-real outcome, loss, or authority boundary while that boundary persists, but
re-evaluate whether the current behavior is the smallest sufficient way to provide it. Scaffolding
whose benefit depends on changing actor, model, runtime, routing, workflow, or
consumer limitations should be re-evaluated as those conditions change. One mechanism can contain
both: remove, merge, narrow, or demote only the behavior whose justification no longer holds while
preserving or replacing the behavior needed for each still-required protection. Stronger capability
is a reason to re-evaluate compensating scaffolding, not proof by itself that a real boundary
disappeared or that another orchestration layer is warranted.

## Retention judgment during Agent-tooling audit

When an existing Agent-tooling mechanism is explicitly under audit or review, judge whether to
retain it by the same current value-and-evidence standard used for proposed machinery. Age,
canonical placement, prior approval, implementation, tests, historical review, persistence, and
downstream dependency are evidence only; none independently establishes design-retention authority.

Keep operational authority distinct from retention judgment. Current canonical tooling remains in
force until a separately authorized correction changes it; an audit finding does not itself let an
ordinary actor ignore or deactivate the current rule.

When a real tooling regression directly involves an inherited mechanism, include that mechanism
itself among the candidate explanations before preserving it through another exception. Consider
whether current evidence supports `KEEP`, `NARROW`, `MERGE-COLLAPSE`, `REMOVE`, or
`INSUFFICIENT EVIDENCE` based on demonstrated contribution, current consumers or loss/authority
boundaries, overlap, whole-path cost, and contrary evidence. These are audit judgments, not a
persistent lifecycle. Later material evidence may revise an earlier judgment.

This does not require ordinary tasks to re-prove unchanged tooling or trigger a retention audit
merely because they consume a canonical mechanism. Keep retention judgment conditional to actual
Agent-tooling audit/review work and proportionate to its selected scope.

## Tooling change gate

Before planning a new or materially expanded tooling concept, answer:

1. What demonstrated problem or credible high-impact risk is being addressed?
2. Why are clearer wording, corrected ownership, less duplication, or the existing owner
   insufficient?
3. What existing concept, step, output, or maintenance burden will be removed or reduced?
4. Does the common task path become shorter, safer, or easier to understand?
5. What representative actor-behavior scenario distinguishes current from intended behavior?

If the answers are weak, simplify, defer, or reject the proposal.

## Evaluation

Prefer representative complete tasks over document-field or checklist-coverage tests. Evaluate
whether the actor understood the task, selected the right capability, stayed within scope and
authority, avoided unnecessary ceremony, validated meaningful behavior, stopped at the correct
external boundary, and produced an inspectable result. For simplification, confirm that the
intended normal task still succeeds, removed or narrowed machinery no longer participates where it
is unnecessary, and representative high-risk or conditional scenarios retain the real boundary it
protected. Reject a supposed simplification that adds a more general route or system beside
still-required old machinery unless the additional capability has its own demonstrated current
consumer, outcome, or loss boundary.

For a materially costly or disputed runtime-instruction surface, compare the current contract with
a compact candidate when that comparison can expose the claimed value. Judge owner selection, task
quality, unnecessary questions or ceremony, scope drift, false STOPs, user-correction burden, and
applicable safety/evidence/authority behavior. Repository or owner inspection can prove duplication,
placement, conditionality, or explanatory-only text; a conceptual compact candidate does not prove
runtime equivalence. Claim preserved actor behavior only from actor-visible evidence that actually
exercises the distinction, and otherwise keep that equivalence unverified. Do not turn this into a
mandatory benchmark, scorecard, evaluator, or recurring experiment lifecycle.

Use parsers, schemas, and field-level tests when those structures are themselves machine-consumed
interfaces. Do not introduce a runtime, registry, dispatcher, scheduler, or synchronization
mechanism to enforce prose semantics without separate demonstrated need and authority.

These principles do not replace the active task or stage contract, local safety rules, or
environment-specific operating mechanics.
