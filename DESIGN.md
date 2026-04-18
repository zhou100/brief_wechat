# 讲过就清爽 Design System

## Product Position

`讲过就清爽` is a WeChat Mini Program for Wu-speaking and dialect-speaking older adults.

The promise is simple:

> 讲一段，它帮你理清爽。

This is not a productivity dashboard. It is not a mobile SaaS app. It is a warm, clear, large-button voice notebook that helps someone speak in their own words and get back a tidy summary.

The product should feel like:

- A red paper note that has been neatly written for you.
- A family helper that understands dialect.
- A simple tool you can trust after one tap.

The product should not feel like:

- An AI demo.
- A work app.
- A financial, medical, or government service.
- A noisy promotion page.
- A young person's English productivity tool.

## Audience

Primary users:

- Older adults who are comfortable with WeChat.
- Users who speak Wu Chinese, Mandarin with local accent, or dialect-mixed speech.
- Users who may not read small text comfortably.
- Users who prefer direct instructions over abstract labels.

Secondary users:

- Adult children who help parents set up the Mini Program.
- Family members receiving shared summaries later.

## Design Principles

### 1. One Page, One Main Action

Every screen should have one obvious red action.

Examples:

- `开始讲`
- `讲好了，帮我整理`
- `再讲一遍`
- `看看整理结果`

Do not show multiple equal-weight actions. Secondary actions should be pale, smaller, and clearly less important.

### 2. Big Enough To Trust

Old users should not have to aim.

Minimum practical sizes:

- Main button height: `112rpx` to `128rpx`
- Main button font: `40rpx` to `44rpx`
- Body text: `34rpx` to `38rpx`
- Section title: `36rpx` to `42rpx`
- Small helper text: never below `30rpx`

Avoid thin gray text. If text matters, make it readable.

### 3. Speak Human, Not System

Never show technical state names to users.

Use:

- `正在听懂你讲的话`
- `正在帮你理清爽`
- `整理好了`
- `这段没听清，再讲一遍`

Avoid:

- `transcribing`
- `failed`
- `job`
- `open loops`
- `summary`
- `key points`

### 4. Warm Red, Not Alarm Red

Red is the brand color, but it should feel warm and familiar, not dangerous.

Use red for:

- Main action buttons
- Small stamp marks
- Important section headers
- Friendly completion states

Do not make the entire app red. Use white and soft warm backgrounds so the red action has power.

### 5. Chinese Elements, Lightly

Use Chinese visual cues as accents, not costume.

Good:

- Small red stamp: `已整理`
- Red paper note feeling
- Soft gold divider
- Subtle knot or cloud motif as a small icon
- Rounded rectangular panels like paper slips

Avoid:

- Dragon and phoenix decoration
- Heavy gold gradients
- Festival posters
- Dense patterns
- Anything that looks like a health supplement ad

### 6. Dialect Is The Superpower

The interface should make dialect feel accepted.

Good copy:

- `普通话、吴语、带口音都可以讲`
- `不用想格式，直接讲`
- `讲过就清爽`

Avoid copy that implies surveillance:

- `监听`
- `监控`
- `追踪`

Use `录音`, `讲`, `整理`.

## Visual Language

### Brand Name

Primary name:

```text
讲过就清爽
```

Short name for compact UI:

```text
清爽
```

Optional descriptor:

```text
方言小记
```

Recommended header usage:

```text
讲过就清爽
方言小记
```

### Color Tokens

Use these as the default design tokens.

```css
--color-red: #E11D2E;
--color-red-dark: #B91C1C;
--color-red-soft: #FFF1F2;
--color-red-paper: #FFF6F3;
--color-gold: #F5C542;
--color-ink: #161616;
--color-text: #2A2A2A;
--color-muted: #5F6673;
--color-border: #E7D7D2;
--color-panel: #FFFFFF;
--color-success: #168A4A;
--color-background: #FFF8F5;
```

Rules:

- Main CTA uses `--color-red`.
- Pressed CTA uses `--color-red-dark`.
- Page background uses `--color-background`.
- Panels use white or `--color-red-paper`.
- Gold is only an accent. Never use it for large areas.

### Typography

System font is acceptable. Prioritize legibility.

Recommended Mini Program font stack:

```css
font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
```

Sizes:

```css
--font-title: 48rpx;
--font-section: 38rpx;
--font-body: 34rpx;
--font-helper: 30rpx;
--font-button: 42rpx;
--font-timer: 88rpx;
```

Weights:

- Titles: `700`
- Buttons: `700`
- Body: `400` or `500`
- Avoid very thin weights.

### Shape

Keep shapes friendly and simple.

```css
--radius-small: 8rpx;
--radius-medium: 16rpx;
--radius-large: 24rpx;
```

Buttons may use `16rpx` to `24rpx`. Repeated cards should use `16rpx`. Avoid pill buttons for every element; reserve roundness for major touch targets.

