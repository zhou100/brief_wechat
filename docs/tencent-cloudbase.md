# Tencent Cloud Full Deployment

Target stack:

```text
WeChat Mini Program
  -> CloudBase Run / CloudBase Hosting domain
  -> FastAPI Docker backend
  -> Tencent Cloud PostgreSQL-compatible database
  -> Tencent COS for audio
  -> OpenAI-compatible AI pipeline from existing worker
```

## Why CloudBase Run

The backend is a Dockerized FastAPI app with an embedded worker. CloudBase Run supports containerized services, so we can deploy it without rewriting the backend into cloud functions.

Do not migrate the backend to CloudBase document database in this phase. The current app relies on SQLAlchemy, Alembic, joins, indexes, and PostgreSQL semantics. Moving to a document database would be a rewrite.

## Tencent Resources To Create

1. CloudBase environment.
2. CloudBase Run service for `time_logger_game/backend`.
3. Tencent COS bucket for audio.
4. PostgreSQL-compatible Tencent database.
5. Mini Program legal domains:
   - request domain: CloudBase Run HTTPS domain
   - uploadFile domain: same CloudBase Run HTTPS domain
   - downloadFile domain: same domain or COS CDN domain if share images are added

## Backend Environment Variables

Set these in CloudBase Run:

```text
ENVIRONMENT=production
LOG_LEVEL=INFO
PORT=10000

DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/DBNAME
SECRET_KEY=<long random secret>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=240

WECHAT_APPID=<mini program appid>
WECHAT_SECRET=<mini program appsecret>
MINIAPP_PUBLIC_BASE_URL=https://<cloudbase-run-domain>

OPENAI_API_KEY=<openai key>

S3_ENDPOINT_URL=https://cos.<region>.myqcloud.com
S3_PUBLIC_ENDPOINT_URL=https://cos.<region>.myqcloud.com
S3_ACCESS_KEY=<tencent secret id>
S3_SECRET_KEY=<tencent secret key>
S3_BUCKET=<cos bucket name>
S3_REGION=<region>

ALLOWED_ORIGINS_STR=*
```

COS also supports S3-compatible access. If a region-specific endpoint differs in your Tencent console, use the endpoint shown by COS.

## Deployment Steps

1. Build and push the backend Docker image from:

```text
backend
```

2. CloudBase Run deploys the existing Dockerfile:

```text
backend/Dockerfile
```

3. On startup, the container runs:

```text
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
```

4. Verify:

```text
GET /health
POST /miniapp/auth/login
```

5. In the Mini Program, set:

```ts
export const API_BASE_URL = "https://<cloudbase-run-domain>";
export const USE_MOCK_API = false;
```

6. Run:

```bash
npm run build
```

7. Test on device:

```text
login -> record -> upload -> job -> result -> share
```

## Notes

- Keep `WECHAT_SECRET` only in CloudBase Run environment variables. Never put it in Mini Program code.
- First version uploads audio through the backend via `wx.uploadFile`; this keeps auth, validation, and object ownership centralized.
- Later, if audio traffic grows, switch `/miniapp/uploads/create` to return a short-lived COS direct-upload credential.
