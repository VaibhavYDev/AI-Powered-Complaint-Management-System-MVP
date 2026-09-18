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
