# AIVOA Complaint Co-pilot

AI-powered Customer Complaint intake for a pharmaceutical Quality Management System (QMS).
Built for the AIVOA "AI Product Engineer (Interns)" Round 1 assignment.

The user never fills the complaint form by hand. They talk to the **AIVOA Co-pilot** — paste a
customer email, describe the issue, ask for a correction, or upload a complaint PDF — and a
LangGraph workflow turns that into a validated, persisted complaint record plus an AI-assisted
risk assessment. The form on the left is a live view of that structured state.

> This is an MVP that demonstrates the workflow. It is not a validated GxP system and makes no
> claim of regulatory compliance. The risk assessment is an AI-assisted triage aid for a human
> reviewer, not a regulatory determination.

## Problem

In API and finished-dosage-form manufacturing, every customer complaint must be recorded,
classified for potential patient risk, investigated and — where warranted — feed into CAPA or
recall decisions. Complaints arrive as free-text emails, phone notes and PDF forms, and QA staff
spend a lot of time re-keying that information into structured QMS fields before triage can even
begin. This project removes the re-keying step and gives the reviewer a first-pass risk triage
immediately.

## Key features

- **LOG** — natural-language complaint → structured complaint record + AI risk assessment
- **EDIT** — conversational corrections ("change the batch number to PCM24099") applied as a
  *partial patch*; nothing else in the record is touched
- **EXTRACT** — PDF upload → text extraction (pypdf) → structured complaint
- **AI-assisted risk assessment** — severity class I/II/III, reasoning, immediate actions,
  recommended follow-up, confidence; regenerated after edits that change complaint or patient facts
- Strict boundary: LLM → structured JSON → Pydantic validation → application logic → PostgreSQL.
  The model never touches the database and the frontend never sees raw model output.
- Honest about missing data: anything not stated stays `null`; the co-pilot tells you which
  fields are still missing.

## Architecture

```
React + Redux Toolkit (frontend)
        │  POST /api/chat  { message, complaint_id }        POST /api/upload (PDF)
        ▼
FastAPI (backend/app/api/complaints.py)
        │  loads existing complaint (if any)                pypdf text extraction
        ▼
LangGraph (backend/app/ai/graph.py)
   START ─► route ─┬─► log ─────► assess_risk ─► END
                   ├─► extract ─► assess_risk ─► END
                   └─► edit ────► (touches complaint/patient?) ─► assess_risk ─► END
                                                             └─► END
        │  every node = one Groq structured-output call, validated into a Pydantic model
        ▼
Application logic: patch merge (merge.py) · persistence (crud.py) · SQLAlchemy JSONB (models.py)
        │
        ▼
CopilotResponse { intent, message, complaint_id, complaint, patch?, risk_assessment? }  ─► Redux ─► form
```

Responsibilities, one place each:

| Concern | Where |
|---|---|
| Canonical complaint schema (Pydantic) | `backend/app/schemas.py` |
| Prompts (field guide is generated from the schema) | `backend/app/ai/prompts.py` |
| Groq calls, strict-schema / JSON-mode structured output, retry, model fallback | `backend/app/ai/llm.py` |
| Graph nodes: route / log / edit / extract / assess_risk | `backend/app/ai/nodes.py` |
| Graph wiring | `backend/app/ai/graph.py` |
| EDIT patch semantics (what may change, what never can) | `backend/app/merge.py` |
| Persistence | `backend/app/crud.py`, `backend/app/models.py` |
| HTTP endpoints + error mapping | `backend/app/api/complaints.py`, `backend/app/main.py` |

### LangGraph workflow

`route` is an LLM classification node that returns `{"intent": "LOG" | "EDIT" | "EXTRACT"}`
(validated by the `RouterDecision` model). A conditional edge dispatches to the matching node.
There is no second, hand-written router: the graph *is* the control flow.

