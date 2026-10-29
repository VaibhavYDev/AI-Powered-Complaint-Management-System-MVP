# Deployment: Google Cloud Run + Neon PostgreSQL

The hosted demo is one Cloud Run service built from the repository `Dockerfile` (React build served
by FastAPI, so the UI and `/api/*` share one origin) and a free Neon PostgreSQL database.
Cloud Run scales to zero when idle and starts a container automatically on the next request.

```
Browser ──► Cloud Run (FastAPI + React build + LangGraph) ──► Groq
                          │
                          └──► Neon PostgreSQL (JSONB, SSL)
```

## 1. Neon (once)

1. Create a free project at https://neon.tech (Postgres 16).
2. Copy the connection string; it looks like
   `postgresql://user:password@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require`.
   The app accepts `postgres://`, `postgresql://` or `postgresql+psycopg://` and keeps the
   `sslmode=require` query parameter. Tables are created automatically on first start.

## 2. Google Cloud (once)

Cloud Run has a monthly free usage allowance (requests, CPU-seconds, memory) that comfortably covers
a demo, but the project must have **billing enabled** (a linked billing account) before Cloud Run
and Cloud Build can be used at all. The region is `us-east1` to sit next to the Neon database
(AWS us-east-2) and to stay in Cloud Run's lowest-price tier.

```bash
gcloud auth login
gcloud config set project <PROJECT_ID>
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

## 3. Deploy from the repository

Build in Cloud Build and deploy in one command (uses the Dockerfile; no local Docker needed):

```bash
gcloud run deploy aivoa-complaint-copilot \
  --source . \
  --region us-east1 \
  --allow-unauthenticated \
  --min-instances 0 --max-instances 3 \
  --memory 512Mi --cpu 1 --concurrency 20 --timeout 120 \
  --set-env-vars GROQ_MODEL=gemma2-9b-it,GROQ_FALLBACK_MODEL=openai/gpt-oss-20b,GROQ_REASONING_EFFORT=low \
  --set-env-vars GROQ_API_KEY=<your Groq key> \
  --set-env-vars DATABASE_URL=<Neon connection string>
```

After the first deploy, set `FRONTEND_URL` to the URL Cloud Run printed (kept for CORS parity;
the UI and API are same-origin so no other frontend configuration exists):

```bash
gcloud run services update aivoa-complaint-copilot --region us-east1 \
  --update-env-vars FRONTEND_URL=https://<service-url>
```

Redeploys keep the existing environment variables; re-run the deploy command without
`--set-env-vars` to ship a new commit, or connect the repository to a Cloud Build trigger
that runs `cloudbuild.yaml` on every push to `main`.

## Cost safety

- **Request-based billing**: CPU is allocated only while a request is being handled (the default;
  `--no-cpu-throttling` is deliberately not used). No background processes run in the container.
- **`--min-instances 0`**: nothing runs, and nothing is billed, while the service is idle. The first
  request after idling starts a container (a few seconds).
- **`--max-instances 3`**: caps concurrent containers so a traffic spike cannot create an
  unexpected bill.
- Neon free tier: compute suspends after inactivity and resumes automatically on the next
  connection; `pool_pre_ping` in `db.py` transparently reconnects.
- Recommended: create a Cloud Billing **budget alert** (e.g. $5/month) in the Google Cloud console
  → Billing → Budgets & alerts.
- No scheduled pings or keep-warm traffic are configured; the service is allowed to scale to zero.

## Verification

```bash
curl https://<service-url>/api/health
# {"database":"ok","groq_configured":true,"configured_model":"gemma2-9b-it",
#  "active_model":"openai/gpt-oss-20b","fallback_reason":"..."}
```

Then open the URL in a browser and run the demo flow (LOG → EDIT → PDF EXTRACT); records are
readable via `GET /api/complaints/{id}` after a redeploy because they live in Neon, not in the
container.