### Spacing

Older users benefit from breathing room.

```css
--space-xs: 12rpx;
--space-sm: 20rpx;
--space-md: 32rpx;
--space-lg: 48rpx;
--space-xl: 72rpx;
```

Use fewer components with more spacing.

## Component Rules

### Main Button

Purpose: the one thing the user should do next.

Style:

```css
height: 120rpx;
border-radius: 20rpx;
background: #E11D2E;
color: #FFFFFF;
font-size: 42rpx;
font-weight: 700;
```

Copy examples:

- `开始讲`
- `讲好了，帮我整理`
- `再讲一遍`
- `保存这条`

### Secondary Button

Purpose: safe fallback.

Style:

```css
height: 96rpx;
border-radius: 16rpx;
background: #FFFFFF;
border: 2rpx solid #E7D7D2;
color: #B91C1C;
font-size: 36rpx;
font-weight: 600;
```

Copy examples:

- `先离开，等会儿看`
- `删除这条`
- `重新整理`

### Paper Panel

Purpose: show one piece of organized content.

Style:

```css
background: #FFFFFF;
border: 2rpx solid #E7D7D2;
border-radius: 20rpx;
padding: 32rpx;
```

Use panels for:

- Result sections
- History items
- Error recovery

Do not nest cards inside cards.

### Red Stamp

Purpose: completion and reassurance.

Visual:

```text
已整理
```

Small, red border, slightly stamp-like. Use sparingly.

## Screen Direction

### Home

Job: get the user to start speaking.

Recommended copy:

```text
讲过就清爽
有事就讲两句，我帮你理清楚。
```

Primary action:

```text
开始讲
```

Helper:

```text
普通话、吴语、带口音都可以。
```

Avoid feature explanations. Do not teach the whole product on the home screen.

### Record

Job: make recording feel safe.

Idle:

```text
准备好了
点一下开始讲
```

Recording:

```text
正在听你讲
00:06
```

Stop CTA:

```text
讲好了，帮我整理
```

Do not show waveform by default. Do not show format settings in product mode.

Default recording format:

```text
MP3, 16kHz, mono, 48kbps
```

### Processing

Job: reassure the user that work is happening.

States:

```text
正在听懂你讲的话
正在帮你理清爽
快好了
```

Failure:

```text
这段没听清
请再讲一遍
```

Debug errors may be visible in development, but product copy should stay human.

### Result

Job: make the output feel useful immediately.

Use Chinese section labels:

```text
一句话
重点
还没办完
```

Preferred layout:

```text
已整理

一句话
...

重点
1. ...
2. ...
3. ...

还没办完
...
```

Actions:

```text
发给家人
重新整理
删除这条
```

`发给家人` is warmer than `分享摘要卡片`.

### History

Job: find old notes without thinking.

Use large date groups:

```text
今天
昨天
4月18日
```

Each row shows:

- One sentence summary
- Time
- Open loop count, if any

Do not add filters until there is enough usage to justify them.

## Content Rules

### Preferred Terms

Use:

- `讲`
- `整理`
- `清爽`
- `一句话`
- `重点`
- `还没办完`
- `家人`
- `删除这条`
- `再讲一遍`

Avoid:

- `Summary`
- `Key points`
- `Open loops`
- `AI pipeline`
- `任务失败`
- `转写失败`
- `job`
- `监听`
- `监控`

### Error Copy

Technical:

```text
xfyun_transcription_failed
```

User-facing:

```text
这段没听清，请再讲一遍。
```

Technical:

```text
Request failed: 401
```

User-facing:

```text
登录过期了，请再试一次。
```

Technical:

```text
audio_convert_failed
```

User-facing:

```text
这段录音格式不太对，请重新录一段。
```

## Accessibility Rules

- No body text below `30rpx`.
- No primary touch target below `96rpx` height.
- Do not rely on color alone for state.
- Keep contrast high.
- Avoid dense paragraphs.
- Avoid English in primary UI.
- Keep destructive actions visually separate from primary actions.

## Product Boundaries

P0:

- Record
- Upload
- Process
- Show result
- History
- Delete

P1:

- Send summary to family
- Weekly view
- Better result card

Not now:

- Realtime transcript
- Complex editing
- Charts
- Full web dashboard replication
- Prompt customization
- Public social feed

## Implementation Notes

Current stable recording format:

```ts
{
  format: "mp3",
  sampleRate: 16000,
  encodeBitRate: 48000,
}
```

Keep test presets in code behind a debug flag, but product UI should not expose them.

The backend now runs in a China-friendly pipeline:

```text
CloudBase storage
-> backend ffmpeg conversion
-> iFlytek Spark SLM IAT
-> Moonshot Kimi
```

This lets the product lean into dialect support instead of pretending it is a generic AI recorder.