- **LOG** (`log_complaint`): `ComplaintData` structured output from the message → `assess_risk`.
- **EDIT** (`edit_complaint`): the model receives the current record and returns an
  `EditProposal` — a sparse list of operations,
  `{"changes": [{"field": "batch_number", "value": "PCM24099"}], "clear": ["phone"]}`.
  Every value is validated through the canonical section models (so `"yes"` becomes `true`
  and a bad date is rejected), null values are ignored, and a field can only be nulled through
  `clear`, which accepts known schema fields only. `merge.patch_from` turns the proposal into
  `{section: {field: value}}` and `apply_patch` merges it into the existing record; unlisted
  fields are never touched. Risk is re-assessed only if the patch touched the `complaint` or
  `patient` sections, so a batch-number correction leaves the assessment untouched.
- **EXTRACT** (`extract_complaint`): same schema as LOG with a document-oriented prompt.
- **assess_risk**: `RiskAssessment` structured output from the (merged) complaint.

Nodes raise plain exceptions for expected failures (`NoComplaintToEdit`, `NothingExtracted`)
and `main.py` maps them to HTTP status codes, so endpoints contain no try/except.

### Structured output and validation

All four model outputs (`RouterDecision`, `ComplaintData`, `EditProposal`, `RiskAssessment`)
are Pydantic models in `schemas.py`; `ai/llm.py` chooses the Groq output method per model:

- **gpt-oss models → Groq Structured Outputs, strict JSON Schema** —
  `with_structured_output(strict_json_schema(Model), method="json_schema", strict=True)`.
  The schema is generated from the Pydantic model (`model_json_schema()`) and adjusted to
  Groq's strict subset: every property required, `additionalProperties: false` on each object,
  nullable fields written as `type: ["string", "null"]` (Groq rejects `anyOf` unions), nullable
  enums inlined with `null`, no `integer`/`number` overlap, unsupported keywords (`default`,
  `minLength`, `minimum`, `format`, …) removed, date fields annotated `(YYYY-MM-DD)`. There is
  no second, hand-written schema. In strict mode the schema travels with the request, so the
  prompts omit the field guide they embed for JSON-object-mode models (~600 tokens per call).
- **any other model → JSON Object Mode** — `with_structured_output(method="json_mode")`.

In both cases the model's JSON is validated by the same Pydantic model (`Model.model_validate`),
which also enforces the constraints the strict schema cannot express (non-empty lists,
confidence 0–1, unparseable dates rejected). If Groq or Pydantic rejects the output, the model
is shown the rejected JSON and the error and asked once for a corrected object; a second failure
becomes `502 The AI returned malformed … data`. The schema normalises common spellings
(`"Physical Defect"` → `physical_defect`, `85` → `0.85`, `"Not provided"` → `null`, `"45 years"` → `45`) but
rejects values that do not fit the target type (`"maybe"` for a boolean, `"forty-two"` for an age,
`"Packaging Defect"` for an enum), so a bad value can never turn into an accidental null.

### Groq model note

The assignment specifies `gemma2-9b-it`. Groq shut that model down on **2025-10-08**, and its
suggested replacements from that time (`llama-3.1-8b-instant`, `llama-3.3-70b-versatile`) were
shut down for free/developer tiers on **2026-08-16**. The configuration therefore separates the
assignment requirement from the operational model:

| Setting | Value | Role |
|---|---|---|
| `GROQ_MODEL` | `gemma2-9b-it` | Assignment model. Tried first, every startup. |
| `GROQ_FALLBACK_MODEL` | `openai/gpt-oss-20b` | Current Groq production model used when Groq reports `GROQ_MODEL` decommissioned. `openai/gpt-oss-120b` is the larger option. |
| — | `llama-3.3-70b-versatile` | Assignment-era alternative only; deprecated, not used as a fallback. |

