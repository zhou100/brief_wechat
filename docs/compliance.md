# WeChat Compliance Checklist

## Personal Information

Brief collects user-submitted audio and derived text. State this plainly:

- Audio recording.
- Transcript.
- Structured summary.
- Key points.
- Open loops.
- WeChat account identifier.

Use purpose-limited language: the data is used to generate records and summaries. Avoid words such as "监听" or "监控".

## User Rights

The Mini Program must provide deletion for each entry. Deletion should remove or invalidate:

- Audio file.
- Transcript.
- Structured result.
- Related share card.
- Related job output where applicable.

## Legal Domains

Configure these separately in the WeChat Mini Program admin console:

- `request` domain for `/miniapp/*` JSON APIs.
- `uploadFile` domain only if using a custom backend upload path. The CloudBase-native path uses `wx.cloud.uploadFile`.
- `downloadFile` domain for generated share-card images if used.
- `socket` domain only if realtime status is added later.

## Permissions

Current explicit permission:

- `scope.record`: record user-submitted voice input.

Avoid extra permissions in the first version.

## Sharing

Only share summary cards:

- One-sentence summary.
- Open-loop count.
- Optional generated image.

Do not share:

- Full transcript.
- Complete long report.
- Original audio.
- Private key points unless the backend explicitly approves the format later.

## Launch Readiness

- Replace `touristappid` in `project.config.json`.
- Replace `API_BASE_URL` in `miniprogram/env.ts`.
- Add backend `/miniapp/*` routes.
- Verify real-device recording and upload.
- Verify job polling can resume after app background/foreground.
- Verify delete and regenerate.
- Verify share landing page is read-only.
- Complete the WeChat privacy protection guide.
