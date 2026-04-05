# FairSwarm Pre-Submission Checklist

## Security

- [ ] Verify all production secrets are set in hosting platforms (no placeholder values).
- [ ] Confirm `backend/.env` is not committed.
- [ ] Validate auth flow: register, login, refresh, logout.
- [ ] Confirm CSRF protection works for state-changing API calls.
- [ ] Confirm request-size and upload signature checks are active.
- [ ] Confirm rate limits trigger correctly for upload and analysis endpoints.

## Data and Analysis

- [ ] Run demo seed script: `python -m scripts.seed_demo_data`.
- [ ] Confirm demo account login works.
- [ ] Confirm seeded datasets appear in dashboard.
- [ ] Run one end-to-end analysis from upload to report.
- [ ] Validate swarm consensus section renders with agent cards.

## Testing and Quality

- [ ] Run backend tests: `pytest`.
- [ ] Confirm backend coverage remains >= 80% (current gate: 86% on core analysis modules).
- [ ] Run backend lint: `ruff check app tests`.
- [ ] Run backend type checks: `mypy app/services/dataset_processor.py app/services/fairness_metrics.py`.
- [ ] Run frontend type checks: `npx tsc --noEmit`.
- [ ] Run frontend build: `npm run build`.
- [ ] Run frontend lint: `npm run lint`.

## CI/CD and Deployment

- [ ] Confirm GitHub Actions secrets are set for Vercel and Railway.
- [ ] Confirm `ci.yml` passes on latest commit.
- [ ] Confirm `deploy.yml` smoke test URLs are correct.
- [ ] Deploy frontend to Vercel.
- [ ] Deploy backend to Railway.
- [ ] Verify production health endpoint: `/health`.

## Demo Readiness

- [ ] Prepare 3-minute walkthrough path (login -> upload -> analysis -> report).
- [ ] Keep backup local run command ready: `docker compose up --build`.
- [ ] Keep fallback static screenshots of reports in case of network instability.
- [ ] Verify judge-visible features load in a clean incognito session.
