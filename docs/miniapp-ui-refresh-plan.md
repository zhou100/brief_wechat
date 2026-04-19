# 讲过就清爽 Mini Program UI Refresh Plan

Date: 2026-04-18

## CEO Decision

The product direction is clear enough to implement.

Use **HOLD SCOPE + small SELECTIVE EXPANSION**:

- Hold the core loop: `start -> record -> upload -> process -> result -> send to family`.
- Expand only the human feeling: older-user readability, Wu/dialect acceptance, Jiangnan warmth, and family-sharing language.
- Do not expand into dashboards, editing, charts, weekly reports, or complex history yet.

The product is not "AI voice notes". It is:

```text
有事讲两句，我帮你理清爽。
```

## Product Goal

Turn the current working technical prototype into a clear, warm, large-button WeChat Mini Program for Wu-speaking and dialect-speaking older adults.

The next implementation should make the app feel like:

- One tap to speak.
- Safe while recording.
- Reassuring while processing.
- Useful immediately after the result appears.
- Natural to send to family.

## Primary Flow

```text
Home
  -> Record
    -> CloudBase upload
      -> Job polling
        -> Result
          -> Send to family / record another / delete
```

The backend pipeline is already working and should be reused:

```text
MP3 16k recording
  -> wx.cloud.uploadFile
  -> backend download
  -> ffmpeg PCM conversion
  -> iFlytek transcription
  -> Kimi summarization
```

## What Already Exists

| Area | Current State | Plan |
|------|---------------|------|
| Recording | `pages/record` records and uploads successfully with MP3 16k | Reuse, restyle, update copy |
| Upload | CloudBase-native upload works | Reuse |
| Job polling | `pages/job` stores active job and resumes from home | Reuse, improve copy and error states |
| Result | `pages/day` renders summary, key points, open loops | Reuse data binding, localize labels |
| Share | `open-type="share"` and share card API exist | Keep, rename user-facing action to `发给家人` |
| Delete | Delete entry and CloudBase file cleanup exist | Keep, restyle as secondary destructive action |
| Regenerate | Regeneration exists | Keep but demote visually |
| Design system | `DESIGN.md` defines tokens and principles | Implement in `app.wxss` |

## NOT In Scope

- Realtime transcription, because it adds latency and state complexity before the basic loop is polished.
- Complex editing, because the product promise is "speak and get clear", not document editing.
- Charts or analytics, because this is not a productivity dashboard.
- Weekly reports, because result quality and repeat use should come first.
- Full web frontend parity, because the Mini Program is a lightweight input and sharing client.
- Public social sharing mechanics, because the natural first share target is family.
- Dialect picker, because the current promise is "普通话、吴语、带口音都可以", and extra setup hurts first use.

## Code Change Plan

### 1. Global Style Tokens

Files:

- `miniprogram/app.wxss`

Add shared design tokens and reusable classes from `DESIGN.md`:

```css
.page-shell
.primary-action
.secondary-action
.danger-action
.paper-panel
.section-title
.helper-text
.red-stamp
.qing-note
.bottom-actions
```

Requirements:

- Primary button height: `112rpx` to `128rpx`.
- Primary button copy size: around `42rpx`.
- Body text: `34rpx` minimum.
- Chinese line height: `1.45` to `1.65`.
- Page background: warm off-white, not blue-gray.
- Primary red balanced by neutral paper surfaces and a qing accent.
- Avoid nested cards.

### 2. Home Page

Files:

- `miniprogram/pages/index/index.wxml`
- `miniprogram/pages/index/index.wxss`
- `miniprogram/pages/index/index.ts`

Change the page from product explanation to a single start action.

Recommended copy:

```text
讲过就清爽
有事讲两句，我帮你理清爽。
普通话、吴语、带口音都可以。
```

Primary button:

```text
开始讲
```

Resume button:

```text
继续整理上次那段
```

Remove or hide the current explanatory panel about "极简闭环". It reads like product copy for builders, not for the actual user.

### 3. Record Page

Files:

- `miniprogram/pages/record/record.wxml`
- `miniprogram/pages/record/record.wxss`
- `miniprogram/pages/record/record.ts`

Keep the existing recorder and upload logic.

User-facing copy:

```text
准备好了
点一下开始讲
```

Recording state:

```text
正在听你讲
```

Stop button:

```text
讲好了，帮我整理
```

Upload state:

```text
正在送去整理
```

Failure:

```text
这段没传上去，请再试一次。
```

Implementation notes:

- Keep MP3 16k as the default.
- Keep debug recording presets hidden.
- Add light vibration on start and stop if supported by WeChat APIs.
- Do not show waveform or format controls in product mode.

### 4. Processing Page

Files:

- `miniprogram/pages/job/job.wxml`
- `miniprogram/pages/job/job.wxss`
- `miniprogram/pages/job/job.ts`

Replace technical job/status wording with human states.

State copy:

```text
正在听懂你讲的话
正在帮你理清爽
快好了
```

Failure copy:

```text
这段没听清
请再讲一遍
```

Network retry copy:

```text
网络有点慢，正在继续整理。
```

Rules:

- Do not show `failed`, `transcribe`, `job`, `xfyun`, or raw technical errors in product mode.
- Keep raw error details available only behind development/debug state if needed.
- Preserve active job storage and resume behavior.

### 5. Result Page

Files:

