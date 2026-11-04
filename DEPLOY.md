# ShalaEmes backend — деплой

## Что добавлено

- `Dockerfile` — образ на `python:3.13-slim`, non-root пользователь, healthcheck.
- `entrypoint.sh` — при старте чинит права на `/data` и запускает процесс от пользователя `app`.
- `run_server.py` — читает `PORT`, `WEB_CONCURRENCY`, `LOG_LEVEL`, доверяет `X-Forwarded-*` от прокси.
- `docker-compose.yml` — контейнер + volume `/data` + ротация логов.
- `deploy/env.example` — шаблон production-переменных.
- `app/main.py` — опциональный `API_TOKEN` для `/api/*` и `DOCS_ENABLED`.
- `requirements.txt` — зафиксированные версии.

## 1. Подготовка

На сервере (или локально для проверки):

```bash
cd backend
cp deploy/env.example .env
# заполни .env: ASR_SERVICE_URL, ASR_SERVICE_API_KEY, LLM_API_KEY
```

Ключи **не коммитить**. `.env` и `data/` уже в `.gitignore`.

## 2. Запуск через Docker Compose (VPS)

```bash
docker compose up -d --build
docker compose logs -f api
curl http://127.0.0.1:8080/health
```

Ожидаемый ответ:

```json
{"status":"ok","asr":"remote","llm":"deepseek"}
```

SQLite лежит в volume `shalaemes_data` (`/data/shalaemes.db`) и переживает пересоздание контейнера.

## 3. HTTPS через Caddy (рекомендуется)

Caddy сам получит сертификат. `Caddyfile`:

```caddyfile
api.shalaemes.kz {
    request_body {
        max_size 64MB
    }
    reverse_proxy 127.0.0.1:8080
}
```

```bash
caddy reload --config /etc/caddy/Caddyfile
```

Проверка:

```bash
curl https://api.shalaemes.kz/health
```

Nginx-вариант: `proxy_pass http://127.0.0.1:8080;` + `client_max_body_size 64m;` + `proxy_set_header X-Forwarded-Proto $scheme;`.

## 4. DigitalOcean App Platform (без SSH)

1. Залей содержимое `backend/` в корень GitHub-репозитория: `Dockerfile`, `app/`, `requirements.txt`, `run_server.py`, `entrypoint.sh`. **Не** загружай `.env`, `data/`, `.venv/`, логи.
2. DigitalOcean → **Apps** → **Create App** → GitHub → выбери репозиторий и ветку.
3. Ресурс: **Web Service**, Dockerfile определится сам. HTTP port: **8080**, health check: **`/health`**.
4. Environment Variables — перенеси значения из `deploy/env.example`. Ключи отметь как **Encrypted**. Обязательно:
   - `SHALAEMES_DATA_DIR=/data`
   - `WEB_CONCURRENCY=1`
   - `DOCS_ENABLED=0`
   - `API_TOKEN=` (пока пусто)
5. **Persistent Storage / Volume**: добавь volume, mount path **`/data`**, 1 GiB. Без него SQLite обнулится при следующем деплое.
6. Instance size — минимум 1 GiB RAM, instances = **1**.
7. Deploy. Получишь URL вида `https://shalaemes-api-xxxxx.ondigitalocean.app`.
8. Проверь `https://.../health`. Для своего домена: Settings → Domains → добавь `api.shalaemes.kz`, CNAME на выданный хост; TLS DigitalOcean сделает сам.

`entrypoint.sh` сам выставит права на `/data`, поэтому volume работает независимо от UID.

### Другие PaaS (Railway / Render / Fly.io)

То же самое: Dockerfile, env-переменные, volume в `/data`, healthcheck `/health`, `WEB_CONCURRENCY=1`.

## 5. Бэкап

```bash
docker compose cp api:/data/shalaemes.db ./backup-$(date +%F).db
```

Для согласованного бэкапа лучше остановить API на несколько секунд или использовать `sqlite3 .backup`. Храни копии вне сервера.

## 6. Проверка после деплоя

```bash
curl https://api.shalaemes.kz/health
curl -X POST https://api.shalaemes.kz/api/sessions
```

Полный прогон: создать сеанс → загрузить чанк → `finish` → дождаться `ready`.

## 7. Безопасность

Перед публичным релизом:

- **Авторизация.** Сейчас пользователь один (`id=1`), многопользовательской авторизации нет. Для приватного теста задай `API_TOKEN` — тогда все `/api/*` требуют `Authorization: Bearer <token>` или `X-Api-Key`. Для Play нужна нормальная авторизация по пользователю.
- **HTTPS обязателен.** Backend слушает HTTP и должен стоять за TLS-прокси.
- **Rate limit и лимит тела** — на прокси (в Caddy пример выше).
- **`DOCS_ENABLED=0`** для публичного продакшена, чтобы не светить `/docs`.
- **Ротация ключей** DeepSeek и ASR; ключи только в env.
- **Мониторинг**: healthcheck + внешний uptime-check + алерты на 5xx.
- **Логи** не должны содержать транскрипты и ключи.

## 8. Android

Для обычных пользователей `127.0.0.1:8080` не работает — это адрес только для разработки через `adb reverse`.

- Release-сборка должна ходить на `https://api.shalaemes.kz` (через `BuildConfig`, не хардкод).
- Debug может остаться на `10.0.2.2` / `127.0.0.1`.
- В release убрать cleartext-HTTP из `network_security_config.xml`.
- Если включён `API_TOKEN`, клиент должен отправлять тот же токен.

## 9. ASR и RunPod

- RunPod остаётся внешним сервисом; приложение общается только с backend.
- URL и ключ ASR живут в env backend.
- Держи модель прогретой (`/warmup`) и монтируй volume для кэша HF, иначе каждый холодный старт будет долгим.
