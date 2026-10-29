# Implementation status

Updated at meaningful checkpoints so the work can be resumed without repeating the audit.
States: NOT STARTED · IN PROGRESS · VERIFIED · BLOCKED (EXTERNAL) · FAILED

| Phase | State | Evidence |
|---|---|---|
| 0 Live deployment | BLOCKED (EXTERNAL) | Code-side work done and verified; Render sync needs dashboard access |
| 1 Security & correctness | VERIFIED | Merged in PR #1; 211 backend tests green on `main` (CI run on `d68afdd` succeeded) |
| 2 Evidence & human review | IN PROGRESS | Backend complete and verified (215 tests): atomic review transitions, mandatory acknowledgment of unsupported values. Reviewer **UI not built**: API client and Redux actions are in place, the panel component is not |
| 3 Care Documentation Reliability Lab | NOT STARTED | |
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

Done and verified on this branch:
- Review decisions are applied by one conditional UPDATE guarded by owner, revision **and**
  pending status, so two reviewers cannot both write and a decision cannot silently overwrite
  another. Covered by `test_two_reviewers_cannot_both_apply_a_decision` and a direct stale-
  revision test.
- Approving a record that still holds values absent from the source is refused with 422 until
  `acknowledge_unsupported` is set; a fully supported record needs no acknowledgment.
- Frontend groundwork: `api.approve/reject/history/exportRecord` and the `decide` / `loadHistory`
  Redux thunks. Additive - 13 frontend tests and the production build still pass.

Next step, in order:
1. `frontend/src/components/ReviewPanel.jsx` consuming `decide` / `loadHistory`, plus per-field
   evidence badges in `ComplaintForm.jsx` (verbatim / normalized / derived / unsupported /
   user_supplied) and the source text. Nothing consumes the new store actions yet.
2. Phase 3 Care Documentation Reliability Lab.
3. Phase 4 benchmark and real-model evaluation (a working Groq key is in `backend/.env`; the
   model actually served is `openai/gpt-oss-20b`, since `gemma2-9b-it` is retired).
4. Phases 5-7, then deployment once the Render sync below is done.
