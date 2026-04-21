# TODOS

Use this file for deferred work that should survive across sessions. Group items by component, keep priority explicit, and move shipped work to Completed.

## Miniapp

### Realtime Dictation Preview

**Priority:** P3

**What:** Explore live dictation during recording, so text appears while the user is still speaking.

**Why:** iFlytek's WebSocket IAT and RTASR APIs support streaming recognition, and WeChat `RecorderManager.onFrameRecorded` can provide audio chunks when `frameSize` is configured. This could make long recordings feel even more alive after the current "record first, tidy later" flow has shipped and stabilized.

**Pros:** Gives immediate confidence that speech is being captured; could reduce anxiety during long notes; makes the product feel more magical for users who talk for 1+ minutes.

**Cons:** Adds a much more complex realtime path: miniapp audio chunk streaming, backend WebSocket relay, partial-result correction, reconnect behavior, WebSocket domain setup, and real-device QA. Streaming ASR can revise earlier text, so UI must handle text replacement without looking broken.

**Effort:** L -> with CC+gstack: ~1-2 hours for a prototype, longer for production polish and real-device hardening.

**Depends on:** Ship the current faster flow first: record -> quick transcript -> optional "一键理清爽". Revisit only after measuring whether users still complain about waiting or uncertainty during long recordings.

---

### Multi-Week Weekly Browsing

**Priority:** P3

**What:** Add a "previous weeks" view to the history page (`pkg_history`) showing past weekly summaries (cached `AuditResult` rows with `audit_type="miniapp_weekly"`).

**Why:** Users can currently only access the most recent week's summary via the day-page banner. Past weeks are invisible even if they were generated and cached.

**Pros:** Closes the "memory" loop — users can look back months later. Reuses existing `AuditResult` cache.

**Cons:** Requires a new history list endpoint, new UI section, and handling gaps (weeks with no summary).

**Effort:** M → with CC+gstack: ~30 min.

**Depends on:** Weekly feature (week_function branch) shipped first.

---

### Monday Push Reminder

**Priority:** P2

**What:** Send a WeChat service message on Monday morning when the prior week has ≥3 completed entries and no weekly summary has been generated yet.

**Why:** Without a push, users only see the weekly banner if they open the app on today's date. Most users will miss it entirely.

**Pros:** Dramatically increases weekly summary engagement; completes the "trigger → generate → share" loop.

**Cons:** Requires WeChat service message subscription (user must opt in via Mini Program); platform review process; backend cron scheduler.

**Effort:** L → with CC+gstack: ~1 hour.

**Depends on:** Weekly feature shipped; WeChat service message subscription registered.

## Backend

No open TODOs.

## Completed

### Weekly Things (上个礼拜的事体)

**Priority:** P1

**Completed:** v0.1.2.0 (2026-04-19)

今日页底部显示"上个礼拜"提示卡；新的周报详情页用 AI 整理主要事体、还要记得、可发家人文字；`重新理一理` 按钮支持最多 5 次；新增/修改/删除条目后周报自动标为过期；LLM 开场白生成含超时降级；今日页去掉分享卡片按钮。

---

### Miniapp Day Date Navigation

**Priority:** P1

**Completed:** v0.1.0.0 (2026-04-19)

今日页支持前后日期切换、原生日期选择器和回到今天；录音日期在开始录音时锁定，并防止慢请求覆盖当前日期内容。
