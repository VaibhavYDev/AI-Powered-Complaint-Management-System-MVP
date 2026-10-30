# Code walkthrough script (5–7 minutes)

Follow one request through the code, in execution order. Have these files open in tabs, in this order:
`frontend/src/main.jsx`, `store.js`, `api.js`, `backend/app/api/complaints.py`, `ai/graph.py`, `ai/nodes.py`,
`ai/llm.py`, `schemas.py`, `merge.py`, `crud.py`. The README's "Code walkthrough guide" has the same steps
with a diagram if you want it on screen.

## 1. React entry point (30 s) — `frontend/src/main.jsx`, `App.jsx`

- `main.jsx`: `createRoot` → Redux `<Provider store={store}>` → `<App />`. Nothing else.
- `App.jsx`: header (fetches `/api/health` once to show the active model), then a 60/40 grid:
  `<ComplaintForm />` on the left, `<Copilot />` on the right. "New complaint" dispatches `reset`.

## 2. Redux state (45 s) — `frontend/src/store.js`

- One slice, `copilot`, four fields: `complaint` (the persisted record exactly as the API returns it — the
  single source of truth for the form), `patch` (fields changed by the last EDIT, for the highlight),
  `messages` (chat history), `busy` (`"sending" | "uploading" | null`).
- Two thunks: `sendMessage(text)` calls `api.chat(text, complaint?.id)` — passing the id is what makes an EDIT
  possible; `uploadDocument(file)` calls `api.upload(file)`.
- `settled` (shared fulfilled reducer): replaces `complaint` and `patch`, appends the reply with its `intent`,
  and appends a risk card when the response carries a new `risk_assessment`. `failed` appends an error bubble
  with the backend's `detail`. No derived copies of server data anywhere.

## 3. API layer (20 s) — `frontend/src/api.js`

- One `request()` helper: `fetch`, parse JSON, throw `Error(detail)` on non-2xx. `chat`, `upload`
  (`FormData`), `health`. Vite proxies `/api` to the backend in dev.

## 4. FastAPI endpoint (45 s) — `backend/app/api/complaints.py`, `main.py`

- `chat()`: `ChatRequest` validated by FastAPI; if `complaint_id` is set, `_load` fetches the row (404 if not);
  `run_copilot(message, source="chat", existing=crud.sections(record))`; `_persist`.
- `upload()`: filename check (415) → `documents.extract_pdf_text` (pypdf; empty/corrupt/image-only → 400)
  → `run_copilot(text, source="document")` → `_persist`.
- `main.py`: `STATUS` maps expected exceptions to HTTP codes (`NoComplaintToEdit` 400, `NothingExtracted` 422,
  `AIOutputError`/`AIProviderError` 502, `AIConfigError` 503…) — so endpoints have no try/except.
  `lifespan` creates tables and calls `resolve_model()`.

## 5. LangGraph router (45 s) — `backend/app/ai/graph.py`

- `build_graph()`: `StateGraph(GraphState)` with nodes `route`, `log`, `edit`, `extract`, `assess_risk`.
- `START → route`; `add_conditional_edges("route", _dispatch, …)` where `_dispatch` just returns the validated
  intent in lower case; `log → assess_risk`, `extract → assess_risk`; `edit → assess_risk` only if
  `_after_edit` sees the patch touching the `complaint` or `patient` sections, else `END`.
- `run_copilot()` is `graph.invoke({text, source, existing})`. There is no other routing code.

## 6. LOG / EDIT / EXTRACT nodes (60 s) — `backend/app/ai/nodes.py`

- `route()`: one call → `RouterDecision {intent}`; documents are prefixed `[Uploaded document]`.
- `log_complaint()` / `extract_complaint()`: one call → `ComplaintData`; `_require_content` raises
  `NothingExtracted` if nothing was found; `_summarize` builds the reply deterministically (what was captured,
  what is still missing).
- `edit_complaint()`: raises `NoComplaintToEdit` if nothing is loaded; one call → `EditProposal`;
  `merge.patch_from` → patch; `apply_patch` → merged view for the risk node; `describe_changes` → reply
  ("Updated batch number: PCM24031 → PCM24099."); unknown fields are named in the reply.
- `assess_risk()`: one call → `RiskAssessment` from the (merged) complaint JSON.
- Nodes never touch the database.

