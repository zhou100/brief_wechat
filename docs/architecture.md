# Mini Program Architecture

## Product Boundary

This Mini Program is not the Web product in a new shell. It is a low-friction input and sharing client.

The first version optimizes one loop:

```text
open -> start -> record -> CloudBase upload -> backend job -> structured result -> share summary card
```

Everything else is secondary. No realtime transcription, no heavy editing, no charts, no complex analytics, and no direct AI calls from the client.

## Client Responsibilities

The Mini Program owns:

1. WeChat login via `wx.login`.
2. Audio capture via `wx.getRecorderManager`.
3. Audio upload via `wx.cloud.uploadFile`.
4. Job polling and resume after leaving the app.
5. Structured result display:
   - summary
   - 3 to 5 key points
   - open loops
6. Delete, regenerate, and share-card actions.

The Mini Program must not:

- Call OpenAI or other third-party AI APIs.
- Store AI keys or object-storage secrets.
- Implement transcription or summary logic locally.
- Share full long reports.

## Backend Responsibilities

The backend owns:

- WeChat code exchange and app session token.
- Audio validation and storage.
- Transcription.
- Structured AI summary generation.
- Job status and failure handling.
- Deletion.
- Regeneration.
- Public read-only share-card data.

Reuse `time_logger_game/backend` services where possible, but add a `/miniapp/*` BFF layer so the Mini Program does not depend on Web API details.

## Package Layout

Main package:

- `/pages/index`: one start action and resume prompt.
- `/pages/record`: start/stop recording, duration, upload retry.
- `/pages/job`: clear processing state and polling.
- `/pages/day`: single-entry structured result page.
- `/pages/me`: account and privacy entry.

Subpackages:

- `/pkg_history`: history, entry stubs, read-only share landing page.
- `/pkg_settings`: settings, privacy, feedback, binding stubs.

Keep the main package small. History and settings are not part of the first-run loop.

## Failure Handling

Required client states:

- Recording unavailable or interrupted.
- Upload failed with retry.
- Job failed with restart path.
- Network interrupted while polling.
- User leaves during processing and resumes from stored `job_id`.

The happy path should remain one-handed and linear.
