# Issue #50 / PR #51 warmth labels

Scope: featured-card shapes/colors, plus the now-approved shared human-readable L1–L6 label names. The result-page marker retains its existing layout and icons, but its visible text matches the featured-card labels. Card-only `null` variation uses the existing wide paired-mascot asset; null/no-daytime remains a neutral, text-only state. Classes consume the server-selected level and existing variation flags; no temperature classification is added.

Input PR revisions verified on 2026-10-18: base `f90cbfda2411b00d9d6a6b51c3212e12036e92a8`, head `09b7d787b6bb424d2a104116aa542513eaf95de7`, branch `ui/issue-50-featured-city-cards`.

## Checks actually run

- `make test`: 92 tests passed. Initial sandbox attempt could not bind local test ports; the permitted rerun passed.
- `node tests/web/icon-regressions.cjs`: passed 320/390/1280px, 1x/2x WebP, PNG retry, all-image failures, variation coexistence and detail rendering.
- `node tests/web/warmth-label-regressions.cjs`: 12 combinations passed (320/390/1280px × normal/200% root font × loaded/missing images). Six levels plus variation-null and unavailable-null retain complete text within labels and cards, with no page overflow; all six level backgrounds differ. Reduced-motion mode has no label transition.
- `git diff --check`: passed.

Browser checks use the existing optional Playwright install and local Chrome with `python3 -m web.server --fixtures --port 8001`. No live weather, cache writes, deployment or independent review was performed. Safari remains unverified. The wavy variation silhouette uses CSS `shape()` with an asymmetric rounded fallback in browsers without support; text is never clipped. Labels add no hover effect or animation.

## Actual browser screenshots

`home-*.png` shows the existing fixture homepage section. `labels-*.png` shows an explicitly synthetic eight-state matrix rendered with the actual CityCard component and stylesheet; it does not claim live city weather coverage. Normal and 200% label-font screenshots plus missing-image cases were visually inspected. Existing mobile stacking is preserved; long labels wrap at large font sizes.

- [Desktop homepage](home-1280.png), [390px homepage](home-390.png), [320px homepage](home-320.png)
- [Desktop all states](labels-1280.png), [390px all states](labels-390.png), [320px all states](labels-320.png)
- [390px 200% label font](labels-390-large.png), [390px missing images](labels-390-missing.png), [390px large font and missing images](labels-390-large-missing.png)

Ready for the next independent review at the updated PR head; no self-approval, merge or deployment.

## Follow-up: confirmed design applied in the same PR (2026-10-18)

The user confirmed the complete six-level animal-and-label preview, after earlier requesting visual confirmation before code changes. Labels now read L1 清爽透气, L2 轻薄衣物, L3 薄外套, L4 中等厚度, L5 保暖外套, L6 厚实保暖. Fill/stroke/text colors match that preview, retaining asymmetric shapes. The L2 preview's softer yellow-green replaces the brighter previous version. "冷热变化大" uses pastel apricot and the existing wide illustration only on featured cards. Lack of a daytime indicator is presented as neutral text, not a graded color.

**Evidence freshness:** The existing screenshots above and historical passing browser results predate this new palette and label mapping. At the new implementation, JavaScript syntax, a lightweight simulated-DOM smoke check of labels and image paths, CSS token checks, and calculated foreground/background contrast (minimum 5.24:1 across seven colored states) have been completed; these are not full browser renders or a new make test run. Before independent review, rerun the local fixture browser checks, icon regression, browser check, make test, and regenerate actual desktop/mobile screenshots. Safari remains unverified. The fixture server and optional browser dependencies are described in web/README.md.

## Directional packing-notice Scheme A follow-up (2026-10-18)

User chose **方案 A · 柔和区分** after viewing the separate four-card prototype, then explicitly allowed the additive response field and front/back integration in PR #51. This is the single authorized API exception in Issue #50; it does not change forecast/historical weather decisions. `packing_variation_kind` is nullable; forecast derives `cold` / `warm` / `mixed` only from the existing packing events (not the Chinese summary or separate early/late-day notes), history uses `mixed` when its existing notice covers colder and warmer conditions, and fixture examples use explicit kinds. The featured-card styles mirror Scheme A's pastel blue/amber/dual-toned background and original exclamation point. A separately approved small follow-up synchronizes only the result-page reminder's tint and its existing cold/hot/mixed illustration; the full server-authored advice and dates remain unchanged.