## 7. Groq structured output (60 s) — `backend/app/ai/llm.py`

- `resolve_model()`: one `GET /models` at startup. `gemma2-9b-it` (the assignment model) is no longer served
  by Groq, so the app switches to `openai/gpt-oss-20b` and `/api/health` reports `configured_model`,
  `active_model`, `fallback_reason`.
- `_runnable()`: for gpt-oss models `with_structured_output(strict_json_schema(Model), method="json_schema",
  strict=True)` — Groq Structured Outputs; for any other model `method="json_mode"`.
- `strict_json_schema()`: derives the schema from `Model.model_json_schema()` and adapts it to Groq's strict
  subset (all properties required, `additionalProperties: false`, nullable unions as type lists, enums inlined,
  unsupported keywords removed). No hand-written schema.
- `structured()` → `_call_with_one_retry` → `_call`: invoke, `Model.model_validate(raw)`; on invalid JSON or a
  Pydantic error the rejected output and the error go back to the model once; second failure → `AIOutputError`.

## 8. Pydantic validation (45 s) — `backend/app/schemas.py`

- `ComplaintData` = four sections (`Complainant`, `Product`, `ComplaintDetails`, `Patient`); every field
  optional, `null` when unknown. Small normalisers ("Physical Defect" → `physical_defect`, "45 years" → 45,
  "Not provided" → null) but ill-typed values are rejected ("maybe" for a boolean, "forty-two" for an age).
- `EditProposal` = `changes: [{field, value}]` + `clear: [field]`; its validator runs every value through the
  real target field (`ComplaintData.model_validate(self.patch())`), so a bad value triggers the retry.
- `RiskAssessment`: `severity_class ∈ {I, II, III}`, non-empty reason/actions/follow-up, `confidence` 0–1,
  fixed disclaimer. `Complaint` = `ComplaintData` + id, reference, source, risk, timestamps = API response.

## 9. PostgreSQL persistence (30 s) — `backend/app/models.py`, `crud.py`, `merge.py`

- `ComplaintRecord`: one JSONB column per section, named exactly like the schema, so
  `Complaint.model_validate(record)` needs no mapping.
- `crud.create` for LOG/EXTRACT; `crud.update` for EDIT: `apply_patch` = `{**existing[section], **patch[section]}`
  per section, then reassign so SQLAlchemy sees the change. Nulls inside `changes` never reach the patch; a
  field becomes null only via an explicit `clear`.

## 10. Response → Redux → UI (30 s) — `schemas.py` `CopilotResponse`, `store.js`, `ComplaintForm.jsx`

- `_persist` returns `CopilotResponse {intent, message, complaint_id, complaint, patch?, risk_assessment?}`;
  `complaint` is always the full persisted record.
- `settled` stores it; `ComplaintForm` renders straight from `complaint` via a section/field table, shows
  "Awaiting AI extraction" for nulls, and highlights fields present in `patch`; `RiskAssessment` renders
  `complaint.risk_assessment`; `Copilot` renders `messages`.
- Close: the model only ever produces JSON; Pydantic decides what is valid; `merge.py` decides what may change;
  `crud.py` decides what is stored; the UI only reflects what the server persisted.

## 11. What sits on top of that pipeline (60 s) — `evidence.py`, `crud.py`, `care/`

The ten steps above are the assignment's pipeline. Three layers were built on top of it, and
each is worth a sentence if there is time:

- `evidence.py` searches the source text for every value the model produced and labels it
  `verbatim`, `normalized`, `derived` or `unsupported`, with the excerpt and page. A match
  proves the characters are in the source, not that the reading is right — which is exactly the
  limitation the adversarial benchmark cases exploit.
- Review (`crud.review`, `components/ReviewPanel.jsx`): a record is a suggestion
  until a person approves it, approval is blocked until unsupported values are acknowledged, and
  the decision is one conditional `UPDATE` guarded by owner, revision and status, so two
  reviewers racing cannot both win. Editing an approved record sends it back for review.
- `care/` is a second case study on caregiver notes: one model call, then deterministic checks
  for attribution, negation, contradiction, care-plan gaps and instructions injected into the
  note. `EVALUATION.md` has the measured results, including the model obeying two of four
  injections while the application contained four of four.
