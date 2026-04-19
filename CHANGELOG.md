# Changelog

All notable changes to this project are documented in this file.

## [0.1.0.0] - 2026-04-19

### Added

- 今日页现在可以切换日期、打开日期选择器，并回到今天。
- 录音会归到开始录音时选中的日期，切换页面状态不会把内容放错天。

### Fixed

- 快速切换日期时，旧请求返回不会覆盖当前日期的内容。
- 分享卡生成会确认仍匹配当前日期，避免慢请求写入过期分享信息。
