# ShalaEmes — backend

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.162-009688?logo=fastapi&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)
![Deploy](https://img.shields.io/badge/deploy-DigitalOcean%20%2B%20Caddy-0080FF?logo=digitalocean&logoColor=white)

FastAPI service for **ShalaEmes**, an Android assistant that helps Kazakh speakers replace foreign words and filler words with natural Kazakh alternatives.

The backend owns sessions, the LLM annotation pipeline, progress and the SQLite database. It talks to the ASR service (Whisper + Kazakh LoRA) and to DeepSeek for word classification.

Part of the platform:

- [**Android app**](https://github.com/Maskatik/shalaemes-android)
- **Backend** (this repository)
- [**ASR service**](https://github.com/Maskatik/shalaemes-asr)

## What it does

```text
audio ──► ASR service ──► transcript with timestamps
                              │
                              ▼
                     LLM annotation (DeepSeek)
                              │
                              ▼
        categories · suggestions · advice · XP · sessions
```

- `POST /api/sessions` — create a session.
- `POST /api/sessions/{id}/chunks` — upload audio.
- `POST /api/sessions/{id}/finish` — start processing.
- `GET /api/sessions/{id}` — poll status and fetch the annotated transcript.
- Sessions, profile, words and data deletion endpoints for the Android client.

## API

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Status and active ASR/LLM providers. |
| `POST` | `/api/sessions` | Create a session. |
| `GET` | `/api/sessions` | Session list with top words. |
| `GET` | `/api/sessions/{id}` | Session detail, words and summary. |
| `POST` | `/api/sessions/{id}/chunks` | Upload an audio chunk. |
| `POST` | `/api/sessions/{id}/finish` | Finish the session and start processing. |
| `DELETE` | `/api/sessions/{id}` | Delete one session. |
| `PATCH` | `/api/sessions/{id}/words/{idx}` | Flag a word as `none` / `asr_error`. |
| `POST` | `/api/sessions/{id}/words/{idx}/learn` | Mark a word as learned (+20 XP). |
| `GET` | `/api/profile` | Level, XP, stats, achievements. |
| `GET` | `/api/words?period=today\|week\|all` | Aggregated words for the home screen. |
| `POST` | `/api/words/{lemma}/learn` | Mark a word as learned from the home screen. |
| `DELETE` | `/api/data` | Delete sessions, words and progress. |

OpenAPI docs are served at `/docs` unless `DOCS_ENABLED=0`.

## Quick start

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Windows:

```powershell
cd backend
.\run.ps1
```

Check:

```bash
curl http://127.0.0.1:8080/health
```

## Configuration

Copy `.env.example` to `.env` and fill in the keys. The main variables:

| Variable | Description |
| --- | --- |
| `ASR_PROVIDER` | `stub`, `krasr` or `remote`. |
| `ASR_SERVICE_URL` | URL of the ASR service, e.g. a RunPod proxy URL. |
| `ASR_SERVICE_API_KEY` | Bearer key for the ASR service. |
| `ASR_SERVICE_TIMEOUT` | ASR timeout in seconds. |
| `LLM_PROVIDER` | `deepseek`, `openai`, `openrouter`, `ollama` or `stub`. |
| `LLM_API_KEY` | LLM provider key. |
| `LLM_MODEL` / `LLM_BASE_URL` | Model and endpoint. |
| `SHALAEMES_DATA_DIR` | Directory for SQLite (default `./data`). |
| `API_TOKEN` | Optional bearer token for `/api/*`. Empty means disabled. |
| `DOCS_ENABLED` | `0` disables `/docs` and `/openapi.json`. |

## Docker and deployment

```bash
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8080/health
```

The image is production-ready: non-root user, healthcheck, `/data` volume, `PORT`/`WEB_CONCURRENCY` support and proxy headers.

Full instructions (Docker Compose, Caddy/HTTPS, DigitalOcean App Platform, backups and security) are in [`DEPLOY.md`](DEPLOY.md).

## Tests

```bash
pytest -q
```

16 tests cover the API, ASR clients, LLM, words and data deletion.

## Project structure

```text
app/
  main.py              application factory, optional API token
  config.py            environment settings
  db.py                SQLite schema and seed
  lexicon.py           starter dictionary
  routers/             health, sessions, words, profile, data
  services/            ASR, LLM, pipeline, annotation, progress
  prompts/annotate.md  LLM prompt
tests/                 pytest suite
Dockerfile
docker-compose.yml
run_server.py          PORT / workers / proxy headers
```

## Status

The backend is deployed over HTTPS behind Caddy, stores data on a persistent volume, and works with real ASR on RunPod. Per-user authentication and the Play Store release are the next milestones.
