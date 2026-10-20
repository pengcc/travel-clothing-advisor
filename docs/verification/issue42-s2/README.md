# Issue #42 / Plan v7 S2 implementation evidence

2026-10-20. Base: `main@47f6bc4db244319bcec1f4c630429e7b07a00ff0`
(S1 merged via #60). Authority: [Plan v7](https://github.com/pengcc/travel-clothing-advisor/issues/42#issuecomment-6275631500),
[clean Plan review](https://github.com/pengcc/travel-clothing-advisor/issues/42#issuecomment-6287947625),
[approval](https://github.com/pengcc/travel-clothing-advisor/issues/42#issuecomment-6288040000),
and the user's current request to implement S2 and create a new Implementation PR.
S1 recorded 106 passing tests and synthetic browser evidence in PR #60. Its hosted
Preview measurements remain unverified; this S2 PR does not bypass that gate.

## Delivered contract

A local publisher selects **one** trusted city record, one current Germany-day
forecast JSON and one validated archive JSON.gz month from existing prepared
objects. It copies no usage ledgers, job state, user queries or unrelated cache.
Existing identity, format, timestamps, hours, archive lag and inner checksum
validators run before any upload. An outer manifest records byte counts and
SHA-256 values. The manifest's byte hash names the entire immutable version.

The publisher uploads `preview/<trial>/versions/<hash>/...` with overwrites off,
reads back all three objects and the manifest, revalidates, then overwrites only
`preview/<trial>/current.json`. Interrupted uploads leave the current reference
unchanged; abandoned immutable objects are retained for operator inspection.
An ambiguous pointer write failure may already have switched it: inspect before
retrying. Resume only reuses exactly matching bytes. No delete/garbage collection,
automatic retries, CAS claim, cross-host lock or exactly-once guarantee is added.
A local nonblocking flock serializes the CLI on one host; **only one trusted host
and publisher may own a namespace**. This is a trial precondition, not a global lock.

Each request reads the pointer once, then the selected manifest and three objects,
verifies all of them and retains a get-only in-memory snapshot for that request.
Even if the pointer changes mid-read, the request cannot mix versions. There is
no application-level cache or fallback to bundled data when remote mode is selected.
An older CDN pointer may select a complete older version only on the same Germany
day. Old-day manifests/forecasts fail closed, including rollback. API JSON carries
`dataset_version` on successful data responses; responses retain `Cache-Control:
no-store`. Immutable objects remain verifiable even when served from CDN cache.

The real Function selects remote mode only with `TRAVEL_PREVIEW_NAMESPACE` and
`VERCEL_ENV=preview`. Dedicated trial credentials are required; default/Production
Blob credentials and SDK local credential refresh are not used. Namespace prefix
checks are application guards, not storage IAM. Use a separate private store and
credentials that cannot access Production. Protection is an external deployment
prerequisite, not implemented or verified by this PR.

A one-city sample exercises personal forecast advice. It deliberately provides
neither the complete-ten featured manifest nor five complete annual histories.
Those paths remain 503; the single archive month proves validated storage reads,
not a historical answer. No new product partial-data behavior is introduced.

## Actual offline checks

- Final `PYTHONDONTWRITEBYTECODE=1 make test PYTHON=.local-tools/s2-venv/bin/python`:
  **114 tests OK** (7.264s), no skipped SDK checks. Earlier system-Python run:
  113 tests OK with one optional SDK check skipped, before the final extra
  credential-configuration regression was added.
- SDK environment: Python 3.11 and `vercel-blob==0.5.0` installed only in ignored
  `.local-tools/s2-venv`; actual SDK calls intercepted by `httpx2.MockTransport`.
  Private reads, missing objects, 403, size rejection and immutable/pointer upload
  flags checked without a Blob request. Dedicated configuration is required even
  when default credentials might exist; no default-token fallback occurs.
- S2 browser: `node tests/web/publication-browser.cjs`, synthetic-only, loopback,
  external browser requests blocked. Same running Function handler observes
  v1 → v2 → rollback and changed rule-driven advice. Test provenance remains in
  page, copied advice and shared text. Partial featured/history paths unavailable;
  widths 320/390/1280 checked. No hosted observation claimed.
- Existing S1 browser: `python3 tests/web/serve_readonly.py` plus
  `node tests/web/readonly-browser.cjs` for full-ten homepage, city, 14-day trip,
  five-year history, copy/share/reload and errors: **passed**.
- Fault tests: partial upload/resume, failed read-back, missing/corrupt objects,
  invalid outer/inner content, mismatched identity, stale/malformed pointer,
  concurrent pointer switch, wrong namespace, expired forecast and rollback.
- `git diff --check`: **passed**.
- `python3 -m unittest discover -s experiments/clothing-rules -v`: **122 tests
  OK** (0.183s).

Small synthetic sample: 7,684 source bytes; 8,385 bytes for one published version
including manifest and pointer. First publication: 8 object GET attempts + 5 PUTs;
request load: 5 GETs (pointer, manifest, cities, forecast, archive), then advice
uses memory only. At most 200,000 bytes per object, three sample objects. Candidate
transport uses 4s per-IO timeout, a cooperative 12s reader/60s publisher deadline,
no retry and bounded streaming reads. A blocking IO can run past the cooperative
deadline by its per-IO timeout. These are bounds, not hosted latency measurements.

One local in-memory diagnostic measured approximately 1.5ms publication and 1.8ms
load + advice. This excludes network, cold start and hosting, and is not a cloud
performance prediction. No provider/weather download, retained cache mutation,
cloud provisioning/upload, protected deployment, paid resource or merge occurred.

## Candidate documentation, not hosted proof

Official sources checked 2026-10-20:

- [Python SDK reference](https://vercel.com/docs/vercel-blob/python-sdk-reference):
  `vercel-blob>=0.5.0`, Python >=3.10, synchronous stream/put APIs and upload flags;
  Python lacks cache bypass and conditional uploads. Installed 0.5.0 checked locally.
- [Private storage](https://vercel.com/docs/vercel-blob/private-storage): authenticated
  delivery and CDN caching. We request 60s upload cache lifetime; stale-read bounds
  and actual time-to-visibility must still be measured on the chosen store.
- [Pricing and limits](https://vercel.com/docs/vercel-blob/usage-and-pricing): Hobby
  includes 1 GB-month storage, 10,000 simple and 2,000 advanced operations; other
  delivery/CDN/function usage also matters. This tiny sample is below storage limits;
  it cannot establish account headroom. For a pessimistic 5 cache misses per request,
  10,000 simple operations covers about 2,000 loads before subtracting publication,
  dashboard and other usage. CDN hits and billing operations are different counts.
  Measure actual usage before claiming no-cost feasibility.

## Remaining separately authorized operational trial

After independent review and explicit external-action permission, establish S1
protected hosted operation first. Then provision/select the isolated private store,
configure only Preview, and supply authorized real prepared inputs. Publish v1;
record bytes/operations/timings. On the **same deployment**, publish same-day v2;
poll a bounded number of normal personal advice requests and record deployment ID,
version, changed advice and elapsed visibility (without retaining trip inputs,
credentials or raw metadata in logs). Exercise wrong token, failed partial upload,
missing/corrupt objects, invalid manifest, stale pointer, Berlin rollover and
same-day rollback; confirm Production cannot read or be written by the trial.
Separately measure function cold start, resource usage, data-read latency and usage
headroom. STOP if measured cache/visibility behavior cannot meet a truthful bound;
do not add another vendor, DB or JS CAS bridge. Rollback switches only the pointer
to a revalidated same-day version; a previous-day version is unavailable.

**Disposition:** code/offline trial delivered, hosted S2 feasibility unverified.
Independent Implementation Review, merge and external trial require their respective
next instructions. #42 was already closed when this work began, contrary to v7's
closeout requirement; this PR does not auto-close it or alter its state. Public P0
for #42/#38, online misses, global budgets and autonomous history completion remain
unresolved. S0–S2 never authorize public readiness or S3.

## PR #61 P2 remediation — existing separate caches

The publisher now accepts `--forecast-dir .forecast-local --history-dir
.history-local --cities-file .forecast-local/cities.json`, with the existing
city/month/namespace arguments. This selects the same three validated sample
objects directly, without manual staging, scanning/uploading cache directories,
or touching worker/control files. Single-root `--source` remains supported;
incomplete or mixed source modes are rejected. The metadata file is bounded to
200,000 bytes and its selected record must match both weather source identities.

Added an actual CLI dry-run regression with separate synthetic cache trees,
multiple cities, worker locks and ledger sentinels. It verifies the exact two
weather object reads, identical selected version, unchanged trees, no publisher
lock/Blob session access, and missing/corrupt metadata/forecast/archive failure.
Final remediation validation: SDK-environment `make test` **115 tests OK** (7.650s)
and `git diff --check` passed. No actual retained-cache inspection, provider call,
cloud upload or deployment was needed. Independent Re-review remains pending.