At startup `ai/llm.py` makes one call to Groq's model catalogue (`GET /models`). If
`GROQ_MODEL` is not in it, the app switches to the fallback immediately and records why — no
completion request is ever sent to a decommissioned model. `GET /api/health` always reports
`configured_model`, `active_model` and `fallback_reason`, so the model in use is never
misrepresented. As a safety net, a `model_decommissioned` / `model_not_found` error on a live
request triggers the same switch. `scripts/probe_models.py` lists the models a key can access
and runs one structured call through the app's own code path.

`openai/gpt-oss-20b` supports Groq Structured Outputs (strict JSON Schema, used here) and returns
its reasoning in a separate `reasoning` field, so `content` is pure JSON for the parser.

## Code walkthrough guide

One request, end to end. Each step is one file and one function, in the order the code runs.

```mermaid
flowchart LR
    UI[React form + Co-pilot<br/>Redux slice] -->|POST /api/chat<br/>POST /api/upload| API[api/complaints.py<br/>chat / upload]
    API -->|load existing record| DB[(PostgreSQL<br/>models.py · crud.py)]
    API -->|run_copilot| G[ai/graph.py<br/>LangGraph]
    G --> R[route]
    R -->|LOG| L[log_complaint]
    R -->|EDIT| E[edit_complaint]
    R -->|EXTRACT| X[extract_complaint]
    L --> RA[assess_risk]
    X --> RA
    E -->|complaint/patient changed| RA
    E -->|otherwise| P
    RA --> P[_persist<br/>crud.create / crud.update]
    P --> DB
    P -->|CopilotResponse| UI
    subgraph every node
        S[ai/llm.py structured<br/>Groq strict JSON Schema → Pydantic]
    end
```

| # | Step | Where | What to say |
|---|---|---|---|
| 1 | User types a message or drops a PDF | `frontend/src/components/Copilot.jsx` → `store.js` thunks `sendMessage` / `uploadDocument` | The form is never typed into; Redux state only changes from validated API responses. `sendMessage` sends the current `complaint.id` so the backend knows whether an EDIT is possible. |
| 2 | Request arrives | `backend/app/api/complaints.py` → `chat()` / `upload()` | `ChatRequest` is validated by FastAPI. If `complaint_id` is given the record is loaded (404 if not). `upload()` runs `documents.extract_pdf_text` (pypdf) first. |
| 3 | Graph runs | `backend/app/ai/graph.py` → `run_copilot()` | `StateGraph`: `START → route → {log, edit, extract}`; `log`/`extract` always go to `assess_risk`; `edit` only if the patch touched `complaint` or `patient`. No hand-written router anywhere else. |
| 4 | Intent | `backend/app/ai/nodes.py` → `route()` | One model call returning `RouterDecision {intent}`. Documents are marked `[Uploaded document]`. |
| 5 | Model call | `backend/app/ai/llm.py` → `structured()` | The **only** place raw model output exists. gpt-oss → Groq strict JSON Schema derived from the Pydantic model (`strict_json_schema`); other models → JSON Object Mode. Result → `Model.model_validate()`. One corrective retry, then `502`. Model fallback lives here too (`resolve_model`). |
| 6a | LOG / EXTRACT | `nodes.py` → `log_complaint()` / `extract_complaint()` | Output type is the canonical `ComplaintData`; unstated facts are `null`; empty extraction → `422`. Reply text is built deterministically (`_summarize`). |
| 6b | EDIT | `nodes.py` → `edit_complaint()` + `merge.py` | Model returns `EditProposal {changes:[{field,value}], clear:[...]}`. `EditProposal` validates each value through the real target field; `merge.patch_from` builds `{section:{field:value}}`; `apply_patch` merges — unlisted fields are untouched; nulls never erase; clears are explicit. |
| 7 | Risk | `nodes.py` → `assess_risk()` | `RiskAssessment {severity_class I/II/III, reason, actions, follow-up, confidence}` + fixed disclaimer. |
| 8 | Persist | `api/complaints.py` → `_persist()` + `crud.py` | LOG/EXTRACT → `crud.create` (new row). EDIT → `crud.update` (merge into JSONB sections). This is the only place AI results are written. |
| 9 | Response | `schemas.py` → `CopilotResponse` | `{intent, message, complaint_id, complaint, patch?, risk_assessment?}` — `complaint` is always the full persisted record built from the row (`Complaint.model_validate(record)`). |
| 10 | State | `frontend/src/store.js` → `settled` reducer | Replaces `complaint` and `patch` from the response and appends the reply (with its intent) and, if present, a risk card to the chat. `ComplaintForm.jsx` renders straight from `complaint`; fields present in `patch` get the "updated" highlight. |

