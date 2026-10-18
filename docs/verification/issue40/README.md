# Issue #40 — committed warmth icons

Validated locally against the offline fixture server (`python3 -m web.server
--fixtures --port 8001`) with installed Chrome and the existing ignored Playwright
installation. No provider calls, deployment or icon binary changes.

- `python3 -m unittest discover -s tests/web -q`: 81 passed, including all 40
  allowlisted icon byte/MIME responses and traversal/unlisted-path rejection.
- `python3 -m unittest discover -s experiments/clothing-rules -q`: 122 passed.
- `node tests/web/icon-regressions.cjs`: passed levels 1–6, variation/null and
  no-daytime-reference states, 320/390/1280px at 1x/2x, selected WebP requests
  without duplicate PNG requests, PNG retry and complete image failure. Result
  reminder text remains readable with every icon blocked. Normal icon loads
  returned 200. Home and result screenshots inspected locally.
- `UI_BASE_URL=http://127.0.0.1:8001 node tests/web/browser.cjs --check-only`:
  63 checks passed, including 200% Chinese text and mobile overflow checks.
- Same base URL with `history-browser.cjs`: 27 checks passed;
  `featured-regressions.cjs`: 10 passed; `review-regressions.cjs`: 35 passed.
- `git diff --check`: passed.

The existing history test now checks level artwork instead of the removed SVG.
The general browser suite's invalid-date wait now checks the existing visible
error text; main already omits a retry button for invalid requests. Neither
change modifies application error behavior.

Reminder input supplies generic variation text rather than a structured cold/hot
kind, so reminders use `alert-variation`; no frontend classification from prose,
temperatures or preference. All supplied cold/hot/landscape assets are served by
the exact allowlist but are not assigned speculative meanings. Backend selection,
weather, copying and sharing remain unchanged. WebP-unsupported browser selection
uses standard picture/PNG markup; Chrome validation directly exercised WebP
failure to PNG and failure of both formats.

## Review #5561693950 follow-up

Featured cards now render a separate decorative generic variation icon beside
`packing_variation_summary`, preserving the primary level indicator and summary
text. No summary means no warning row. No weather rules or icon binaries changed.

The focused browser regression first failed on the reviewed head because the
separate warning icon was absent. After the fix, `node
tests/web/icon-regressions.cjs` passed, including colder/L2, warmer/L4, stable/L4
(no warning), and split/null cards at 320/390/1280px; summary equality, decorative
ARIA, retained primary artwork, no horizontal overflow, and readable warning
text under PNG fallback and total image failure. The 390px colder-card screenshot
was inspected locally. The existing browser suite (`UI_BASE_URL=http://127.0.0.1:8001
node tests/web/browser.cjs --check-only`) passed all 63 checks. `git diff --check`
also passed. These follow-up runs used offline fixtures only.
