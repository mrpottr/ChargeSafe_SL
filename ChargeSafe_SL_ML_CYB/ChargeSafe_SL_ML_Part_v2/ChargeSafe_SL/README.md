# ChargeSafe SL

ChargeSafe SL is a web platform focused on EV charging safety and cyber risk awareness for Sri Lanka, combining a FastAPI backend, React frontend, and PostgreSQL data layer in a Docker-first development workflow.

## Overview

This repository contains the current working system foundation for:

- API service and database connectivity
- Charging station data retrieval
- Health and readiness monitoring endpoints
- Containerized local development for team collaboration

## Technology Stack

- Backend: FastAPI, SQLAlchemy, Psycopg
- Frontend: React, Vite
- Database: PostgreSQL 16
- DevOps: Docker Compose

## System Architecture

- `frontend` (React/Vite) consumes API endpoints from `backend`
- `backend` (FastAPI) serves REST endpoints and queries PostgreSQL
- `db` (PostgreSQL) initializes schema from `database/init/001_schema.sql`
- Services are orchestrated through `docker-compose.yml`

## Repository Structure

- `backend/` FastAPI service source and Dockerfile
- `frontend/` React application source and Dockerfile
- `database/init/001_schema.sql` PostgreSQL schema bootstrap
- `database/create_database.ps1` local database bootstrap script
- `docker-compose.yml` multi-service orchestration
- `.env.example` local (non-Docker) environment template
- `.env.docker.example` Docker environment template

## Implemented API Endpoints

- `GET /api/health` database connectivity health check
- `GET /api/ready` service readiness check
- `GET /api/stations` latest charging stations (up to 50 rows)

Interactive docs are available at `/docs` when backend is running.

## Database

The schema is defined in `database/init/001_schema.sql` and includes:

- Core station and user entities
- Incident reporting entities
- Cyber/ML score support tables
- Geospatial support via `cube` and `earthdistance`
- Audit and chatbot session tables

PostgreSQL initialization behavior:

- SQL scripts in `/docker-entrypoint-initdb.d/` run only when the DB volume is new/empty.
- If schema changes are made later, apply migrations or recreate the DB volume in development.

## Quick Start (Docker)

1. Create Docker env file:

```powershell
Copy-Item .env.docker.example .env.docker
```

2. Update values in `.env.docker` if required (passwords/ports).

3. Start all services:

```powershell
docker compose --env-file .env.docker up --build
```

4. Access services:

- Frontend: `http://localhost:5173`
- Backend API docs: `http://localhost:8000/docs`
- Backend health: `http://localhost:8000/api/health`

## Local Development (Without Docker)

1. Create local env file:

```powershell
Copy-Item .env.example .env
```

2. Ensure PostgreSQL is available locally and run schema bootstrap if needed.

3. Start backend:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

4. Start frontend:

```powershell
cd frontend
npm install
npm run dev
```

## Environment Variables

Defined through `.env.example` and `.env.docker.example`:

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_PORT`
- `BACKEND_PORT`
- `FRONTEND_PORT`
- `BACKEND_CORS_ORIGINS`
- `VITE_API_BASE_URL`

## Team Collaboration Workflow

- Use a shared Git repository with protected `main`
- Create feature branches: `feature/<name>`, `fix/<name>`
- Open PRs for every merge and require at least one review
- Keep secrets out of Git (`.env`, `.env.docker` should stay uncommitted)
- Commit only template config files (`.env.example`, `.env.docker.example`)
- Validate the full stack with Docker Compose before merging

New contributors should follow the full step-by-step onboarding document:
`TEAM_ONBOARDING_GUIDE.md`

## Security and Operational Notes

- Do not store real secrets in tracked files.
- Keep local ports configurable to avoid conflicts with other running projects.
- Use container health checks (`db`) as startup dependency gating for backend readiness.
