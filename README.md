# ChargeSafe SL

ChargeSafe SL is a team-ready full-stack platform scaffold built with FastAPI, React, and PostgreSQL.

## Stack

- Backend: FastAPI + SQLAlchemy + Psycopg
- Frontend: React + Vite
- Database: PostgreSQL 16
- Container orchestration: Docker Compose

## Project structure

- `database/init/001_schema.sql`: PostgreSQL schema with the requested `station_images` omission
- `database/create_database.ps1`: local PostgreSQL bootstrap script
- `backend/`: FastAPI service
- `frontend/`: React client
- `docker-compose.yml`: shared team development environment

## Team workflow with Docker

1. Copy `.env.docker.example` to `.env.docker`
2. Set a shared local password in `.env.docker`
3. Start the stack:

```powershell
docker compose --env-file .env.docker up --build
```

4. Open the apps:

- Frontend: `http://localhost:5173`
- Backend docs: `http://localhost:8000/docs`
- Backend health: `http://localhost:8000/api/health`

The PostgreSQL schema is automatically applied when the `db` container initializes for the first time.

## Local workflow without Docker

1. Copy `.env.example` to `.env`
2. Update your PostgreSQL credentials
3. Create the database:

```powershell
.\database\create_database.ps1
```

4. Run the backend:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

5. Run the frontend:

```powershell
cd frontend
npm install
npm run dev
```

## API endpoints

- `GET /api/health`
- `GET /api/ready`
- `GET /api/stations`

## Notes

- The schema enables `pgcrypto`, `cube`, and `earthdistance`.
- The `station_images` table was intentionally excluded.
- Docker is the recommended path for team collaboration to avoid environment drift.
