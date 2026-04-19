# Miniapp API Contract

The Mini Program is a lightweight input and sharing client. It only talks to first-party `/miniapp/*` endpoints. The backend owns transcription, summarization, storage, deletion, and regeneration.

## Minimal User Flow

```text
wx.login -> /miniapp/auth/login
record audio
wx.cloud.uploadFile
wx.cloud.getTempFileURL
POST /miniapp/entries
GET /miniapp/jobs/{job_id}
GET /miniapp/daily/{date}
GET /miniapp/entries/{entry_id}/result
POST /miniapp/share/cards
```

## Auth

### `POST /miniapp/auth/login`

Request:

```json
{ "code": "wx.login temporary code" }
```

Response:

```json
{
  "token": "app session jwt",
  "user": {
    "id": "user id",
    "display_name": "optional"
  }
}
```

Server behavior:

- Exchange `code` server-side with WeChat.
- Store `openid`.
- Store `unionid` when available.
- Issue app-owned session/JWT.

## Upload

The first CloudBase-native version uploads audio directly from the Mini Program:

```ts
wx.cloud.uploadFile({ cloudPath, filePath })
wx.cloud.getTempFileURL({ fileList: [fileID] })
```

The backend receives the CloudBase `fileID` and a short-lived temp URL, then owns transcription, summarization, and database state. The older `/miniapp/uploads/create` and `/miniapp/uploads/audio` backend upload path remains as a fallback for non-CloudBase clients.

## Entries

### `POST /miniapp/entries`

Request:

```json
{
  "cloud_file_id": "cloud://env.bucket/raw_audio/2026-04-16/recording.mp3",
  "cloud_temp_url": "https://example.tcb.qcloud.la/temp-signed-audio-url",
  "duration_ms": 53000,
  "local_date": "2026-04-16",
  "client_meta": {
    "source": "wechat-miniapp",
    "recorder": "wx.getRecorderManager"
  }
}
```

Response:

```json
{
  "entry_id": "uuid",
  "job_id": "uuid"
}
```

Server behavior:

- Create entry.
- Enqueue transcription and AI summary job.
- Return immediately.

### `GET /miniapp/daily/{date}`

Returns the completed entries for one local calendar date.

Request path:

```text
/miniapp/daily/2026-04-19
```

Response:

```json
{
  "entry_id": "latest-entry-uuid",
  "date": "2026-04-19",
  "created_at": "2026-04-19T12:00:00Z",
  "summary": "One sentence daily summary.",
  "key_points": [
    "Point 1",
    "Point 2"
  ],
  "open_loops": [
    "Follow up on X"
  ],
  "entries": [
    {
      "id": "entry-uuid",
      "local_date": "2026-04-19",
      "created_at": "2026-04-19T12:00:00Z",
      "duration_seconds": 53,
      "categories": []
    }
  ],
  "category_groups": []
}
```

Rules:

- `date` is `YYYY-MM-DD` in the user's local calendar.
- Future dates should not be requested by the Mini Program.
- Empty days return a friendly empty daily result rather than a client crash.

### `GET /miniapp/entries/{entry_id}/result`

Response:

```json
{
  "entry_id": "uuid",
  "result_id": "uuid",
  "created_at": "2026-04-16T12:00:00Z",
  "summary": "One sentence summary.",
  "key_points": [
    "Point 1",
    "Point 2",
    "Point 3"
  ],
  "open_loops": [
    "Follow up on X"
  ]
}
```

Rules:

- `summary` is one sentence.
- `key_points` contains 3 to 5 items when enough content exists.
- `open_loops` contains unfinished decisions, tasks, questions, or follow-ups.
- Do not return full long reports in the Mini Program first path.

### `DELETE /miniapp/entries/{entry_id}`

Delete the user's audio, transcript, structured summary, share cards, and related job/output records where applicable.

### `POST /miniapp/entries/{entry_id}/regenerate`

Response:

```json
{
  "entry_id": "uuid",
  "job_id": "uuid"
}
```

Re-enqueue summarization for the same uploaded audio/transcript.

## Jobs

### `GET /miniapp/jobs/{job_id}`

Response:

```json
{
  "job_id": "uuid",
  "entry_id": "uuid",
  "status": "processing",
  "progress": 45,
  "step": "summarizing",
  "result_preview": {
    "summary": "Optional partial summary"
  }
}
```

Allowed `status` values:

- `queued`
- `processing`
- `done`
- `failed`

The client stores `job_id` locally so users can leave and resume polling later.

## Sharing

Sharing is growth-critical and must not expose the full report.

### `POST /miniapp/share/cards`

Request:

```json
{ "entry_id": "uuid" }
```

or:

```json
{ "date": "2026-04-19" }
```

Response:

```json
{
  "card": {
    "share_id": "public-read-token",
    "title": "我的 Brief 摘要",
    "summary": "One sentence summary.",
    "open_loop_count": 2,
    "image_url": "optional generated card image"
  }
}
```

### `GET /miniapp/share/cards/{share_id}`

Public read-only response:

```json
{
  "share_id": "public-read-token",
  "summary": "One sentence summary.",
  "open_loop_count": 2,
  "created_at": "2026-04-16T12:00:00Z"
}
```

The share landing page must invite the recipient to start recording. It must not expose the original audio, transcript, key points, or complete open loops.
