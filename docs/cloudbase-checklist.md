# Tencent CloudBase Checklist

Use this checklist to deploy the outer `brief_wechat` repo as the source of truth. The ignored `time_logger_game/` directory is not part of deployment.

## Console Steps

| Step | Where | Action | Notes |
|---|---|---|---|
| 1 | CloudBase left nav: SQL 型数据库 | Open the built-in MySQL database | Use MySQL 8.0 if available. Keep the default VPC/subnet unless you have a reason to change it. |
| 2 | SQL 型数据库 details | Create or confirm database name, username, password, host, and port | These become `DATABASE_URL`. Use the internal host/IP for CloudBase Run. |
| 3 | CloudBase left nav: 云存储 | Confirm cloud storage is enabled | Mini Program uploads audio with `wx.cloud.uploadFile`; the backend receives the returned CloudBase `fileID`. |
| 4 | Local Mini Program code | Set CloudBase env id | Put your env id, for example `cloud1-d1gvgrhtq5b993f00`, in `miniprogram/env.ts`. |
| 5 | CloudBase left nav: 云函数 / 托管 / 主机 | Open 云托管 -> 服务管理 | Do not use 函数管理. This backend is Docker/FastAPI, not a cloud function. |
| 6 | 云托管 -> 服务管理 | Create a new service | Example service name: `brief-backend`. |
| 7 | New service | Select GitHub repository deployment | Repository: `zhou100/brief_wechat`. |
| 8 | New service | Set build/code directory | `backend` |
| 9 | New service | Set Dockerfile path | Use `backend/Dockerfile`; if CloudBase treats `backend` as the working directory, use `Dockerfile`. |
| 10 | New service | Set service port | `10000` |
| 11 | New service | Add environment variables | Use the table below. |
| 12 | After deployment | Check health endpoint | Open `https://<cloudbase-run-domain>/health`; it should return `status: ok`. |
| 13 | WeChat public platform | Configure legal domains | Add the CloudBase Run HTTPS domain to `request`. CloudBase native upload does not use your backend `uploadFile` domain. |
| 14 | Local terminal | Rebuild Mini Program JS | Run `npm run build`. |
| 15 | WeChat DevTools | Compile and test | Test login, recording, CloudBase upload, processing, result, delete, regenerate, and share. |

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
| `USE_CLOUDBASE_STORAGE` | `true` |
| `MOONSHOT_API_KEY` | Your Moonshot/Kimi API key |
| `MOONSHOT_BASE_URL` | `https://api.moonshot.cn/v1` |
| `MOONSHOT_MODEL` | `kimi-k2.5` |
| `XFYUN_APP_ID` | Your iFlytek app id |
| `XFYUN_API_KEY` | Your iFlytek API key |
| `XFYUN_API_SECRET` | Your iFlytek API secret |
| `XFYUN_IAT_URL` | `wss://iat.cn-huabei-1.xf-yun.com/v1` |
| `ALLOWED_ORIGINS_STR` | `*` |

Example:

```text
DATABASE_URL=mysql+aiomysql://root:your_password@172.17.0.14:3306/cloud1-d1gvgrhtq5b993f00?charset=utf8mb4
```

## Mini Program Configuration

After the backend deploys successfully, update:

```ts
// miniprogram/env.ts
export const API_BASE_URL = "https://<cloudbase-run-domain>";
export const CLOUDBASE_ENV_ID = "cloud1-d1gvgrhtq5b993f00";
export const REQUEST_TIMEOUT_MS = 20000;
export const JOB_POLL_INTERVAL_MS = 1600;
export const USE_MOCK_API = false;
export const USE_CLOUDBASE_UPLOAD = true;
```

Then run:

```bash
npm run build
```

## WeChat Public Platform Settings

| Setting | Value |
|---|---|
| request 合法域名 | CloudBase Run HTTPS domain |
| uploadFile 合法域名 | Not needed for `wx.cloud.uploadFile`; only add custom upload domains if you switch back to backend upload |
| downloadFile 合法域名 | CloudBase/COS temp download domain if DevTools or real-device testing asks for it |
| 用户隐私保护指引 | State that the app collects user-submitted audio, transcript text, summaries, open loops, and WeChat account identifiers only to generate records and summaries. |

## Verification

Backend:

```text
GET /health
POST /miniapp/auth/login
POST /miniapp/entries
GET /miniapp/jobs/{job_id}
GET /miniapp/entries/{entry_id}/result
```

Mini Program:

```text
home -> record -> stop -> wx.cloud.uploadFile -> job -> result -> share
```

## Important Notes

- Use CloudBase 云托管 -> 服务管理, not 函数管理.
- Use CloudBase built-in MySQL for this deployment.
- Audio upload uses CloudBase native storage: `wx.cloud.uploadFile -> fileID -> /miniapp/entries`.
- Do not expose `WECHAT_SECRET` or OpenAI API key in Mini Program code.
- The backend initializes MySQL tables from SQLAlchemy models on startup. Old Alembic history is retained for legacy Postgres deployments but not used for CloudBase MySQL.
