# FairSwarm

FairSwarm is a swarm-intelligence platform for AI bias detection. It runs multiple specialized agents, aggregates their findings, and produces actionable fairness reports for uploaded datasets.

## Why FairSwarm

- Multi-agent consensus instead of single-model judgment.
- Bias metrics + narrative recommendations in one workflow.
- Security-focused architecture for hackathon demos and production pilots.
- One-command local setup, plus CI/CD-ready deployment configs.

## Core Capabilities

- Secure authentication with access + refresh token rotation.
- Dataset ingestion with file signature validation, CSV injection detection, and Excel macro/script checks.
- Fairness scoring and intersectional analysis.
- Swarm consensus engine for cross-model bias reasoning.
- PDF/JSON report generation.
- Demo seed pipeline for fast judge walkthroughs.

## Tech Stack

- Frontend: Next.js 14 (App Router), TypeScript, Tailwind CSS, React Query.
- Backend: FastAPI, Python 3.11, Pydantic, Supabase SDK.
- Data/Storage: Supabase Postgres + Supabase Storage.
- Fairness: AIF360 + Fairlearn.
- CI/CD: GitHub Actions, Vercel (frontend), Railway (backend).

## Security Hardening Implemented

- HttpOnly cookie auth flow via Next.js proxy route.
- CSRF double-submit validation for state-changing requests.
- Request-size limits (JSON and multipart) and content-type validation.
- SQL-like payload detection in API middleware.
- Per-user rate limiting for uploads and analysis starts.
- Token blocklist + refresh token persistence and revocation.
- Runtime key-rotation support (Supabase `runtime_config` table with env fallback).
- Sensitive-data masking for logs.
- Strict security headers and CSP.

## Project Structure

```
FairSwarm/
   backend/
      app/
      tests/
      scripts/
   frontend/
      app/
      components/
   .github/workflows/
   docker-compose.yml
```

## Quick Start (Under 5 Minutes)

### 1. Clone

```bash
git clone https://github.com/Ankitkr-ak007/FairSwarm.git
cd FairSwarm
```

### 2. Configure Environment

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

Set real keys in `backend/.env` for Supabase + AI providers.

### 3. Start With Docker Compose

```bash
docker compose up --build
```

App endpoints:

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs
- Backend health: http://localhost:8000/health

## Local Development Without Docker

### Backend

```bash
cd backend
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

## Database Setup (Supabase)

Run schema migration from:

- `backend/supabase_schema.sql`

This includes user/auth tables plus:

- `refresh_tokens`
- `rate_limit_counters`
- `runtime_config`

## Demo Data Seeder

Use the included seed script to create a demo account, two synthetic datasets, and precomputed analyses.

```bash
cd backend
python -m scripts.seed_demo_data
```

Seeded login:

- Email: demo@fairswarm.ai
- Password: Demo@123456

## Testing and Quality

### Backend

```bash
cd backend
pytest
ruff check app tests
mypy app/services/dataset_processor.py app/services/fairness_metrics.py
```

Current backend test status:

- 27 tests passing.
- Coverage gate: 86% on core analysis modules (`dataset_processor`, `fairness_metrics`).

### Frontend

```bash
cd frontend
npx tsc --noEmit
npm run build
npm run lint
```

## CI/CD

Workflows in `.github/workflows/`:

- `ci.yml`: backend tests/coverage + lint/type checks + frontend build/lint.
- `deploy.yml`: deploy frontend to Vercel, backend to Railway, run smoke tests.

## Deployment Configuration

### Frontend (Vercel)

- Config file: `frontend/vercel.json`
- Includes security headers and API rewrite support.

Required secrets for deploy workflow:

- `VERCEL_TOKEN`
- `VERCEL_ORG_ID`
- `VERCEL_PROJECT_ID`

### Backend (Railway)

- Config file: `backend/railway.json`
- Dockerized deployment with healthcheck on `/health`.

Required secrets for deploy workflow:

- `RAILWAY_TOKEN`
- `RAILWAY_PROJECT_ID`
- `RAILWAY_SERVICE_ID`

Optional smoke-test/deploy notification secrets:

- `PROD_FRONTEND_URL`
- `PROD_BACKEND_URL`
- `DEPLOY_WEBHOOK_URL`

### Containerization

- Backend Dockerfile: `backend/Dockerfile` (multi-stage, non-root runtime user, healthcheck).
- Frontend Dockerfile: `frontend/Dockerfile`.
- Combined local stack: `docker-compose.yml`.

## API Surface (High Level)

- Auth: `/api/v1/auth/*`
- Datasets: `/api/v1/datasets/*`
- Analysis: `/api/v1/analysis/*`
- Reports: `/api/v1/reports/*`
- AI Swarm: `/api/v1/ai/*`
- Realtime updates: `/ws/analysis/{analysis_id}`

## Notes for Judges and Demo Reviewers

- Use seeded demo account for instant walkthrough.
- Upload flow enforces strict file validation and abuse controls.
- Bias score combines statistical metrics with swarm consensus rationale.
- Shared report pages support sanitized rendering for safe display.

## Known Warnings

- Frontend lint shows non-blocking React Hook dependency warnings in dashboard/report pages.
- Some npm advisories originate in transitive dependencies and can be addressed in a dependency-upgrade pass.

## License

No license file is currently included in this repository. Add one before public distribution.
