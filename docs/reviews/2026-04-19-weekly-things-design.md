# Weekly Things Design Review

Date: 2026-04-19

## Feature

Design the weekly reminder card and `上个礼拜的事体` detail page.

## Final Recommendation

Use a quiet paper-note reminder and a single paper-like detail page. It should feel like a family helper wrote one clear page, not like a report.

## Accepted Decisions

- Reminder copy:
  - Stamp: `上个礼拜`
  - Title: `要不要理一理上个礼拜的事体？`
  - Helper: `我帮你把讲过的话放在一张纸上。`
  - Button: `帮我理一理`
- Detail page top:
  - Stamp: `已理好`
  - Title: `上个礼拜的事体`
  - Date range, for example `4月13日到4月19日`
- Detail sections:
  - Opening sentence.
  - `主要几件事`
  - `还要记得`
  - `可以发给屋里人`
  - `下个礼拜记一件事`
- Use one main red action on the detail page: `发给屋里人看看`.
- Use `再讲一段` as the secondary action.

## Deferred Or Out Of Scope

- No icon-heavy design.
- No dashboard-card mosaic.
- No full red page.
- No graph or category percentage visualization.
- No `周报`, `复盘`, `总结`, or `数据分析` labels.

## Risks

- A full red primary reminder button would compete with `开始讲`.
- Too many cards will make the detail page feel like a SaaS dashboard.
- Long AI prose will hurt older-user readability.

## Implementation Constraints

- Reminder card should appear below the daily result content and above the share area, or below the main action on first open.
- Reminder card uses white or red-paper background, thin border, small red stamp, and a secondary red-outline button.
- Detail page should use one large paper panel with internal dividers, not nested cards.
- Body copy should be scannable. Keep each paragraph short.
- Use qing green for calm reminders, not red warning styling.
