# Stage 8 — Production Hardening + Deployment Readiness Audit

## Scope
Stage 7 audited as a production candidate. No live deployment was performed because this environment has no Telegram bot credentials or production hosting target.

## Hardening completed
- Production startup refuses:
  - missing BOT_TOKEN
  - wildcard CORS
  - non-HTTPS API_ALLOWED_ORIGIN
  - missing/non-HTTPS MINIAPP_URL
  - API_DEV_MODE enabled
- Telegram initData remains the production authentication mechanism.
- Per-user/IP in-memory API rate limiting with HTTP 429 + Retry-After.
- Security response headers:
  - X-Content-Type-Options
  - X-Frame-Options
  - Referrer-Policy
  - Permissions-Policy
  - HSTS in production
- Mini App Content Security Policy added.
- JSON body size guard retained.
- Multipart upload size/count guards retained.
- Durable storage and backup configuration remains environment-driven.
- SQLite backup helper retained with restrictive backup permissions.
- Dockerfile and production docker-compose configuration added.
- `.env.production.example` added with no real secrets.
- `.dockerignore` excludes DB, storage, uploads, caches and tests from image context.

## Validation
- 46/46 tests passed
- Preflight: PASS
- Python compile: PASS
- Mini App JavaScript syntax: PASS
- Static security scan: no secret-like literals found
- Deployment artifact checks: PASS

## Environment limitation
Docker CLI/daemon is not installed in the audit sandbox, so an actual image build/push was not claimed.
Telegram production deployment was not claimed because BOT_TOKEN, public HTTPS hosting and domain/certificate are deployment-specific secrets/infrastructure.

## Production configuration
Required:
- BOT_TOKEN
- MINIAPP_URL=https://...
- API_ALLOWED_ORIGIN=https://...
- API_ENV=production
- API_DEV_MODE=0
- LEGALBOT_DB_PATH=/data/legal_bot.db
- LEGALBOT_STORAGE_DIR=/data/storage
- LEGALBOT_BACKUP_DIR=/data/backups

Optional AI:
- AI_ENABLED
- AI_EXTERNAL_DATA_CONSENT
- DEEPSEEK_API_KEY

## Recommended deployment sequence
1. Provision HTTPS domain/reverse proxy.
2. Set production environment variables/secrets.
3. Run DB initialization/migrations.
4. Start API and Telegram bot as separate services using the shared persistent volume.
5. Point Telegram Mini App button to MINIAPP_URL.
6. Verify `/healthz`, Telegram initData authentication, upload, AI credit rollback, and draft versioning.
7. Enable scheduled backups and monitor logs.
