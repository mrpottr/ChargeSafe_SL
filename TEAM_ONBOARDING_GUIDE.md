# ChargeSafe SL Team Onboarding Guide

This guide is for teammates who are new to GitHub, Docker, and PostgreSQL.
Follow each step in order.

## 1. What You Need

Install these tools on Windows:

1. Git: https://git-scm.com/download/win
2. Docker Desktop: https://www.docker.com/products/docker-desktop/
3. Node.js LTS (recommended): https://nodejs.org/
4. VS Code (recommended): https://code.visualstudio.com/

After installation, restart your computer once.

## 2. First-Time Accounts and Access

1. Create a GitHub account: https://github.com/signup
2. Ask the project owner to add your GitHub username to the repository as a collaborator.
3. Accept the collaborator invitation from your email or GitHub notifications.

## 3. Clone the Repository

Open PowerShell and run:

```powershell
cd "E:\ECU_stuffs\APPLIED PROJECT"
git clone <REPOSITORY_URL>
cd ChargeSafeSL
```

How to get `<REPOSITORY_URL>`:

1. Open the repo on GitHub.
2. Click the green `Code` button.
3. Copy HTTPS URL.

## 4. Create Your Local Environment File

In the project root:

```powershell
Copy-Item .env.docker.example .env.docker
```

Open `.env.docker` and set at least:

- `POSTGRES_PASSWORD` to your own local password

If ports are already used on your machine, change these values:

- `POSTGRES_PORT` (example: `5433`)
- `BACKEND_PORT` (example: `8001`)
- `FRONTEND_PORT` (example: `5174`)

## 5. Start the Project with Docker

Run:

```powershell
docker compose --env-file .env.docker up --build
```

Wait until all services are up.

Open in browser:

- Frontend: `http://localhost:<FRONTEND_PORT>`
- Backend docs: `http://localhost:<BACKEND_PORT>/docs`
- Health check: `http://localhost:<BACKEND_PORT>/api/health`

Example with defaults:

- `http://localhost:5173`
- `http://localhost:8000/docs`

## 6. PostgreSQL Basics for This Project

You do not need to install PostgreSQL manually for normal team work.
Docker runs PostgreSQL in a container.

Important behavior:

1. `database/init/001_schema.sql` runs automatically only on first DB creation.
2. If schema file changes later, old DB volume keeps old state.
3. For development, you can reset DB containers/volumes when needed.

## 7. Daily Team Workflow (Simple)

Use this process every time:

1. Pull latest code:

```powershell
git checkout main
git pull origin main
```

2. Create your feature branch:

```powershell
git checkout -b feature/<short-task-name>
```

3. Make code changes.

4. Run and test with Docker:

```powershell
docker compose --env-file .env.docker up --build
```

5. Commit your changes:

```powershell
git add .
git commit -m "Add <what-you-changed>"
```

6. Push your branch:

```powershell
git push -u origin feature/<short-task-name>
```

7. Open a Pull Request on GitHub from your branch to `main`.
8. Request at least one teammate review.
9. Merge only after approval.

## 8. Rules That Prevent Team Problems

1. Never commit `.env` or `.env.docker`.
2. Commit only template files like `.env.example` and `.env.docker.example`.
3. Never push directly to `main`.
4. One feature per branch.
5. Pull latest `main` before starting new work.
6. Use clear commit messages.

## 9. How to Stop and Restart Containers

Stop containers:

```powershell
docker compose --env-file .env.docker down
```

Start again:

```powershell
docker compose --env-file .env.docker up --build
```

## 10. Common Errors and Fixes

Port already in use:

1. Edit `.env.docker`
2. Change ports (`POSTGRES_PORT`, `BACKEND_PORT`, `FRONTEND_PORT`)
3. Restart compose

Containers start but app not loading:

1. Check Docker Desktop container status
2. Open logs:

```powershell
docker compose --env-file .env.docker logs -f
```

Schema changes not appearing:

1. Old DB volume is still active
2. Recreate DB for development when team agrees

Git says branch is behind:

```powershell
git checkout main
git pull origin main
git checkout feature/<your-branch>
git merge main
```

## 11. First Task Checklist (for New Teammates)

1. Can clone repo
2. Can run `docker compose ... up --build`
3. Can open frontend and backend docs in browser
4. Can create a branch
5. Can push branch and open PR

If all 5 are done, you are fully ready to collaborate on ChargeSafe SL.

## 12. Quick Git Commands (Push/Pull Cheat Sheet)

Use this exact sequence.

Start of day (get latest team code):

```bash
git checkout main
git pull origin main
```

Meaning:

- `git checkout main` moves you to the main branch
- `git pull origin main` downloads latest main from GitHub

Start a new task:

```bash
git checkout -b feature/my-task
```

Meaning:

- creates your branch and switches to it

Save your code changes:

```bash
git add .
git commit -m "Describe what you changed"
```

Meaning:

- `git add .` stages changes
- `git commit` saves a local snapshot

Push your branch to GitHub:

```bash
git push -u origin feature/my-task
```

Meaning:

- uploads your feature branch (not main)

Open Pull Request on GitHub:

1. Go to your repo page
2. Click `Compare & pull request`
3. Base branch: `main`
4. Compare branch: `feature/my-task`
5. Create PR and request review

After PR is merged:

```bash
git checkout main
git pull origin main
git branch -d feature/my-task
```

Meaning:

- sync local main with merged code
- delete old local feature branch

If your branch gets behind main:

```bash
git checkout main
git pull origin main
git checkout feature/my-task
git merge main
git push
```

Golden rule:

- Do not use `git push origin main` for daily work.
- Always push to your own `feature/...` branch, then merge with a PR.
