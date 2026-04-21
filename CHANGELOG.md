# Changelog

All notable changes to this project are documented in this file.

## [0.1.5.0] - 2026-04-21

### Added

- Voice notes now finish as soon as the original transcript is saved, then show an optional "一键理清爽" action for refinement and categorization.

### Changed

- The miniapp now presents raw transcripts first and keeps "理清爽" as a single explicit action, removing the old separate "重新分类" entry point.
- iFlytek transcription can send frames without real-time pacing, retry with the slower 40ms pacing if the provider rejects the fast stream, and process split audio segments concurrently.
- CloudBase deployment examples now include the new transcription pacing, segment concurrency, and on-demand tidy refinement settings.

### Fixed

- Days with both organized content and fresh untidied transcripts now open the transcript timeline first, so the text promised by the tidy panel is visible immediately.

## [0.1.4.0] - 2026-04-21

### Changed

- Longer voice notes are preprocessed before iFlytek transcription: long silence is trimmed and audio is split into API-safe segments before the text is stitched back together.
- CloudBase deployment docs now describe the iFlytek-only ASR setup and the tunable preprocessing settings.

### Removed

- Tencent ASR provider configuration and setup guidance have been removed from the backend and deployment docs.

## [0.1.3.3] - 2026-04-20

### Fixed

- Opening 今日清爽 at the start of a new day no longer shows a false "今天内容暂时打不开" toast before anything has been recorded.

## [0.1.3.2] - 2026-04-20

### Fixed

- The miniapp now waits longer for manual day reclassification, so a successful reclassification no longer shows a false failure toast just because the model response took more than 20 seconds.
- Example miniapp environment files now include the reclassification timeout setting, keeping copied configs buildable.

## [0.1.3.1] - 2026-04-20

### Fixed

- Fixed day reclassification in the miniapp by eager-loading job rows before filtering completed entries, avoiding async SQLAlchemy `MissingGreenlet` failures in production.
- Reclassification now returns a retryable service-unavailable response if the classifier backend fails, instead of leaking a generic internal server error.

## [0.1.3.0] - 2026-04-20

### Added

- 今日页可以手动“重新分类”，修好模型或提示词后，旧记录不用重新录音也能重新整理。

### Changed

- 分类和周报开场白默认改走 TokenHub，分类优先使用 `deepseek-v3.2`，忙或失败时自动切到混元。
- 分类提示词补充沪语和日常流水账示例，像买菜做饭、接小孩、运动、白相这些事会更稳定地归到对应分类。
- 讯飞转写等待时间放宽，较慢说话或停顿更久的录音不容易被提前截断。

### Fixed

- 分类服务失败、超时或模型过载时，不再把整段内容假装成“感悟”保存。

## [0.1.2.0] - 2026-04-19

### Added

- 今日页底部现在有"上个礼拜"提示卡，只要讲话够多就会出现，帮你回顾上周事体。
- 新的"上个礼拜的事体"页面，用 AI 整理出主要几件事、还要记得的事、以及可以发给家人的文字。
- `重新理一理` 按钮：生成好之后再讲了新内容，可以重新理一次（每周最多 5 次）。
- 后台 `stale` 机制：新增或修改条目后，周报自动标记为过期，显示"可以重新理一理"提示。
- LLM 生成的开场白：每次整理都会生成一句温暖的沪语风格的总结，超时会自动降级。

### Changed

- 今日页去掉了"发给家人"的分享卡片按钮，分享入口统一移到周报页。

## [0.1.1.0] - 2026-04-19

### Added

- 今日页现在可以在“按分类看”和“按讲话顺序看”之间切换。
- 讲话顺序视图会保留原始转写，方便校对和回想。

### Changed

- 分类页现在以“整理好了，已做的归档，还要做的单独放。”作为默认心智。
- 已做类会优先展示，并使用“办事体、照顾家人、休息”等更贴近方言小记的分类名。
- 分类提示词默认把当天流水账归为已发生记录，只有明确未来动作才归到“还要做”。

### Fixed

- 当有转写但没有分类卡片时，今日页会自动切到讲话顺序视图，不再显示空状态。

## [0.1.0.0] - 2026-04-19

### Added

- 今日页现在可以切换日期、打开日期选择器，并回到今天。
- 录音会归到开始录音时选中的日期，切换页面状态不会把内容放错天。

### Fixed

- 快速切换日期时，旧请求返回不会覆盖当前日期的内容。
- 分享卡生成会确认仍匹配当前日期，避免慢请求写入过期分享信息。
