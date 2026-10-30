# Implementation status

Updated at meaningful checkpoints so the work can be resumed without repeating the audit.
States: NOT STARTED · IN PROGRESS · VERIFIED · BLOCKED (EXTERNAL) · FAILED

| Phase | State | Evidence |
|---|---|---|
| 0 Live deployment | BLOCKED (EXTERNAL) | Code-side work done and verified; the Render sync needs dashboard access |
| 1 Security & correctness | VERIFIED | Merged in PR #1; CI green on `main` (`d68afdd`) |
| 2 Evidence & human review | VERIFIED | Backend and reviewer UI; the whole workflow is now asserted by a browser test on every pull request |
| 3 Care Documentation Reliability Lab | VERIFIED | Backend, deterministic checks and UI; injection containment asserted in a browser test |
| 4 Real-model evaluation | VERIFIED | 43-case benchmark run three times against `openai/gpt-oss-20b`; results in `EVALUATION.md` and `backend/eval/results/`; two real defects found and fixed |
| 5 Provider reliability & observability | VERIFIED | Bounded timeout and retries per inference; privacy-safe telemetry used by the benchmark. A provider abstraction was **deliberately not added** — see below |
| 6 QA & CI | VERIFIED | Four CI jobs: `backend` (real PostgreSQL), `frontend`, `e2e` (real browser), `smoke` (real container) |
| 7 README presentation | VERIFIED | Rewritten around real screenshots, measured results and accurate counts; every Markdown link and anchor checked |
| 8 Integration & deployment | BLOCKED (EXTERNAL) | PR #1 and #3 merged; PR #2 superseded; opening the PR for this branch and deploying both need account access |

## Verified facts

- Backend **279 tests** (276 pass locally; 3 need PostgreSQL and run in CI).
- Frontend **17 unit tests** and **3 browser end-to-end tests**.
- The browser suite passes against the stub provider *and* against the real Groq API.
- The CI smoke job was replayed locally against a real container, step for step: `SMOKE OK`.
- The CI e2e job was replayed on Linux from a clean `git archive` checkout: `3 passed`. It found
  a harness bug that could not reproduce on Windows (below), so the first two replays failed.

## Decisions worth stating

**No provider abstraction.** Phase 5 asked for provider reliability. What it got was a bounded
timeout and bounded retries per inference, plus telemetry. An interface with one implementation
would be speculative generality: the second provider would reveal the right seam, and inventing
it now would mean inventing the wrong one. Failure handling is already provider-shaped —
`AIProviderError`, `AIOutputError`, `AIConfigError` — so a second provider slots in behind
`structured()` without the rest of the application changing.

**The browser tests stub the provider, not the application.** `backend/scripts/stub_groq.py`
answers Groq's wire protocol; `GROQ_BASE_URL` and `GROQ_API_BASE` point the real clients at it.
Nothing in the application is modified, mocked or made test-aware, so routing, validation,
evidence, persistence, auth and the interface are genuinely exercised. `E2E_REAL=1` runs the
identical suite against Groq, and that run produces the committed screenshots.

**Run the browser tests on the platform CI uses.** The Playwright config clears the
end-to-end database so each run starts empty, and it is also re-evaluated inside every worker,
by which time the API holds that file open. On Windows the delete fails and the failure was
swallowed. On Linux unlinking an open file succeeds, so a worker pulled the database out from
under the running server: `select 1` kept working, `/api/health` kept reporting `database: ok`,
and every query that needed a table failed, so the session endpoint answered 503 to everything.
All three tests failed on Linux for a reason the machine they were written on could not produce.

## Defects found by real runs rather than by tests

Each one is fixed with a regression test:

- resident names compared with honorifics attached, producing false care-plan gaps;
- the negation check reading backwards past a sentence end, so one resident's "No pain
  reported." flagged the next resident's entry;
- the extraction schema absorbing any resident an observation claimed into the note's roster,
  which defeated the "resident not in the note" check;
- injected instructions inside a note rated `verbatim` by the lexical evidence check, because
  the injected sentence really is in the source. Instruction spans are now located directly and
  anything drawn from them raises a high-priority alert. Containment has been 4/4 on the
  adversarial cases in every run since;
- **a documentation alert belonging to the note rather than to one observation could never be
  acknowledged**: the interface sent `source_contains_instructions:null` where the API expected
  `source_contains_instructions:None`, so a note containing an injected instruction could not be
  approved at all. Found by the first run of the browser suite. The key is now built once,
  server-side, and sent to the client;
- the CI care-lab step carried a raw `0x01` byte where a `sed` backreference was meant to be, so
  it ran with an empty CSRF token.

## Blocker: live deployment

`https://aivoa-complaint-copilot.onrender.com` accepts the TCP connection and returns **no bytes
within 90s** (re-checked at this checkpoint). A nonexistent Render subdomain returns `404` in
under a second, so the service is registered but has **no healthy instance**.

Two causes were found; both are fixed in the repository:

1. `render.yaml` requested a paid instance plus a paid PostgreSQL add-on, so the blueprint could
   never sync without payment. It now requests the **free** plan.
2. Startup connected to the database with no timeout, so an unreachable database stopped the
   process from ever binding its port. Fixed and measured: the container now serves the UI in
   **8 seconds** against a blackholed database, reporting `status: degraded`.

**Outstanding external action** (no payment required, about two minutes):

1. Render dashboard → `aivoa-complaint-copilot` → **Manual Sync** (or **Resume** if suspended).
   The blueprint keeps its last applied spec, which is why merging the fix did not change
   anything by itself.
2. Service → **Environment** → set `DATABASE_URL` (Neon pooled connection string) and
   `GROQ_API_KEY`. Leave the Render-generated `SESSION_SECRET` untouched.

No Render API key exists in this environment or the repository, so the sync cannot be triggered
from here. The README lists the demo as broken rather than linking it as if it worked.

## Blocker: pull request for this branch

`gh` is not installed and the GitHub connector in this session is unauthenticated, so the branch
can be pushed but the pull request cannot be opened from here. Branch:
`feat/review-ui-and-care-lab`, based on `main` (`d68afdd`).

PR #2 is superseded: every commit on `feat/evidence-and-review` is an ancestor of `main`. It
should be closed rather than merged.
