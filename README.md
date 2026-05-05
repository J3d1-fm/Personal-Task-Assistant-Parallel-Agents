# Personal Task Tracker

Private task tracker for Personal Codex.

It provides:

- A web UI for reviewing, assigning, and completing tasks.
- A JSON API for Codex and integrations to create and update tasks.
- Database-backed storage, with SQLite for local development and PostgreSQL for Google Cloud.
- Reminder fields so missed tasks can be queried and notified.

## Local Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.
This workspace currently has a local `.env` with `TASK_TRACKER_API_KEY=dev-key`.

## Google Login

The web UI is protected with Google OAuth. Create OAuth credentials in Google Cloud
Console and add this redirect URI:

```text
http://127.0.0.1:8000/auth/google/callback
```

For Cloud Run, add the deployed callback URL too:

```text
https://<cloud-run-url>/auth/google/callback
```

Then set:

```bash
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
ALLOWED_GOOGLE_EMAILS=your-email@gmail.com
SESSION_SECRET_KEY=long-random-secret
```

The JSON API still supports `Authorization: Bearer <TASK_TRACKER_API_KEY>` for Codex,
reminder jobs, and external ingestion.

## API

Set `TASK_TRACKER_API_KEY` in `.env`. API clients must send:

```http
Authorization: Bearer <key>
```

Main endpoints:

- `GET /api/tasks`
- `POST /api/tasks`
- `PATCH /api/tasks/{task_id}`
- `POST /api/ingest/context`
- `GET /api/reminders/due`

## Google Cloud

The intended production shape is Cloud Run + Cloud SQL for PostgreSQL.

Use `deploy/gcloud.example.sh` as a deployment checklist after creating a GCP project,
Artifact Registry repository, Cloud SQL Postgres instance, and a Secret Manager secret
for the API key.
