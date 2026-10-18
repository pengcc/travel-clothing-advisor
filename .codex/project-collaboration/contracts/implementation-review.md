# Implementation Review Quality — Travel

This is a **subordinate evaluation contract** adapted from Badminton Implementation Review. docs/collaboration.md alone governs stage authority, Review independence, PR result publication, remediation, merge and closeout. This does not install another reviewer workflow.

Review the **actual current** implementation PR base/head and diff. Ground conclusions in the Issue's accepted acceptance criteria, applicable current approved Plan version and approval, target-owned code, and verified validation; do not invent missing authority or test results.

Evaluate proportionately:
1. **Issue/Task alignment:** solves the stated real need within accepted scope and non-goals.
2. **Execution conformance:** respects approved Plan or directly authorized request without silent substitution.
3. **Observable behavior:** relevant entrypoint, user-visible/API result, failure and integration boundaries behave as intended.
4. **Risk and authority:** permissions, privacy, safety, side effects and publication boundaries are preserved.
5. **Implementation quality:** correctness, maintainability, existing Python/web conventions, unnecessary changes or duplication.
6. **Evidence and artifacts:** meaningful tests, documentation and behavior agree; distinguish run checks, static inspection and unavailable runtime evidence.

Actionable findings (blocking / must fix / should fix) specify exact location/evidence, impact and **required end state**. Optional ideas do not make an otherwise clean review actionable. If material evidence is unavailable, identify affected conclusions as provisional rather than treating missing evidence as clean or presuming a defect.

For a subsequent independently requested **re-review**, resolve the **new** PR base/head, check each earlier actionable required end state, and inspect related regressions/scope drift. Corrections use the **same PR** and require an authorized implementation request. Review by itself never fixes code, approves, merges, releases or deploys. No marker or report artifact is required for a clean result unless separately requested by the target owner.
