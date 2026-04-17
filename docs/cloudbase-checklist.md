# Tencent CloudBase Checklist

Use this checklist to deploy the outer `brief_wechat` repo as the source of truth. The ignored `time_logger_game/` directory is not part of deployment.

## Console Steps

| Step | Where | Action | Notes |
|---|---|---|---|
| 1 | CloudBase left nav: SQL 型数据库 | Open the built-in MySQL database | Use MySQL 8.0 if available. Keep the default VPC/subnet unless you have a reason to change it. |
| 2 | SQL 型数据库 details | Create or confirm database name, username, password, host, and port | These become `DATABASE_URL`. |
| 3 | CloudBase left nav: 云存储 | Create an audio bucket | Example bucket name: `brief-audio`. |
| 4 | Tencent Cloud CAM | Create a SecretId / SecretKey | Backend uses this to write COS/cloud storage. Never put it in Mini Program code. |
| 5 | CloudBase left nav: 云函数 / 托管 / 主机 | Open 云托管 -> 服务管理 | Do not use 函数管理. This backend is Docker/FastAPI, not a cloud function. |
| 6 | 云托管 -> 服务管理 | Create a new service | Example service name: `brief-backend`. |
| 7 | New service | Select GitHub repository deployment | Repository: `zhou100/brief_wechat`. |
| 8 | New service | Set build/code directory | `backend` |
| 9 | New service | Set Dockerfile path | Use `backend/Dockerfile`; if CloudBase treats `backend` as the working directory, use `Dockerfile`. |
| 10 | New service | Set service port | `10000` |
| 11 | New service | Add environment variables | Use the table below. |
| 12 | After deployment | Check health endpoint | Open `https://<cloudbase-run-domain>/health`; it should return `status: ok`. |
| 13 | WeChat public platform | Configure legal domains | Add the CloudBase Run HTTPS domain to `request` and `uploadFile`. Add it to `downloadFile` too if needed. |
| 14 | Local Mini Program code | Update `miniprogram/env.ts` | Set `API_BASE_URL` to the CloudBase Run domain and `USE_MOCK_API=false`. |
| 15 | Local terminal | Rebuild Mini Program JS | Run `npm run build`. |
| 16 | WeChat DevTools | Compile and test | Test login, recording, upload, processing, result, delete, regenerate, and share. |

## Backend Environment Variables

Set these in CloudBase Run service settings.

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `LOG_LEVEL` | `INFO` |
| `PORT` | `10000` |
| `DATABASE_URL` | `mysql+aiomysql://USER:PASSWORD@HOST:3306/DBNAME?charset=utf8mb4` |
| `SECRET_KEY` | A long random secret string |
| `ALGORITHM` | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `240` |
| `WECHAT_APPID` | Your Mini Program AppID |
| `WECHAT_SECRET` | Your Mini Program AppSecret |
| `MINIAPP_PUBLIC_BASE_URL` | Your CloudBase Run HTTPS domain |
| `OPENAI_API_KEY` | Your OpenAI API key |
| `S3_ENDPOINT_URL` | Tencent COS endpoint, for example `https://cos.ap-shanghai.myqcloud.com` |
| `S3_PUBLIC_ENDPOINT_URL` | Same as `S3_ENDPOINT_URL` for the first version |
| `S3_ACCESS_KEY` | Tencent Cloud SecretId |
| `S3_SECRET_KEY` | Tencent Cloud SecretKey |
| `S3_BUCKET` | Your COS/cloud storage bucket name |
| `S3_REGION` | Region, for example `ap-shanghai` |
| `ALLOWED_ORIGINS_STR` | `*` |

Example:

```text
DATABASE_URL=mysql+aiomysql://root:your_password@10.0.0.12:3306/brief_wechat?charset=utf8mb4
```

## Mini Program Configuration

After the backend deploys successfully, update:

```ts
// miniprogram/env.ts
export const API_BASE_URL = "https://<cloudbase-run-domain>";
export const REQUEST_TIMEOUT_MS = 20000;
export const JOB_POLL_INTERVAL_MS = 1600;
export const USE_MOCK_API = false;
```

Then run:

```bash
npm run build
```

## WeChat Public Platform Settings

| Setting | Value |
|---|---|
| request 合法域名 | CloudBase Run HTTPS domain |
| uploadFile 合法域名 | CloudBase Run HTTPS domain |
| downloadFile 合法域名 | CloudBase Run HTTPS domain or COS/CDN domain if share images are added |
| 用户隐私保护指引 | State that the app collects user-submitted audio, transcript text, summaries, open loops, and WeChat account identifiers only to generate records and summaries. |

## Verification

Backend:

```text
GET /health
POST /miniapp/auth/login
POST /miniapp/uploads/create
POST /miniapp/uploads/audio
POST /miniapp/entries
GET /miniapp/jobs/{job_id}
GET /miniapp/entries/{entry_id}/result
```

Mini Program:

```text
home -> record -> stop -> upload -> job -> result -> share
```

## Important Notes

- Use CloudBase 云托管 -> 服务管理, not 函数管理.
- Use CloudBase built-in MySQL for this deployment.
- Audio upload goes through the backend first: `wx.uploadFile -> /miniapp/uploads/audio -> COS/cloud storage`.
- Do not expose `WECHAT_SECRET`, Tencent Cloud SecretKey, or OpenAI API key in Mini Program code.
- The backend initializes MySQL tables from SQLAlchemy models on startup. Old Alembic history is retained for legacy Postgres deployments but not used for CloudBase MySQL.
