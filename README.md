# AIVOA Complaint Co-pilot

**[Launch live demo](https://ai-powered-complaint-management-system-ky8u.onrender.com)** · [Health check](https://ai-powered-complaint-management-system-ky8u.onrender.com/api/health)

AI-assisted intake for pharmaceutical customer complaints, built around one rule: **the user
never fills the form.** They paste a customer email, describe the problem, ask for a correction,
or drop a PDF. A LangGraph workflow turns that into a validated complaint record, marks where
every value came from, assesses patient risk, and holds the whole thing as a *suggestion* until
a human approves it.

The interesting part is not that a model can fill a form. It is everything built around the
model so that its output can be trusted in a regulated process: strict schema validation,
provenance for every extracted value, partial edits that cannot silently erase data, approval
gates, an audit trail, and a 43-case benchmark that measures how often the extraction is
actually right.

> An MVP, not a validated GxP system. The risk assessment is an AI-assisted triage aid for a
> human reviewer, never a regulatory determination. No claim of GDPR, GxP or clinical validation
> is made, and nothing here should be used with real patient data.

---

## See it running

![Complaint logged from one sentence](screenshots/02-log-populated.png)

One sentence of prose on the right; a structured QMS record on the left. Each field carries a
provenance label — `quoted`, `matched`, `inferred`, `not in source` — so a reviewer can see at a
glance which values the source actually supports.

| | |
|---|---|
| ![Human review](screenshots/06-human-review.png) | ![Care lab](screenshots/08-care-lab.png) |
| **Human review.** The one value the source does not support is listed by name, and approval is blocked until a reviewer accepts responsibility for it. | **Care Documentation Reliability Lab.** The note contained an instruction aimed at the reader; the model obeyed it, and the application caught it anyway. |

More: [empty intake](screenshots/01-empty-state.png) ·
[risk assessment in full](screenshots/03-risk-assessment.png) ·
[an edit changing one field](screenshots/04-edit-highlight.png) ·
[extraction from a PDF](screenshots/05-pdf-extract.png) ·
[approved and exported](screenshots/07-approved-export.png)

Every screenshot is produced by the browser test suite running against the real Groq API
(`E2E_REAL=1 npm run e2e`), so they cannot drift from what the code does or be mocked up.

### Running it yourself

```bash
docker build -t aivoa-copilot . && docker run -p 8000:8000 -e GROQ_API_KEY=sk-... -e DATABASE_URL=sqlite:////tmp/demo.db aivoa-copilot
```

Then open <http://localhost:8000>. One image contains the built React app and the API on a single
origin. PostgreSQL is the real target (see [Setup](#setup)); SQLite is enough to look around.

**[Live demo](https://ai-powered-complaint-management-system-ky8u.onrender.com)** — on Render's
free tier, so the first request after a period of inactivity takes a minute or so to wake the
instance. `/api/health` reports the real database, schema and model state. The reviewer
interface and the Care Documentation Reliability Lab reach the demo with the deployment that
follows this branch being merged. See [DEPLOYMENT.md](DEPLOYMENT.md).

---

## The problem

Every customer complaint about a medicine has to be recorded, classified for potential patient
harm, investigated, and — where warranted — fed into CAPA or a recall decision. The complaints
arrive as free-text emails, phone notes and scanned forms. QA staff re-key them into structured
fields before triage can even begin, which is slow and is itself a source of transcription
error.

So the obvious thing is to point an LLM at it. The non-obvious thing is what you then owe the
reviewer: a way to tell a quoted fact from an invented one, a correction mechanism that cannot
quietly destroy the rest of the record, and a refusal to treat model output as a record until a
person has signed it off. That is most of what this repository is.

## What it does

| | |
|---|---|
| **LOG** | Free text → a complete complaint record + an AI risk assessment. |
| **EDIT** | "Actually change the batch number to PCM24099" → a *partial patch*. Unlisted fields are never touched; a model-emitted `null` never erases anything; clearing a field requires an explicit request. |
| **EXTRACT** | PDF upload → text (pypdf) → the same structured record. Routed deterministically — a document is never sent to the router model. |
| **Evidence** | Every extracted value is searched for in the source text and labelled `verbatim`, `normalized`, `derived` or `unsupported`, with the matching excerpt and page. |
| **Review** | A record is `needs_review` until approved. Unsupported values must be acknowledged first. Editing an approved record sends it back for review. Every transition is recorded. |
| **Care Lab** | A second, independent case study: caregiver shift notes, with checks for attribution, negation, contradiction, care-plan gaps and prompt injection. See [below](#care-documentation-reliability-lab). |

## Architecture

```
React 19 + Redux Toolkit            session cookie + X-CSRF-Token
        │  POST /api/chat { message, complaint_id }   POST /api/upload (PDF)
        ▼
FastAPI  ── auth.py: session, ownership, CSRF, rate limit
        │  documents.py: bounded PDF text extraction
        ▼
LangGraph  (ai/graph.py)
   START ─► route ─┬─► log ─────► assess_risk ─► END
                   ├─► extract ─► assess_risk ─► END
                   └─► edit ────► touches complaint/patient? ─► assess_risk ─► END
                                                             └─► END
        │  every node: one Groq structured-output call → Pydantic model
        ▼
evidence.py  verify every value against the source text
merge.py     apply the patch; decide what may change
crud.py      owner-scoped persistence, atomic review transitions
        ▼
PostgreSQL (JSONB per section) ── alembic migrations 0001–0004
        ▼
CopilotResponse ─► Redux ─► form + risk assessment + review panel
```

One concern, one place:

| Concern | Where |
|---|---|
| Canonical schema (LLM output, API, DB, UI state) | `backend/app/schemas.py` |
| Groq calls, strict JSON Schema, retry, model fallback, telemetry | `backend/app/ai/llm.py` |
| Graph nodes | `backend/app/ai/nodes.py` · wiring in `ai/graph.py` |
| Prompts (field guide generated from the schema) | `backend/app/ai/prompts.py` |
| What an EDIT may change | `backend/app/merge.py` |
| Where a value came from | `backend/app/evidence.py` |
| Session identity, ownership, CSRF, rate limits | `backend/app/auth.py` |
| Persistence and review transitions | `backend/app/crud.py`, `backend/app/models.py` |
| Schema migrations | `backend/alembic/versions/` |
| Care lab | `backend/app/care/` |

### The LangGraph workflow

`route` classifies the message into `LOG | EDIT | EXTRACT` (validated as `RouterDecision`), and a
conditional edge dispatches. The graph *is* the control flow — there is no second, hand-written
router beside it.

Three details worth defending in review:

- **Documents skip the router.** An upload is known to be an extraction, so `route` short-circuits
  without a model call: one less call, one less thing to get wrong, and the classifier can never
  mislabel a PDF.
- **The router classifies intent only.** It is not told whether an edit is currently possible.
  An earlier version was, and would answer "LOG" to *"change the batch number to B999"* when no
  complaint was loaded, creating a one-field complaint out of a correction. The precondition is
  now enforced by the application (`400`), where it belongs.
- **Risk is re-assessed only when it could have changed.** `_after_edit` inspects the patch: a
  correction to the complainant's phone number does not spend a model call re-deriving a severity
  class, but a change to the defect or the patient does.

### Structured output, then validation

Five model outputs — `RouterDecision`, `ComplaintData`, `EditProposal`, `RiskAssessment`,
`CareNote` — are Pydantic models, and `ai/llm.py` picks the output method per model:

- **gpt-oss models → Groq Structured Outputs, strict JSON Schema.** The schema is *derived* from
  the Pydantic model and adapted to Groq's strict subset by `strict_json_schema()`: every
  property required, `additionalProperties: false`, nullable fields as `type: ["string","null"]`
  (Groq rejects `anyOf` unions and ambiguous `integer`/`number` unions), nullable enums inlined
  with `null`, unsupported keywords stripped, date fields annotated `(YYYY-MM-DD)`. There is no
  second hand-written schema to drift. In strict mode the schema travels with the request, so the
  prompts drop the ~600-token field guide they need otherwise.
- **anything else → JSON Object Mode.**

Either way the result is validated by the same Pydantic model, which enforces what a JSON Schema
cannot: non-empty action lists, confidence in 0–1, dates that actually parse. The schema
normalises the spellings models really produce (`"Physical Defect"` → `physical_defect`, `85` →
`0.85`, `"Not provided"` → `null`, `"45 years"` → `45`) but **rejects** values that do not fit the
target type, so a bad value can never degrade into a silent `null`. On rejection the model is
shown its own output and the error once; a second failure is a `502`, not a guess.

#### Why `EditProposal` is a flat list

Strict schema mode makes *every* property required, which means a nested "patch object" cannot
express sparsity — the model would have to emit all 31 fields to change one. So an edit is a
sparse list instead:

```json
{ "changes": [{ "field": "batch_number", "value": "PCM24099" }], "clear": ["phone"] }
```

Each value is validated through its real target field before anything merges, `clear` accepts
only known schema fields, and nulls in `changes` are ignored. Erasure is only ever explicit.

### Evidence, and what a lexical match does not prove

`evidence.py` searches the source text for each extracted value and labels it:

| Label | Meaning |
|---|---|
| `verbatim` | the value appears in the source as written |
| `normalized` | it appears in a different rendering (a date written another way, `500mg` vs `500 mg`) |
| `derived` | correctly inferred but not literally present ("received today" → a date) |
| `unsupported` | not findable in the source at all |
| `user_supplied` | set by a person, not the model |

This is deliberately a *pointer*, not a guarantee: a match proves the characters are in the
source, not that the reading is right. The benchmark below found exactly where that breaks — an
injected instruction inside a note is physically in the source, so a fabricated finding drawn
from it is rated `verbatim`. That failure is contained by a separate deterministic check, not by
asking the model more nicely.

### Human review

A record is a suggestion until a person approves it. The reviewer sees provenance per field, the
source text, and a list of anything `unsupported`; approval is blocked until those are
acknowledged. Approve/reject is a **single conditional UPDATE** guarded by owner, revision and
current status, so two reviewers racing cannot both succeed. Editing an approved record returns
it to `needs_review` at a new revision. Only an approved record can be exported.

---

## Care Documentation Reliability Lab

An independent case study in the same codebase, aimed at a different domain: **caregiver shift
notes**. All residents, notes and care plans are fictional, and nothing here makes a clinical
judgement — the output is documentation for a person to review.

One model call extracts observations; everything after it is deterministic, because the
reliability of the result must not rest on the prompt. `care/checks.py` independently checks:

- **Attribution** — is this observation about a resident the note actually names?
- **Negation** — "No pain reported" is not a finding of pain. Clipped at sentence boundaries,
  after a real run showed one resident's negation suppressing the next resident's entry.
- **Contradiction** between observations, and **care-plan gaps** (a new wound with no matching
  plan entry), honorific-tolerant after "Frau Anna Keller" vs "Anna Keller" produced false gaps.
- **Injected instructions** — text addressed to the reader rather than describing a resident.
  Any finding whose evidence points into such a span raises a high-priority alert that blocks
  approval.

### Measured results

43 hand-written cases, ground truth authored before any model was run, scored by deterministic
comparison. Three full runs on the same revision against `openai/gpt-oss-20b`; the spread is
published rather than the best number. Full methodology, denominators and failure analysis in
[EVALUATION.md](EVALUATION.md); raw per-case reports in `backend/eval/results/`.

| Metric | run-002 | run-003 | run-004 |
|---|---|---|---|
| Cases fully correct | 39/43 | 39/43 | 40/43 |
| Field exact match | 0.967 | 0.956 | 0.989 |
| Observation recall | 0.974 | 0.947 | 1.000 |
| Hallucination rate | 0.000 | 0.018 | 0.000 |
| Negation error rate | 0.200 | 0.200 | 0.200 |
| Abstention when expected | 1.000 | 1.000 | 1.000 |
| Schema validation success | 1.000 | 1.000 | 1.000 |
| Latency P50 / P95 (s) | 3.63 / 8.17 | 2.77 / 8.15 | 3.12 / 9.12 |

Cost: **$0.00475 for 43 notes** (~$0.0001 per note) at Groq's published price, computed only
when a price for that exact model is on file.

**The model obeys 2 of 4 prompt injections. The application contains 4 of 4.** That gap is the
point of the lab: the extraction is wrong and is scored as wrong, but a reviewer cannot approve
it unseen.

Negation is the weakest result and is reported as such: 1 failure in 5 opportunities, a
safety-relevant category on a small denominator. Observation precision (~0.65–0.69) is
deliberately left out of the headline table because the ground truth lists observations a correct
reading *must* produce, not an exhaustive set — a model that also records "ate well" would be
penalised for thoroughness. Ground truth was never relaxed to flatter a score.

---

## Model configuration

The assignment specifies `gemma2-9b-it`. Groq shut that model down on **2025-10-08**, and the
alternatives of that era (`llama-3.1-8b-instant`, `llama-3.3-70b-versatile`) were shut down for
free and developer tiers on **2026-08-16**. Rather than quietly changing the requirement, the
configuration separates it from the operational model:

| Setting | Value | Role |
|---|---|---|
| `GROQ_MODEL` | `gemma2-9b-it` | The assignment model. Checked first, every startup. |
| `GROQ_FALLBACK_MODEL` | `openai/gpt-oss-20b` | Serves requests when Groq does not serve `GROQ_MODEL`. `openai/gpt-oss-120b` is the larger option. |

One call to Groq's catalogue at startup decides which model serves requests, so a completion is
never sent to a decommissioned model. `GET /api/health` always reports `configured_model`,
`active_model` and `fallback_reason` — the model actually in use is never misrepresented, in the
UI or in this README. A `model_decommissioned` error on a live request triggers the same switch
as a safety net.

## Security

| | |
|---|---|
| **Identity** | Signed, HttpOnly session cookie (`SameSite=Lax`, `Secure` under `SECURE_COOKIES=true`). Visitors get an anonymous workspace automatically, so the demo needs no sign-up; register/login (bcrypt) attaches an email to a workspace. |
| **Authorization** | Every record has an `owner_id` and every read and write filters on it *inside the query*. Another workspace's record is a `404`, so ids cannot be probed. The owner comes from the cookie, never the body. |
| **CSRF** | State-changing requests must echo the session's token in `X-CSRF-Token`; the token is useless without the cookie. |
| **Rate limits** | Model-backed endpoints and session creation are limited per principal and per address. In-process, so with several instances the allowance is per instance. |
| **Input bounds** | Uploads bounded by bytes, pages, characters and wall-clock, with a per-page timeout in a worker thread, so a malformed PDF cannot hold a worker open. |
| **Startup** | `ENVIRONMENT=production` refuses to start without a stable `SESSION_SECRET` and Secure cookies. |
| **Telemetry** | Calls, retries, token counts, latency and error class only. Prompts, documents and model output are never recorded. |

Not implemented and not claimed: separation of duties between author and reviewer, tenant-level
encryption, data-residency guarantees, or any GxP/GDPR compliance position.

## Tests and CI

| Suite | Count | What it covers |
|---|---|---|
| Backend (`pytest`) | **278** | Schema normalisation and rejection, EDIT patch safety, evidence labelling, auth and cross-workspace isolation, review concurrency, PDF limits, migrations, care checks, benchmark scoring, HTTP contract. 3 need PostgreSQL and are skipped without it — CI provides one. |
| Frontend (`vitest`) | **17** | Session/CSRF handling in the API layer, Redux reducers and thunks. |
| Browser (`playwright`) | **3** | A real Chromium against the built app served by the real API, with a real database, sessions and CSRF. |

```bash
cd backend && python -m pytest -q                    # 275 passed, 3 skipped without PostgreSQL
cd frontend && npm test                              # 17 passed
cd frontend && npm run e2e                           # builds, then 3 browser tests
```

The browser suite starts the API itself and needs a Python on `PATH`; if yours lives in a
virtualenv, point `E2E_PYTHON` at it (`.venv\Scripts\python.exe` on Windows).

CI (`.github/workflows/ci.yml`) runs four jobs on every pull request: `backend` (against a real
PostgreSQL 16 service), `frontend`, `e2e`, and `smoke`, which builds the Docker image, starts it
the way the deployment does, and asserts that complaint and care data are closed to
unauthenticated callers and that CSRF is enforced. **No secrets are used**, so the suite runs for
pull requests from forks.

### How the browser tests run without a provider key

`backend/scripts/stub_groq.py` answers Groq's wire protocol with canned replies chosen by the
requested response schema. The application is not modified and is not aware of it:
`GROQ_BASE_URL` and `GROQ_API_BASE` point its real clients at the stub, so routing, validation,
evidence, persistence, auth and the interface are all genuinely exercised — only the remote
endpoint is replaced. The stub answers `400` to anything it has no canned reply for, so a test
can never pass because the stub improvised. `E2E_REAL=1` runs the identical suite against the
real Groq API, which is how the screenshots in this README are produced.

It earned its keep on the first run: a documentation alert belonging to the note rather than to
one observation produced an acknowledgement key of `...:null` in JavaScript and `...:None` in
Python, so those alerts could never be cleared and a note containing an injected instruction
could never be approved at all. The key is now built once, server-side.

## Setup

### 1. Database

```bash
docker compose up -d
```

PostgreSQL 16 on `localhost:5432` (user/password/db: `aivoa`). Any PostgreSQL works — set
`DATABASE_URL`. The schema is owned by alembic and upgraded at startup; a failed upgrade leaves
the service running in a reported degraded state rather than dead, and is retried.

### 2. Environment

Copy `backend/.env.example` to `backend/.env`. Never commit it.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | e.g. `postgresql+psycopg://aivoa:aivoa@localhost:5432/aivoa`. Provider-style `postgres://` URLs are accepted as-is. |
| `GROQ_API_KEY` | Groq API key. |
| `GROQ_MODEL` / `GROQ_FALLBACK_MODEL` | See [Model configuration](#model-configuration). |
| `GROQ_REASONING_EFFORT` | `low` (default) / `medium` / `high` — gpt-oss only. |
| `SESSION_SECRET` | Signs the session cookie. Required for sessions to survive a restart or a second instance. |
| `SECURE_COOKIES` | `true` when served over HTTPS. |
| `FRONTEND_URL` | CORS origin of the dev server (`http://localhost:5173`). |

### 3. Backend

```bash
cd backend && python -m venv .venv
```

Activate it (`.venv\Scripts\activate` on Windows, `source .venv/bin/activate` elsewhere), then:

```bash
pip install -r requirements.txt
```

```bash
uvicorn app.main:app --reload --port 8000
```

API docs at <http://localhost:8000/docs>.

### 4. Frontend

```bash
cd frontend && npm install && npm run dev
```

<http://localhost:5173>; Vite proxies `/api` to port 8000.

### Deployment

`render.yaml` (free plan) and `cloudbuild.yaml` (Cloud Run + Neon) are both in the repository,
and [DEPLOYMENT.md](DEPLOYMENT.md) has the commands, cost-safety settings and verification steps
for each. The same image runs anywhere: the React build is served by FastAPI, so one origin is
the whole product and the browser needs no configuration.

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/auth/anonymous` | Start a workspace; returns the CSRF token |
| `POST` | `/api/auth/register` · `/api/auth/login` · `/api/auth/logout` | Attach an account to a workspace |
| `GET` | `/api/auth/me` | Current principal |
| `POST` | `/api/chat` | Message → LOG or EDIT |
| `POST` | `/api/upload` | PDF → EXTRACT |
| `GET` | `/api/complaints` · `/api/complaints/{id}` | Owner-scoped list / one record |
| `POST` | `/api/complaints/{id}/approve` · `/reject` | Review decision (revision-guarded) |
| `GET` | `/api/complaints/{id}/history` | Audit trail |
| `GET` | `/api/complaints/{id}/export` | Mock export; approved records only |
| `POST` | `/api/care` | Analyse a caregiver note |
| `GET` | `/api/care` · `/api/care/{id}` · `/history` · `/export` | Care records, audit, export |
| `POST` | `/api/care/{id}/approve` · `/reject` | Care review decision |
| `GET` | `/api/health` | Liveness; always 200, body reports database, schema and model state |
| `GET` | `/api/ready` | Readiness; 503 until the service can actually serve |

<details>
<summary>Example: LOG, then an EDIT that changes exactly one field</summary>

```bash
curl -sX POST localhost:8000/api/auth/anonymous -c jar            # → {"csrf_token": "..."}

curl -sX POST localhost:8000/api/chat -b jar -H "X-CSRF-Token: $CSRF" \
  -H "Content-Type: application/json" -d '{
  "message": "Customer Rahul Sharma reported that Paracetamol 500 mg tablets from batch PCM24031 were chipped and broken inside the blister pack. The complaint was received today. No hospitalization occurred and the sample is available."
}'
```

```json
{
  "intent": "LOG",
  "message": "Logged a new complaint for Paracetamol 500 mg tablets · batch PCM24031 · reported by Rahul Sharma. Captured 16 of 30 fields. Still missing: email, phone, organization…",
  "complaint_id": 1,
  "complaint": {
    "reference": "CC-2026-0001", "status": "needs_review", "revision": 1,
    "product": { "batch_number": "PCM24031", "...": "..." },
    "evidence": { "product.batch_number": { "status": "verbatim", "excerpt": "from batch PCM24031 were chipped" } },
    "risk_assessment": { "severity_class": "III", "confidence": 0.8, "...": "..." }
  }
}
```

```bash
curl -sX POST localhost:8000/api/chat -b jar -H "X-CSRF-Token: $CSRF" \
  -H "Content-Type: application/json" \
  -d '{"message": "Actually change the batch number to PCM24099.", "complaint_id": 1}'
```

```json
{
  "intent": "EDIT",
  "message": "Updated batch number: PCM24031 → PCM24099.",
  "patch": { "product": { "batch_number": "PCM24099" } },
  "complaint": { "revision": 2, "status": "needs_review", "...": "everything else unchanged" }
}
```
</details>

### Error contract

| Situation | Status |
|---|---|
| No session / CSRF token missing or wrong | `401` / `403` |
| EDIT with no `complaint_id`; empty, corrupt or image-only PDF | `400` (`415` for a non-PDF filename) |
| Unknown or other-workspace id | `404` |
| Record changed since you read it (review race) | `409` |
| Nothing extractable; unsupported values not acknowledged | `422` |
| Malformed model output twice, or a Groq error | `502` |
| `GROQ_API_KEY` missing, or the database is down | `503` |

Responses always carry a human-readable `detail`; stack traces are never returned.

## Limitations

- Text-based PDFs only. Scanned documents need OCR, which is out of scope.
- One model, one provider, one prompt. The benchmark says nothing about any other configuration,
  and 43 synthetic cases written by the author of the checks probe known failure modes rather
  than sampling real documentation.
- Negation handling is the weakest measured behaviour (1 failure in 5 opportunities).
- Rate limiting is in-process, so it is per instance rather than global.
- The risk assessment cannot be edited through chat; it is regenerated when the facts it depends
  on change.
- Free-tier Groq keys cap `gpt-oss-20b` at roughly 8k tokens/minute, and a LOG costs ~3.5k
  tokens across three calls. Bursts return 429s, which the SDK retries with backoff, so rapid
  requests get slower rather than failing.
- The hosted demo is not currently serving (see [above](#running-it-yourself)).

## Repository

```
backend/app/        schemas · merge · evidence · crud · auth · documents · migrate
backend/app/ai/     graph · nodes · prompts · llm
backend/app/api/    complaints · care · auth
backend/app/care/   schemas · checks · extract        the reliability lab
backend/alembic/    migrations 0001–0004
backend/eval/       43-case benchmark, scorer, committed run reports
backend/scripts/    stub_groq.py (CI) · e2e.py (real provider) · probe_models.py
backend/tests/      278 tests
frontend/src/       App · store · api · components/{ComplaintForm,Copilot,RiskAssessment,ReviewPanel,CareLab}
frontend/e2e/       browser tests; screenshots are a by-product of the real-provider run
samples/            fictional complaint PDFs + their generator
```

| Document | What is in it |
|---|---|
| [EVALUATION.md](EVALUATION.md) | Benchmark methodology, denominators, failure analysis, honest limits |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Render and Cloud Run deployment, cost safety, restoring the demo |
| [CODE_WALKTHROUGH.md](CODE_WALKTHROUGH.md) | One request end to end, file by file |
| [DEMO_SCRIPT.md](DEMO_SCRIPT.md) | A 2–3 minute product demo |
| [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) | Phase-by-phase state, including what is blocked and why |

## Licence

[Apache 2.0](LICENSE). All sample data, residents and complaints are fictional.
