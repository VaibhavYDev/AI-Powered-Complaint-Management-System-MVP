# Submission checklist

Assignment: AIVOA — Round 1 AI Product Engineer (Interns) — AI-Powered Customer Complaint
Management System.

Items are ticked only where they were actually verified, and the date of that check is given
where it matters.

## Repository

- [x] Repository created and pushed — <https://github.com/VaibhavYDev/AI-Powered-Complaint-Management-System-MVP>
- [x] README covers setup, architecture, the LangGraph workflow, structured output, evidence and
      review, the case study with measured results, security, tests, API and limitations
- [x] Every Markdown link and anchor in the repository resolves (checked mechanically)
- [x] No secret in the repository or anywhere in its history — `git log -p --all` contains no
      Groq-key-shaped string; only `backend/.env.example` is committed
- [x] `.env`, `.venv/`, `node_modules/`, `frontend/dist/`, caches and test artefacts are ignored,
      and none of them are tracked (109 tracked files, all intentional)
- [x] Demo PDFs committed (`samples/complaint_01..03*.pdf`) with the generator that made them
- [x] No resume, database file or personal document committed
- [x] **Live demo** — <https://ai-powered-complaint-management-system-ky8u.onrender.com> answers
      `/api/health` with `status: ready`, `database: ok`, `schema: ready`, and `/api/ready` 200.
      See [DEPLOYMENT.md](DEPLOYMENT.md).

## Verification

- [x] `docker compose up -d` → PostgreSQL reachable
- [x] Backend suite: **280 tests pass** against a real PostgreSQL 16 container (277 pass on
      SQLite alone; 3 migration tests need PostgreSQL)
- [x] Frontend unit suite: **17 tests pass**
- [x] Browser suite: **3 end-to-end tests pass**, against the stubbed provider *and* against the
      live Groq API
- [x] `GET /api/health` reports `database: ok`, `groq_configured: true`, the configured model and
      the model actually serving requests
- [x] `scripts/e2e.py` passes all 40 checks against the live Groq API: LOG → EDIT → nested EDIT →
      multi-field EDIT → explicit clear → risk-relevant EDIT → EXTRACT, plus the error paths
- [x] The whole flow demonstrated in a real browser, including human review, approval, export and
      an edit revoking approval
- [x] The CI smoke job replayed locally against a real container, step for step
- [x] The CI e2e job replayed on Linux from a clean `git archive` checkout
- [x] CI runs four jobs on every pull request with **no secrets**: `backend`, `frontend`, `e2e`,
      `smoke`

## Beyond the assignment

- [x] Evidence and provenance for every extracted value, with a human review gate and an audit
      trail ([README](README.md#evidence-and-what-a-lexical-match-does-not-prove))
- [x] Care Documentation Reliability Lab — a second, independent case study with deterministic
      checks for attribution, negation, contradiction, care-plan gaps and prompt injection
- [x] A 43-case benchmark with hand-authored ground truth, run three times against the real
      model, with denominators and failure analysis ([EVALUATION.md](EVALUATION.md))

## Still to do (not code)

- [ ] Product demonstration video (5–10 min) — script in [DEMO_SCRIPT.md](DEMO_SCRIPT.md)
- [ ] Code explanation video — script in [CODE_WALKTHROUGH.md](CODE_WALKTHROUGH.md)
- [ ] Submission form: repository URL, both video links, updated resume
