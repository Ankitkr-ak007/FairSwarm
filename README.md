# FairSwarm 🛡️🐝
**A Swarm Intelligence AI Bias Detection Platform**

Inspire by MiroFish's swarm intelligence, FairSwarm uses multiple free AI models running in parallel to analyze bias from specialized perspectives (statistical, contextual, historical, intersectional). Their findings are aggregated via weighted consensus to produce a unified FairSwarm bias score.

## Architecture

- **Frontend**: Next.js 14 App Router, Tailwind CSS, Radix UI, Framer Motion
- **Backend**: FastAPI 0.109, Python 3.11
- **Database**: Supabase PostgreSQL

## Getting Started

1. Clone the repository.
2. Setup environment variables:
   - Copy `backend/.env.example` to `backend/.env` and update values.
   - Copy `frontend/.env.example` to `frontend/.env.local` and update values.
3. Start local development environment:
   ```bash
   docker-compose up --build
   ```
4. Access applications:
   - **Frontend**: `http://localhost:3000`
   - **Backend API Docs**: `http://localhost:8000/docs`