**Current verification status:** Source-level JS syntax and CSS/label checks were performed during edits; Python backend tests, full `make test`, optional Playwright tests and new desktop/mobile screenshots have not yet run in the current execution environment because the repository checkout and browser fixture server are unavailable here. Historical image files above predate this follow-up and are not evidence for new colors. Run the existing fixture server with `python3 -m web.server --fixtures --port 8001`, `make test`, then `node tests/web/icon-regressions.cjs` and `node tests/web/warmth-label-regressions.cjs` using an environment with the optional Playwright install, visually check 320/390/1280px and long Chinese text before independent review. No deployment, merge, or independent review implied.

## Detail-view directional reminder follow-up (2026-10-18)

The user explicitly approved bringing Scheme A to the existing result-page notice on PR #51. The result page now uses the already-returned `packing_variation_kind` to select muted blue and `alert-cold`, warm amber and `alert-hot`, or the blue/orange gradient and `alert-variation`. Historical risk retains its non-forecast title, and both all-day and personal result views keep the unmodified complete advice/date text. Subsequent navigation clears the previous direction, and a missing/unknown kind falls back to the original generic notice; no weather rules, API shape, city-list logic or cache changes were made in this follow-up.

**Checks performed in this chat for the updated files:** Parse of the actual top-level-await JavaScript module via an async-function wrapper; syntax of the augmented browser regression file; static CSS brace check. Execution of the actual result-rendering directional code block with a minimal fake DOM validated cold, warm, mixed, no notice, rerender and unknown/missing direction; calculated text/background contrast is 6.56:1 (cold), 5.72:1 (warm), and 6.52–7.28:1 at the mixed-gradient stops. These **do not establish visual browser behavior**. Existing user screenshots show a live-data *warm* case **before** this detail view follow-up; they do not verify this head or the other cases.

**Still not run for this updated head:** `make test`, full fixture-driven Playwright suite (particularly `node tests/web/browser.cjs --check-only`), actual current-version desktop/320px/390px screenshots or a new live Open-Meteo walkthrough. This tool environment has no complete local checkout and GitHub hostname resolution for `git clone` failed; do not report checks as passed. Run the existing deterministic offline tests and use actual live data for end-to-end verification when available, without trying to force all three variation types from a single forecast day. PR remains Draft awaiting these results, independent review and separate merge approval.

## Python 3.9 local test-run follow-up (2026-10-19)

The user executed `make test` on macOS using Xcode Command Line Tools Python 3.9: **98 tests ran, 2 assertion failures, overall FAILED**. Both failing subtests are in `test_dev_commands.DevCommandTests.test_existing_inaccessible_directories_fail_before_listening`, one for history/one for forecast, specifically the `stat` injection. Rather than the expected injected PermissionError, `sitecustomize.py` caused `TypeError: stat() takes exactly 1 positional argument (2 given)`. Root cause: the test patched `os.stat` with an ordinary Python function; Python 3.9's pathlib accessor can bind it and supply an extra positional argument. This failure originated in the main-branch dev-startup regression tests merged by PR #53, not from the clothing advice or the new direction API.

**Narrow test-only repair in the same PR #51:** update the test's injected os.stat/os.scandir hook to a callable object with `__call__`, which is not a method descriptor; preserve both intended PermissionError cases, the no-listener assertion, and other checks. No application runtime code changed to address these failures.

**Actual post-edit checks:** fetched the updated source, verified all four subtests and their assertions remain, and ran an isolated Python 3.13 callable/nonbinding + target-path PermissionError check for both `stat` and `scandir`. **Not yet run:** the user's actual macOS Python 3.9 `make test` or full browser verification at this updated head. Previous real failure is not claimed resolved until the macOS rerun passes.
