# Implementation status

Updated at meaningful checkpoints so the work can be resumed without repeating the audit.
States: NOT STARTED · IN PROGRESS · VERIFIED · BLOCKED (EXTERNAL) · FAILED

| Phase | State | Evidence |
|---|---|---|
| 0 Live deployment | BLOCKED (EXTERNAL) | Code-side work done and verified; Render sync needs dashboard access |
| 1 Security & correctness | VERIFIED | Merged in PR #1; 211 backend tests green on `main` (CI run on `d68afdd` succeeded) |
| 2 Evidence & human review | VERIFIED | Backend + reviewer UI work together; full workflow exercised in a browser (extract -> flagged unsupported value -> acknowledge -> approve -> export -> edit revokes approval at revision 2) |
| 3 Care Documentation Reliability Lab | VERIFIED | Backend, checks and UI; verified in a browser with the real model on a synthetic German and English note: 3 observations attributed to 2 residents, the wound-versus-care-plan gap raised, approve and mock export |
| 4 Real-model evaluation | VERIFIED | 43-case benchmark run three times against `openai/gpt-oss-20b`; results in `EVALUATION.md` and `backend/eval/results/`; two real defects found and fixed |
| 5 Provider reliability & observability | IN PROGRESS | Privacy-safe telemetry (calls, retries, tokens, latency, error class) added and used by the benchmark; provider abstraction outstanding |
| 6 QA & CI | IN PROGRESS | CI green on `main`; browser E2E outstanding |
| 7 README presentation | IN PROGRESS | Live-demo section honest; screenshots predate the review UI |
| 8 Integration & deployment | BLOCKED (EXTERNAL) | PR #1 and #3 merged; PR #2 superseded; deployment blocked |

## Verified facts

- `main` = `d68afdd`. CI (`backend`, `frontend`, `smoke`) **passed** on that commit.
- Backend 211 tests, frontend 13 tests, PostgreSQL migration tests green against a disposable
  PostgreSQL 16 container.
- PR #1 merged, PR #3 merged. **PR #2 is superseded**: every commit on
  `feat/evidence-and-review` is an ancestor of `main`. It targets a branch that no longer
  exists as a merge base and should be closed rather than merged.

## Blocker: live deployment

`https://aivoa-complaint-copilot.onrender.com` accepts the TCP connection and returns **no bytes
within 120s**. A nonexistent Render subdomain returns `404` in under a second, so the service is
registered but has **no healthy instance**.

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
from here.

## Resume checkpoint

Branch `feat/review-ui-and-care-lab`, based on `main` (`d68afdd`).

Phases 2, 3 and 4 are complete and verified. Phase 5 is part done.

Real defects found by real runs rather than by tests, each fixed with a regression test:
- resident names compared with honorifics attached, producing false care-plan gaps;
- the negation check reading backwards past a sentence end, so one resident's "No pain
  reported." flagged the next resident's entry;
- the extraction schema absorbing any resident an observation claimed into the note's roster,
  which defeated the "resident not in the note" check;
- injected instructions inside a note being rated `verbatim` by the lexical evidence check,
  because the injected sentence really is in the source. Instruction spans are now located
  directly and anything drawn from them is raised as a high-priority alert. Containment has
  been 4/4 on the adversarial cases in every run since.

Next, in order:
1. Finish Phase 5: minimal provider abstraction and backoff with jitter.
2. Phase 6: browser end-to-end coverage in CI.
3. Phase 7: README rewrite with the measured results and fresh screenshots.
4. Phase 8: deployment, once the Render sync below is done.
