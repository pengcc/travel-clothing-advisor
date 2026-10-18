# Design Judgment Principles

Use these principles to judge whether a current or proposed design is suitable for the real need. They are a
judgment yardstick, not a workflow, checklist, or source of requirements.

## Start from the real situation

Begin with the supported outcome, real actors or consumers, operating conditions, constraints, and
meaningful failure or loss boundaries.

Treat current implementation, historical fixes, compatibility paths, tests, and operational habits
as evidence, not preservation requirements. Do not optimize or preserve a mechanism before
establishing what real requirement or outcome makes it useful.

## Judge fit, not apparent strength

A design is not better merely because it is more general, automated, defensive, flexible, modern,
or simple.

For each material capability, protection, abstraction, check, state, retry, compatibility layer, or
coordination mechanism, identify the concrete outcome or loss boundary it improves and the cost it
introduces in state, ordering, runtime, validation, maintenance, recovery, or operator understanding.

Keep additional complexity when its demonstrated benefit warrants that cost. Remove, narrow, delay,
or avoid it when the benefit is speculative, duplicated, or disproportionate to the real need.

## Find the natural owner and boundary

For each material truth, transition, resource, or failure, identify the boundary that can actually
establish or change it.

Do not assume that the current file, module, worker, process, container, service, cache, or
abstraction boundary is the correct ownership or isolation boundary. Look for overlapping owners
that independently decide, check, synchronize, reserve, clean, or recover the same truth.

Place responsibility where the relevant fact can be established reliably with the least duplicated
coordination.

## Compare credible alternatives by trade-off

When a materially different design is credible and could change the conclusion, compare it with the
current or proposed design.

Compare what each option buys and gives up across the properties that matter for this task, such as
correctness, user experience, safety, integrity, operability, failure recovery, runtime cost,
validation burden, maintenance cost, and future change isolation.

Do not prefer the simpler or more complex model by default. Prefer the model whose trade-offs best
fit the demonstrated need and conditions.

## Judge the whole relevant lifecycle

Do not approve a design only because each local component is individually reasonable.

Trace the smallest complete lifecycle that can materially affect the outcome: the real entrypoint,
authoritative transitions, necessary handoffs or side effects, actor-visible result, and meaningful
failure or recovery boundaries.

Distinguish normal-path requirements from retry, compatibility, convergence, exceptional recovery,
or damaged-state repair. Do not make the common path continuously pay for rare recovery unless the
real scenario or loss boundary justifies it.

## Validate the design claim

Prefer evidence that can fail when the real supported outcome, invariant, ownership boundary, or
loss condition is wrong. Internal helper behavior is not a substitute for a runtime, persistence,
integration, lifecycle, or actor-visible boundary when that boundary is the claim.

Validation is also part of the design cost. Frequently executed checks, containers, startup work,
and CI coverage should have distinct regression value proportional to their runtime and maintenance
burden.

Conclude from the evidence whether the design should be kept, simplified, strengthened, reframed
around a different boundary, or held pending better evidence. The purpose is suitability to the real
need, not completion of a checklist.
