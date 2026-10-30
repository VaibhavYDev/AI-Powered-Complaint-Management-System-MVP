# Demo scripts

Two versions: a 2-3 minute technical walk-through of the whole release, and the longer product
demo below it.

---

## 2-3 minutes, the whole release

Open the [live demo](https://ai-powered-complaint-management-system-ky8u.onrender.com) (free
instance: the first request takes a minute to wake) or run it locally. Leave a few seconds
between AI actions - a free Groq key allows roughly 8k tokens a minute.

**0:00 - What it is (20 s).** Pharmaceutical complaints arrive as emails, phone notes and PDFs,
and QA staff re-key them into a QMS before triage can start. Left is the structured record,
right is the co-pilot. Nobody types into the form.

**0:20 - One sentence becomes a record (40 s).** Click *Try a sample complaint*, then *Send*.
One message: LangGraph routes it, a strict JSON Schema derived from the Pydantic model shapes
the extraction, Pydantic validates it, and it lands in PostgreSQL. The form fills, the reference
appears, and a risk assessment arrives in the same graph run. Point at the fields the customer
never mentioned: still empty. The model is not allowed to invent them.

**1:00 - Provenance (20 s).** Every field carries a label: `quoted`, `matched`, `inferred`,
`not in source`. A match proves the characters are in the source, not that the reading is right
- so it is shown as a pointer for the reviewer, not a guarantee.

**1:20 - A correction that cannot destroy anything (25 s).** Type *"Actually change the batch
number to PCM24099."* Only Batch number turns amber; the complainant, the product and the risk
assessment are untouched. The model returns a sparse patch, the server merges it, and a null it
emits never erases a field - clearing one takes an explicit request.

**1:45 - The human gate (25 s).** Section 6: the record is `needs review`. The one value the
source does not support is named, and *Approve* stays disabled until a reviewer accepts it.
Approve, export, then edit again - the record goes back to review at a new revision, and the
audit trail shows every step.

**2:10 - Where it gets interesting (40 s).** Open *Care Lab*. A caregiver note, with a sentence
addressed to the reader rather than describing a resident. The model obeys it and records a
medication nobody gave. The injected sentence is physically in the note, so the evidence check
rates the fabrication `quoted` - a lexical match cannot tell care from an instruction. A
deterministic check locates instruction spans instead and blocks approval until a human
acknowledges it. Across the 43-case benchmark the model obeys two of four injections; the
application contains four of four.

**2:50 - Close (10 s).** 279 backend tests, 17 frontend, 3 browser end-to-end against a real
Chromium, and a 43-case benchmark whose published numbers are re-derived from the stored model
answers on every test run.

---

# Product demo script (5–7 minutes)

Before recording: `docker compose up -d`, backend on :8000 (`/api/health` shows `active_model`), frontend on :5173,
`samples/complaint_02_adverse_event.pdf` open in a folder. Leave ~15 s between AI actions — the free Groq tier
allows ~8k tokens/minute and a burst just makes the next answer wait.

## 1. The problem (45 s)

- In pharmaceutical manufacturing (API and finished dosage forms) every customer complaint has to be recorded,
  classified for patient risk, investigated and — if needed — feed into CAPA or a recall.
- Complaints arrive as emails, phone notes and PDF forms. QA staff re-key them into a QMS form before triage
  even starts. This co-pilot removes the re-keying and gives a first-pass risk triage immediately.
- Point at the screen: **left** is the structured complaint record, **right** is the AIVOA Co-pilot.
  Nobody types into the form — the AI populates and updates it.

## 2. Empty form (20 s)

- Show the five sections (Complainant, Product, Complaint/Defect, Patient, AI-Assisted Risk Assessment),
  every field "Awaiting AI extraction", the "Pending triage" badge, and the co-pilot's welcome message.
- Mention the header pill: the backend reports the model actually in use.

## 3. LOG — natural language (60 s)

- Click **Try a sample complaint** (or paste your own), then **Send**.
- While it runs: one message → LangGraph routes it → structured extraction → risk assessment → PostgreSQL.
- When it returns, walk the result:
  - the reply has a **LOG** chip, names product/batch/complainant and says how many fields were captured
    and which are still missing;
  - the form fills: name, product, strength, batch, defect category, sample available, received date
    (resolved from "today"), hospitalization = No;
  - fields the customer never mentioned stay empty — the AI does not invent data;
  - the header now shows the record reference (`CC-2026-…`), "via chat" and "AI triaged".

## 4. Risk assessment (45 s)

- Scroll to **section 5**: severity class badge, reasoning, immediate actions, recommended follow-up,
  confidence bar, and the disclaimer.
- The chat shows a compact card of the same assessment, visibly separate from the normal reply.
- Say clearly: this is AI-assisted preliminary triage for the quality unit, not a regulatory decision.

## 5. EDIT — conversational correction (60 s)

- Type: **"Actually change the batch number to PCM24099."** → Enter.
- Show the **EDIT** chip and the reply "Updated batch number: PCM24031 → PCM24099."
- Show the amber **updated** highlight on Batch number only; everything else, including the risk
  assessment, is untouched. Explain: the model returns only the changed field as a patch; the server merges it.
- Optional second edit (nested field): **"The complainant's email is rahul@example.com"** — only Email changes.
- Optional risk-relevant edit: **"The customer was hospitalised overnight"** — patient fields change *and*
  a new risk assessment is generated (severity escalates).

## 6. EXTRACT — PDF upload (60 s)

- Click **Upload PDF** (or drag the file onto the co-pilot) and choose `complaint_02_adverse_event.pdf`.
- Show the upload state ("Reading the document…"), then the **EXTRACT** chip.
- A new record appears (`via document`), all sections populated including patient data (62-year-old,
  hospitalised) and lot/manufacturing/expiry dates; risk assessment is Class II.
- If time allows, `complaint_03_api_foreign_particles.pdf` shows an API (active ingredient) complaint.

## 7. Close (45 s)

- Click **New complaint** to show the state resets.
- Architecture in one breath: React + Redux → FastAPI → LangGraph (router → LOG / EDIT / EXTRACT →
  risk assessment) → Groq structured output → Pydantic validation → PostgreSQL → back to the form.
- Product value: intake in seconds instead of minutes, consistent structured records, missing data made
  explicit, and a triage suggestion the reviewer can act on — with the human still in charge.
