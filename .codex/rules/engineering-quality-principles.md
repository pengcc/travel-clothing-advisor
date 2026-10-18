# Engineering Quality — Travel

Adapted from Badminton's engineering-quality-principles.md. Apply as focused engineering judgment during planning, implementation and review, not as another stage or authorization owner. docs/collaboration.md and AGENTS.md govern the task, scope, PR and external-effect boundaries.

- Prefer the smallest correct change consistent with Travel's existing Python web application, APIs and data preparation logic. Do not import Badminton's Next.js, pnpm, MongoDB, CI or deployment assumptions.
- Preserve accepted product behavior and current ownership. If a real design/architecture deviation is needed, explain its evidence and contain its blast radius.
- Validate observable behavior at affected trust and failure boundaries. Preserve clear errors, data freshness and evidence limitations; do not claim a fixture check proves live forecast or historical data coverage.
- Select regression tests for meaningful failures, not merely every new line, description, heading or internal method. Prefer assertions a plausible consequential regression would break. Avoid duplicating existing coverage.
- Read the target Makefile and relevant module tests before choosing checks: make test executes Python unittest tests; make dev requires prepared forecast/history data and is not a universal validation prerequisite. Do not run live downloads, modify retained caches, or deploy without applicable permission.
- Keep changes reviewable, report checks actually run, and avoid product code or unrelated cleanup during documentation/Skill-only adoption.
