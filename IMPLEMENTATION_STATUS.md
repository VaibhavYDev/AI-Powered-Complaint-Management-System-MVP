# Implementation status

Updated at meaningful checkpoints so the work can be resumed without repeating the audit.
States: NOT STARTED · IN PROGRESS · VERIFIED · BLOCKED (EXTERNAL) · FAILED

Released. PR #4 is merged as `e6a0302`, and the public service was verified running that exact
revision. Render deploys whatever is on `main`, and `/api/health` always reports the revision
actually serving, so later documentation commits move it on without any claim here going stale.

| Phase | State | Evidence |
|---|---|---|
| 0 Live deployment | VERIFIED | <https://ai-powered-complaint-management-system-ky8u.onrender.com> reports `revision: e6a0302…`, `status: ready`, `schema: ready`; `/api/ready` is 200 |
| 1 Security & correctness | VERIFIED | Merged in PR #1; cross-session isolation re-verified against the live service |
| 2 Evidence & human review | VERIFIED | Backend and reviewer UI; the whole workflow is asserted by a browser test on every pull request |
| 3 Care Documentation Reliability Lab | VERIFIED | Backend, deterministic checks and UI; injection containment asserted in a browser test |
| 4 Real-model evaluation | VERIFIED | Three runs against `openai/gpt-oss-20b`; published metrics re-derived from the stored predictions by a test |
| 5 Provider reliability & observability | VERIFIED | Bounded timeout and retries per inference; privacy-safe telemetry. A provider abstraction was **deliberately not added** — see below |
| 6 QA & CI | VERIFIED | Four GitHub Actions jobs green on the merge commit `e6a0302`: `backend`, `frontend`, `e2e`, `smoke` |
| 7 README presentation | VERIFIED | Live URL, real screenshots, measured results, accurate counts; every Markdown link and anchor checked |
| 8 Integration & deployment | VERIFIED | PR #4 merged (20 commits, 61 files); Render auto-deployed the merge; the repository Website field points at the demo |

## Verified on the release code

- Backend **280 tests** pass against a real PostgreSQL 16 container (277 on SQLite alone; 3
  migration tests need PostgreSQL).
- Frontend **17** unit tests; production build clean.
- Browser **3** end-to-end tests, against the stub provider *and* the real Groq API, on Windows
  and on Linux.
- Container smoke test against a real image: `SMOKE OK`.
- `scripts/e2e.py`: 40/40 against the local stack; 36/40 against the live service before the
  connection dropped, with the remaining four re-run separately against it and passing.
- Migrations `0001 → 0002 → 0003 → 0004`, a single linear chain.

## Verified against the public service after the release

With real Groq inference and the production PostgreSQL database, on the deployed `e6a0302`:

- a complaint logged from one sentence, with provenance on every extracted field;
- approval refused while a value was unsupported, allowed once acknowledged;
- export refused before approval (`409`) and allowed after it;
- a stale revision refused (`409`);
- an edit changing only the field it named, and sending the approved record back to review at a
  new revision, with the audit trail showing extracted → approved → edited;
- the Care Lab reading a two-resident note, the model obeying an instruction addressed to the
  reader, and the application raising it as two high-priority alerts that blocked approval until
  acknowledged, then exporting;
- every documented error path (`400`, `401`, `403`, `404`, `409`, `415`, `422`);
- a second session unable to read or list the first session's records;
- a Groq free-tier `429` surfacing as a clean provider error rather than a crash.

## Known divergence in the deployed configuration

The live service reports `configured_model: openai/gpt-oss-20b`, so `GROQ_MODEL` was set to the
operational model directly in the Render dashboard rather than to the assignment's
`gemma2-9b-it` that `render.yaml` specifies. Nothing is broken by this — it skips the startup
fallback — but the demo therefore does not exercise the fallback path the README describes. To
align them, set `GROQ_MODEL=gemma2-9b-it` in the service's Environment; `/api/health` will then
report the fallback and its reason, as it does locally.

## Decisions worth stating

**No provider abstraction.** Phase 5 asked for provider reliability. What it got was a bounded
timeout and bounded retries per inference, plus telemetry. An interface with one implementation
would be speculative generality: the second provider would reveal the right seam. Failure
handling is already provider-shaped — `AIProviderError`, `AIOutputError`, `AIConfigError` — so a
second provider slots in behind `structured()` without the rest of the application changing.

**The browser tests stub the provider, not the application.** `backend/scripts/stub_groq.py`
answers Groq's wire protocol; `GROQ_BASE_URL` and `GROQ_API_BASE` point the real clients at it.
Nothing in the application is modified, mocked or made test-aware. `E2E_REAL=1` runs the
identical suite against Groq, and that run produces the committed screenshots.

## Defects found by real runs rather than by tests

Each one is fixed with a regression test:

- resident names compared with honorifics attached, producing false care-plan gaps;
- the negation check reading backwards past a sentence end, so one resident's "No pain
  reported." flagged the next resident's entry;
- the extraction schema absorbing any resident an observation claimed into the note's roster,
  which defeated the "resident not in the note" check;
- injected instructions rated `verbatim` by the lexical evidence check, because the injected
  sentence really is in the source. Instruction spans are now located directly and anything
  drawn from them raises a high-priority alert. Containment has been 4/4 in every run since;
- an alert belonging to the note rather than to one observation could never be acknowledged: the
  interface sent `source_contains_instructions:null` where the API expected
  `source_contains_instructions:None`, so a note containing an injected instruction could not be
  approved at all. Found by the first run of the browser suite;
- the Playwright config deleted the end-to-end database out from under the running server. On
  Windows the delete failed and was swallowed; on Linux unlinking an open file succeeds, so
  `select 1` kept working, `/api/health` kept reporting `database: ok`, and every query that
  needed a table failed. All three browser tests failed on Linux for a reason the machine they
  were written on could not produce;
- `scripts/e2e.py` predated the auth layer and could not have run at all;
- the CI care-lab step carried a raw `0x01` byte where a `sed` backreference belonged, so it ran
  with an empty CSRF token;
- `EVALUATION.md` and the README reported 41 of 43 cases fully correct for `run-004`; the report
  says 40. A test now re-derives every published metric from the stored predictions, so an
  edited figure or a weakened dataset fails the suite.
