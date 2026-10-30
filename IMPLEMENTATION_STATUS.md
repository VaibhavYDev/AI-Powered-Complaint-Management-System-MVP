# Implementation status

Updated at meaningful checkpoints so the work can be resumed without repeating the audit.
States: NOT STARTED · IN PROGRESS · VERIFIED · BLOCKED (EXTERNAL) · FAILED

| Phase | State | Evidence |
|---|---|---|
| 0 Live deployment | BLOCKED (EXTERNAL) | Code-side work done and verified; Render sync needs dashboard access |
| 1 Security & correctness | VERIFIED | Merged in PR #1; 211 backend tests green on `main` (CI run on `d68afdd` succeeded) |
| 2 Evidence & human review | VERIFIED | Backend + reviewer UI work together; full workflow exercised in a browser (extract -> flagged unsupported value -> acknowledge -> approve -> export -> edit revokes approval at revision 2) |
| 3 Care Documentation Reliability Lab | VERIFIED | Backend, checks and UI; verified in a browser with the real model on a synthetic German and English note: 3 observations attributed to 2 residents, the wound-versus-care-plan gap raised, approve and mock export |
| 4 Real-model evaluation | NOT STARTED | |
| 5 Provider reliability & observability | NOT STARTED | |
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

Phases 2 and 3 are complete and verified in a browser against the real model
(`openai/gpt-oss-20b`).

Two defects found by real runs rather than by tests, both fixed with regression tests:
- resident names were compared with honorifics attached, so a note saying "Frau Anna Keller"
  did not match a care plan saying "Anna Keller" and produced false documentation gaps;
- the negation check read backwards past the end of a sentence, so "No pain reported." for one
  resident flagged the next resident's mobility entry.

Next, in order:
1. Phase 4 benchmark and real-model evaluation. A working Groq key is in `backend/.env`; the
   model actually served is `openai/gpt-oss-20b` because `gemma2-9b-it` is retired.
2. Phase 5 provider reliability and telemetry.
3. Phase 6 remaining QA, Phase 7 README.
4. Phase 8 deployment, once the Render sync below is done.
