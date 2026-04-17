# Brief WeChat Mini Program

Brief WeChat is a lightweight Mini Program client for voice capture, AI summary, and share-card growth.

This repo does not copy the existing React web app. It keeps `time_logger_game/` as a local ignored reference and builds a new WeChat-runtime client around the smallest useful loop:

```text
open -> start -> record -> CloudBase upload -> backend job -> structured result -> share summary card
```

## Product Scope

First version:

- record and upload audio with CloudBase native storage
- poll backend job status
- show structured result:
  - one-sentence summary
  - 3 to 5 key points
  - open loops
- delete one entry
- regenerate one entry
- share a summary card
- show read-only share landing page

Deferred:

- realtime transcription
- waveform visualization
- complex editing
- charts and analytics
- full long report sharing
- direct AI calls from the client

## Structure

```text
miniprogram/
  pages/                 main package: index, record, job, result, me
  pkg_history/           subpackage: history stubs and read-only share landing
  pkg_settings/          subpackage: settings, privacy, feedback, binding
  services/              auth, request, upload, entry APIs, recorder
  types/                 API types
docs/
  architecture.md        product and technical boundary
  api-contract.md        /miniapp/* BFF contract
  compliance.md          WeChat privacy and launch checklist
```

## Local Setup

```bash
npm install
npm run build
cp miniprogram/env.example.ts miniprogram/env.ts
```

Update `miniprogram/env.ts`:

```ts
export const API_BASE_URL = "https://your-api.example.com";
```

Open this repo root in WeChat DevTools with `project.config.json`.

## Backend Contract

The Mini Program expects a first-party BFF layer:

- `POST /miniapp/auth/login`
- `POST /miniapp/entries`
- `GET /miniapp/jobs/{job_id}`
- `GET /miniapp/entries/{entry_id}/result`
- `DELETE /miniapp/entries/{entry_id}`
- `POST /miniapp/entries/{entry_id}/regenerate`
- `POST /miniapp/share/cards`
- `GET /miniapp/share/cards/{share_id}`

The BFF lives in `backend/` and exposes the Mini Program API without making the Mini Program depend on the old Web API surface.

## Tencent Cloud Deployment

The full Tencent Cloud target uses CloudBase Run, CloudBase MySQL, and CloudBase native storage. It is documented in:

- `docs/tencent-cloudbase.md`
- `docs/cloudbase-checklist.md`
- `deployment/tencent-cloudbase-env.example`
- `miniprogram/env.tencent.example.ts`