Where the boundaries are: the model only ever produces JSON (5); Pydantic decides what is valid (5, 6b);
`merge.py` decides what may change (6b); `crud.py` decides what is stored (8). Failures are plain
exceptions mapped to HTTP codes in `main.py` (`STATUS`), so no endpoint has a try/except.

## Technology stack

| Layer | Choice |
|---|---|
| Frontend | React 19, Redux Toolkit 2, Tailwind CSS 4, Inter font (Vite 8) |
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2, Pydantic 2 |
| AI | LangGraph 1.2, LangChain Groq 1.1, Groq (`gemma2-9b-it` configured → `openai/gpt-oss-20b` fallback) |
| Documents | pypdf (text-based PDFs; OCR out of scope) |
| Database | PostgreSQL 16 (JSONB), docker-compose for local dev |

## Project structure

```
backend/
  app/
    main.py            FastAPI app, CORS, exception → HTTP mapping, /api/health
    config.py          environment settings
    db.py              engine / session
    models.py          ComplaintRecord (JSONB per section)
    schemas.py         canonical complaint schema + API models
    merge.py           EDIT patch semantics
    crud.py            create / get / update
    documents.py       PDF validation + text extraction
    api/complaints.py  /api/chat, /api/upload, /api/complaints
    ai/graph.py        LangGraph wiring
    ai/nodes.py        route, log, edit, extract, assess_risk
    ai/prompts.py      prompts + schema-derived field guide
    ai/llm.py          Groq client, structured output, retry, fallback
  tests/               unit + API contract tests (SQLite, stubbed graph)
  scripts/e2e.py       real Groq + PostgreSQL end-to-end check
  requirements.txt · .env.example
frontend/
  src/
    main.jsx           React root + Redux Provider
    App.jsx            header (backend/model status), 60/40 layout
    store.js           Redux Toolkit slice: complaint, patch, messages, busy; sendMessage / uploadDocument thunks
    api.js             the three fetch calls (/api/chat, /api/upload, /api/health)
    components/
      ComplaintForm.jsx  read-only QMS form driven by the complaint record; highlights patched fields
      RiskAssessment.jsx section 5: severity badge, reasoning, actions, follow-up, confidence
      Copilot.jsx        chat history, intent chips, risk cards, input, PDF button + drag-and-drop
  vite.config.js       React + Tailwind plugins; proxies /api to the backend in dev
samples/               fictional demo complaint PDFs + generator
docker-compose.yml     PostgreSQL 16
```

## Setup

### 1. Database

```bash
docker compose up -d
```

Starts PostgreSQL 16 on `localhost:5432` (user/password/db: `aivoa`). Any other PostgreSQL works —
just set `DATABASE_URL`. Tables are created automatically on backend startup (no migrations needed
for the MVP).

### 2. Environment variables

Copy `backend/.env.example` to `backend/.env` and fill in your key. Never commit `.env`.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy URL, e.g. `postgresql+psycopg://aivoa:aivoa@localhost:5432/aivoa` |
| `GROQ_API_KEY` | Groq API key |
| `GROQ_MODEL` | `gemma2-9b-it` (assignment default) |
| `GROQ_FALLBACK_MODEL` | `openai/gpt-oss-20b` — current Groq model used if `GROQ_MODEL` is decommissioned (`openai/gpt-oss-120b` for the larger option) |
| `GROQ_REASONING_EFFORT` | `low` (default) / `medium` / `high` — gpt-oss only; `low` keeps free-tier token budgets in check |
| `FRONTEND_URL` | CORS origin of the React dev server (`http://localhost:5173`) |