- `miniprogram/pages/day/day.wxml`
- `miniprogram/pages/day/day.wxss`
- `miniprogram/pages/day/day.ts`

Replace English section labels.

Use:

```text
一句话
重点
还没办完
```

Empty open loops copy:

```text
这段讲完了，没留下要办的事。
```

Actions:

```text
发给家人
再讲一段
重新整理
删除这条
```

Priority:

1. `发给家人`
2. `再讲一段`
3. `重新整理`
4. `删除这条`

`重新整理` and `删除这条` should be visually demoted. Delete should not sit beside the primary action.

### 6. User-Facing Error Mapping

Files:

- `miniprogram/pages/record/record.ts`
- `miniprogram/pages/job/job.ts`
- Optional helper: `miniprogram/utils/errors.ts`

Create or consolidate a small user-facing error mapper.

Examples:

| Technical Error | User Copy |
|-----------------|-----------|
| `Request failed: 401` | `登录过期了，请再试一次。` |
| `xfyun_transcription_failed` | `这段没听清，请再讲一遍。` |
| `audio_convert_failed` | `这段录音格式不太对，请重新录一段。` |
| upload timeout | `网络有点慢，请重试上传。` |

Do not expose vendor names to normal users.

## State Machine

```text
idle
  -> recording
    -> uploading
      -> processing
        -> done
        -> failed
  -> upload_failed
```

Resume behavior:

```text
processing + user leaves
  -> store brief_active_job_id
  -> home shows resume CTA
  -> job page resumes polling
```

## Failure Modes

| Codepath | Failure | Handling Needed | Test Needed |
|----------|---------|-----------------|-------------|
| `ensureLogin` before recording | token expired or backend 401 | Show `登录过期了，请再试一次。` | Manual devtools + real device |
| Recorder start | permission denied | Show permission guidance, keep user on record page | Manual real device |
| Stop recording | temp file missing | Show `这段没录上，请再讲一遍。` | Manual devtools |
| CloudBase upload | invalid host / network timeout | Show retry button and preserve temp file | Manual real device |
| Job polling | network interruption | Keep polling, show calm retry text | Manual devtools throttling |
| Job failed | transcription or summarization failed | Show human retry state, no raw vendor error | Manual by forcing failed job |
| Result empty | summary fields missing | Show friendly empty copy, no blank panel | Mock API or backend fixture |
| Share card generation | card API fails | Share fallback to home or entry, show no scary error | Manual devtools share |

Critical gap to avoid:

- A failed job that only says `failed` or exposes `xfyun_error_*` to an older user.

## Test Plan

Run:

```bash
npm run build
```

Manual WeChat DevTools:

1. Launch home page.
2. Start recording.
3. Stop and upload.
4. Verify processing copy.
5. Verify result labels are Chinese.
6. Leave processing page, return home, resume active job.
7. Delete result.

Real iOS device:

1. Record 5-10 seconds using default MP3 16k.
2. Confirm upload succeeds.
3. Confirm transcription and Kimi summary succeed.
4. Confirm `发给家人` opens WeChat share.
5. Confirm no English labels or raw technical errors appear in the happy path.

Visual QA:

- Buttons are big enough for older users.
- Text does not overflow on narrow iPhone screens.
- Primary action is visible without hunting.
- Delete is visually separated from primary actions.
- Result page does not feel like an English SaaS app.

## Dependency Table

| Step | Modules Touched | Depends On |
|------|-----------------|------------|
| Global tokens | `miniprogram/app.wxss` | `DESIGN.md` |
| Home refresh | `miniprogram/pages/index` | Global tokens |
| Record refresh | `miniprogram/pages/record`, optional `miniprogram/utils` | Global tokens |
| Processing refresh | `miniprogram/pages/job`, optional `miniprogram/utils` | Global tokens |
| Result refresh | `miniprogram/pages/day`, optional `miniprogram/utils` | Global tokens |
| Build/manual QA | whole Mini Program | page refreshes |

## Parallelization

Sequential implementation is preferred for the first pass because all pages should share the same global tokens and copy rules.

Possible split after global tokens land:

- Lane A: Home + Record
- Lane B: Processing + Result

Conflict risk:

- Both lanes may touch shared error-copy helpers if created. Keep helper changes in one lane or do them before splitting.

## Acceptance Criteria

- The four core pages match `DESIGN.md`.
- No primary UI labels use English terms like `Summary`, `Key points`, `Open loops`, `failed`, or `job`.
- Default recording remains MP3 16k.
- Existing backend/API flow is unchanged.
- Active job resume still works.
- Upload retry still works.
- Result delete still works.
- Share action is presented as `发给家人`.
- `npm run build` succeeds.

## Implementation Order

1. Add global tokens and reusable classes.
2. Refresh home page.
3. Refresh record page.
4. Refresh processing page.
5. Refresh result page.
6. Consolidate user-facing errors if duplication becomes messy.
7. Run build.
8. Manual WeChat DevTools pass.
9. Real iOS device pass.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | CLEAR | Hold core loop, expand only human tone and family sharing |
| Eng Review | `/plan-eng-review` | Architecture & tests | 1 | CLEAR | No backend changes needed, frontend refactor has clear state and test plan |
| Design Review | `/design-consultation` | Design source of truth | 1 | CLEAR | `DESIGN.md` defines Wu/Jiangnan tone, large-button UI, copy rules |

VERDICT: CEO + ENG + DESIGN CLEARED. Ready to implement the Mini Program UI refresh.
