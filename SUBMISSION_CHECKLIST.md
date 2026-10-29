# Submission checklist

Assignment: AIVOA — Round 1 AI Product Engineer (Interns) — AI-Powered Customer Complaint Management System

## Repository

- [x] GitHub repository created — https://github.com/VaibhavYDev/AI-Powered-Complaint-Management-System-MVP
- [x] Repository pushed successfully (`git push -u origin main`)
- [ ] Live demo deployed to Google Cloud Run (Neon PostgreSQL) and the README Live Demo URL verified from a fresh browser
- [ ] README complete (setup, architecture, API, LangGraph flows, demo, limitations)
- [ ] `.gitignore` verified (`git status --ignored` shows `.env`, `.venv/`, `node_modules/` ignored)
- [ ] `.env` excluded — only `backend/.env.example` is committed; no keys anywhere in history (`git log -p | grep -i gsk_` is empty)
- [ ] Demo PDFs included (`samples/complaint_01..03*.pdf`)
- [ ] Resume NOT committed to the repository

## Verification

- [ ] `docker compose up -d` → PostgreSQL reachable
- [ ] `cd backend && .venv\Scripts\python -m pytest -q` → all tests pass
- [ ] Backend running, `GET /api/health` shows `database: ok`, `groq_configured: true`, and the active model
- [ ] `scripts/e2e.py` passes: LOG → EDIT → nested EDIT → EXTRACT + error paths
- [ ] Frontend running, full flow demonstrated in the browser (LOG, EDIT, EXTRACT, risk assessment)
- [ ] Final application tested end-to-end on a clean clone

## Videos

- [ ] Product demo recorded (5–10 min): empty form → chat LOG → form fills → risk assessment → EDIT changes one field only → PDF EXTRACT → final state
- [ ] Code explanation recorded: frontend → API → FastAPI → LangGraph router → LOG/EDIT/EXTRACT → Groq → Pydantic → DB → response → Redux → form

## Submission form

- [ ] Resume updated
- [ ] GitHub repository URL
- [ ] Product demonstration video link
- [ ] Code explanation video link
- [ ] Submission form completed