### 3. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows   |   source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Interactive API docs: http://localhost:8000/docs

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The Vite dev server proxies `/api` to `http://localhost:8000`, so no
frontend configuration is needed; for a production build set `VITE_API_URL` to the backend origin.

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/chat` | Natural-language message → LOG or EDIT |
| `POST` | `/api/upload` | `multipart/form-data` PDF → EXTRACT |
| `GET` | `/api/complaints` | Recent complaints |
| `GET` | `/api/complaints/{id}` | One complaint |
| `GET` | `/api/health` | DB status, Groq configuration, active model |

### LOG

```bash
curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d '{
  "message": "Customer Rahul Sharma reported that Paracetamol 500 mg tablets from batch PCM24031 were chipped and broken inside the blister pack. The complaint was received today. No hospitalization occurred and the sample is available.",
  "complaint_id": null
}'
```

```json
{
  "intent": "LOG",
  "message": "Logged a new complaint for Paracetamol 500 mg tablets · batch PCM24031 · reported by Rahul Sharma. Captured 9 of 31 fields. Still missing: email, phone, organization, country, contact channel… — tell me if you have them.",
  "complaint_id": 1,
  "complaint": { "id": 1, "reference": "CC-2026-0001", "complainant": {...}, "product": {...}, "complaint": {...}, "patient": {...}, "risk_assessment": {...} },
  "patch": null,
  "risk_assessment": { "severity_class": "III", "severity_reason": "...", "immediate_actions": ["..."], "recommended_follow_up": ["..."], "confidence": 0.8, "disclaimer": "AI-assisted preliminary triage ..." }
}
```

### EDIT

```bash
curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d '{
  "message": "Actually change the batch number to PCM24099.",
  "complaint_id": 1
}'
```

```json
{
  "intent": "EDIT",
  "message": "Updated batch number: PCM24031 → PCM24099.",
  "complaint_id": 1,
  "patch": { "product": { "batch_number": "PCM24099" } },
  "complaint": { ...full record with only batch_number changed... },
  "risk_assessment": null
}
```

`risk_assessment` is non-null on an EDIT only when the edit changed complaint/patient facts and a
new assessment was generated; the current assessment is always available in `complaint.risk_assessment`.

### EXTRACT

```bash
curl -X POST http://localhost:8000/api/upload -F "file=@samples/complaint_02_adverse_event.pdf"
```

```json
{
  "intent": "EXTRACT",
  "message": "Extracted a complaint from the document for Amoxiclav-DS Tablets · batch AMC25017 · reported by Dr. Priya Menon. Captured 27 of 31 fields. ...",
  "complaint_id": 2,
  "complaint": { ... },
  "risk_assessment": { "severity_class": "I", ... }
}
```

### Errors

| Situation | Status |
|---|---|
| EDIT request with no `complaint_id` | `400` |
| Empty / corrupt / image-only / non-PDF upload | `400` (`415` for a non-`.pdf` filename) |
| Unknown `complaint_id` | `404` |
| Message contained no complaint information, or edit mapped to no field | `422` |
| Model returned malformed data twice / Groq error | `502` |
| `GROQ_API_KEY` missing / database down | `503` |

Responses always carry a human-readable `detail`; stack traces are never returned.

## Data model

One canonical schema (`schemas.py`) is used everywhere:

- `ComplaintData` — the four AI-populated sections: `complainant`, `product`, `complaint`,
  `patient`. Every field is optional and `null` when unknown. This is the LOG/EXTRACT
  structured-output type.
- `ComplaintPatch` / `EditProposal` — the same sections, used as the EDIT structured-output type
  (unset fields are excluded when dumping, so only proposed changes survive).
- `RiskAssessment` — `severity_class` (`I`/`II`/`III`), `severity_reason`, `immediate_actions`,
  `recommended_follow_up`, `confidence` (0–1), plus a fixed `disclaimer`.
- `Complaint` — `ComplaintData` + `id`, `reference` (`CC-YYYY-NNNN`), `source`,
  `risk_assessment`, timestamps. This is the API response type and is built directly from the
  SQLAlchemy row.
- `ComplaintRecord` (SQLAlchemy) stores each section as a JSONB column named exactly like the
  schema section, so rows round-trip through `Complaint.model_validate(record)` with no mapping code.

## Risk assessment behaviour

Class I = potential for serious health consequences; Class II = temporary/reversible effects or
significant quality defect; Class III = unlikely to cause harm (cosmetic/minor). The prompt asks
the model to consider defect type, patient involvement, adverse events, hospitalisation/death,
counterfeit suspicion, sterile products and sample availability, to lower confidence when facts
are missing, and to cite no regulations. Every assessment carries a fixed disclaimer and the UI
labels it "AI-Assisted Risk Assessment".

## Tests

```bash
cd backend
.venv\Scripts\python -m pytest -q          # 67 unit/API tests, no network or Postgres needed
.venv\Scripts\python scripts/probe_models.py   # which models this key can use + one JSON-mode call
.venv\Scripts\python scripts/e2e.py            # real Groq + PostgreSQL run against http://localhost:8000
```

`tests/` cover schema normalisation/rejection, EDIT patch safety (single/nested/multiple fields,
nulls never erase data, explicit clear only), PDF validation and the HTTP contract (SQLite with a
stubbed graph). `scripts/e2e.py` runs LOG → EDIT → nested EDIT → EXTRACT plus the error paths
against the live stack and asserts that unrelated fields are untouched by edits.

## Demo flow

1. Open the app — empty form, co-pilot ready ("Try a sample complaint" fills the message below).
2. Paste the Paracetamol complaint above → form fills, risk assessment appears (Class III).
3. "Actually change the batch number to PCM24099." → only that field changes; reply names the change.
4. "The complainant's email is rahul@example.com" → nested field updated, everything else intact.
5. Upload `samples/complaint_02_adverse_event.pdf` → new complaint extracted from the document,
   hospitalisation captured, Class I/II assessment.
6. `samples/complaint_03_api_foreign_particles.pdf` shows a B2B API (active ingredient) complaint.

## Sample data

`samples/` contains three fictional PDFs (all names, companies and identifiers are invented) and
`generate_samples.py` to regenerate them:

- `complaint_01_blister_defect.pdf` — pharmacy email, chipped tablets, no patient harm
- `complaint_02_adverse_event.pdf` — hospital complaint form, discoloured tablets, patient hospitalised
- `complaint_03_api_foreign_particles.pdf` — formulation customer reports particles in an API batch

## Known limitations

- Text-based PDFs only; scanned documents need OCR, which is out of scope.
- One complaint is edited at a time; there is no authentication, audit trail or workflow states.
- `gemma2-9b-it` (and the llama-3.x alternatives) have been shut down by Groq; the fallback model is used whenever Groq rejects the configured one, and `/api/health` says so.
- Small models occasionally miss a field; the co-pilot reports missing fields so they can be added by chat.
- Clearing a field requires an explicit request ("remove the phone number"); model-emitted nulls are ignored by design.
- The AI risk assessment (severity class etc.) is not editable through chat; it is regenerated when complaint or patient facts change.
- The risk assessment is advisory and must be reviewed by the quality unit.
- Free-tier Groq keys are limited to ~8k tokens/minute on `gpt-oss-20b`; a LOG costs ~3.5k tokens
  (router + extraction + risk). Bursts return 429s, which the Groq SDK retries with back-off
  (`max_retries=5`), so rapid-fire requests get slower rather than failing.
