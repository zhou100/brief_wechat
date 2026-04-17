# Tencent Cloud Full Deployment

Target stack:

```text
WeChat Mini Program
  -> CloudBase native storage for audio
  -> CloudBase Run / CloudBase Hosting domain
  -> FastAPI Docker backend
  -> CloudBase built-in MySQL
  -> OpenAI-compatible AI pipeline from existing worker
```

## Why CloudBase Run

The backend is a Dockerized FastAPI app with an embedded worker. CloudBase Run supports containerized services, so we can deploy it without rewriting the backend into cloud functions.

Use CloudBase built-in MySQL for the first production deployment. The backend models use SQLAlchemy portable UUID/JSON types so the same app can run on MySQL.

Audio upload should use CloudBase native storage from the Mini Program. The client sends the CloudBase `fileID` and a short-lived temp URL to `/miniapp/entries`; the backend downloads the audio for transcription and stores the `fileID` on the entry.

## Tencent Resources To Create

1. CloudBase environment.
2. CloudBase Run service for `backend/`.
3. CloudBase native storage.
4. CloudBase built-in MySQL database.
5. Mini Program legal domains:
   - request domain: CloudBase Run HTTPS domain
   - uploadFile domain: not needed for `wx.cloud.uploadFile`
   - downloadFile domain: CloudBase/COS temp download domain if requested by DevTools or real-device testing

## Backend Environment Variables

Set these in CloudBase Run:

```text
ENVIRONMENT=production
LOG_LEVEL=INFO
PORT=10000

DATABASE_URL=mysql+aiomysql://USER:PASSWORD@HOST:3306/DBNAME?charset=utf8mb4
SECRET_KEY=<long random secret>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=240

WECHAT_APPID=<mini program appid>
WECHAT_SECRET=<mini program appsecret>
MINIAPP_PUBLIC_BASE_URL=https://<cloudbase-run-domain>
USE_CLOUDBASE_STORAGE=true

OPENAI_API_KEY=<openai key>

ALLOWED_ORIGINS_STR=*
```

## Deployment Steps

1. CloudBase Run deploys from:

```text
backend
```

2. Use the existing Dockerfile:

```text
backend/Dockerfile
```

3. On startup, the container runs:

```text
python scripts/init_db.py
uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
```

For MySQL deployments, the app initializes the schema from current SQLAlchemy models. The old Alembic history is retained for legacy PostgreSQL deployments but is not used for CloudBase MySQL.

4. Verify:

```text
GET /health
POST /miniapp/auth/login
```

5. In the Mini Program, set:

```ts
export const API_BASE_URL = "https://<cloudbase-run-domain>";
export const CLOUDBASE_ENV_ID = "cloud1-d1gvgrhtq5b993f00";
export const USE_MOCK_API = false;
export const USE_CLOUDBASE_UPLOAD = true;
```

6. Run:

```bash
npm run build
```

7. Test on device:

```text
login -> record -> wx.cloud.uploadFile -> job -> result -> share
```

## Notes

- Keep `WECHAT_SECRET` only in CloudBase Run environment variables. Never put it in Mini Program code.
- The Mini Program uploads audio to CloudBase storage and only sends `fileID` plus a temp URL to the backend.
- The backend still has the old S3-compatible upload path for non-CloudBase clients, but CloudBase production should use the native path.
