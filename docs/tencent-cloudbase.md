# Tencent Cloud Full Deployment

Target stack:

```text
WeChat Mini Program
  -> CloudBase native storage for audio
  -> CloudBase Run / CloudBase Hosting domain
  -> FastAPI Docker backend
  -> CloudBase built-in MySQL
  -> iFlytek ASR + TokenHub LLM tidy pipeline
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

TOKENHUB_API_KEY=<tokenhub key>
TOKENHUB_BASE_URL=https://tokenhub.tencentmaas.com/v1
LLM_MODEL=deepseek-v3.2
CLASSIFICATION_MODEL=deepseek-v3.2
CLASSIFICATION_FALLBACK_MODEL=hunyuan-2.0-instruct-20251111
CLASSIFICATION_TEMPERATURE=0.2
CLASSIFICATION_TIMEOUT_SECONDS=20

XFYUN_APP_ID=<xfyun app id>
XFYUN_API_KEY=<xfyun api key>
XFYUN_API_SECRET=<xfyun api secret>
XFYUN_IAT_URL=wss://iat.cn-huabei-1.xf-yun.com/v1
XFYUN_EOS_MS=5000
XFYUN_FRAME_INTERVAL_SECONDS=0
XFYUN_FALLBACK_FRAME_INTERVAL_SECONDS=0.04
XFYUN_SEGMENT_CONCURRENCY=2
XFYUN_MAX_SEGMENT_SECONDS=55
XFYUN_SILENCE_RMS_THRESHOLD=200
XFYUN_SILENCE_SPLIT_SECONDS=1.2
XFYUN_KEEP_SILENCE_SECONDS=0.25
TRANSCRIPT_REFINE_ENABLED=false
MINIAPP_TIDY_REFINE_ENABLED=true

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
export const REQUEST_TIMEOUT_MS = 20000;
export const TIDY_TIMEOUT_MS = 60000;
export const JOB_POLL_INTERVAL_MS = 1600;
export const USE_MOCK_API = false;
export const USE_CLOUDBASE_UPLOAD = true;
```

6. Run:

```bash
npm run build
```

7. Test on device:

```text
login -> record -> wx.cloud.uploadFile -> job -> raw transcript -> one-tap tidy -> share
```

## Notes

- Keep `WECHAT_SECRET` only in CloudBase Run environment variables. Never put it in Mini Program code.
- The Mini Program uploads audio to CloudBase storage and only sends `fileID` plus a temp URL to the backend.
- The backend still has the old S3-compatible upload path for non-CloudBase clients, but CloudBase production should use the native path.
- iFlytek audio frames are sent as fast as the websocket accepts by default. If the fast path fails, the backend retries once with `XFYUN_FALLBACK_FRAME_INTERVAL_SECONDS=0.04`.
- New recordings finish after transcription. The miniapp's "一键理清爽" action runs transcript refinement and categorization on demand.
