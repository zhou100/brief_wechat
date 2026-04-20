# Weekly Things CEO Review

Date: 2026-04-19

## Feature

Add a soft weekly reminder and detail page for `上个礼拜的事体`.

## Final Recommendation

Build it as a small selective expansion, not as a `周报` feature.

The product value is not "weekly reporting." The value is: the user spoke many small things during the week, and the app can turn those scattered spoken notes into one simple paper-like summary that can be read or sent to family.

## Accepted Decisions

- Use the phrase `要不要理一理上个礼拜的事体？`.
- Do not add a persistent week tab.
- Show the reminder only when the prior week has enough completed entries.
- Generate the weekly detail only after the user taps `帮我理一理`.
- The detail page is titled `上个礼拜的事体`.
- The primary action on the detail page is `发给屋里人看看`.

## Deferred Or Out Of Scope

- No dashboards.
- No charts.
- No weekly tab.
- No multi-week archive.
- No automatic push notifications.
- No trend analysis.
- No direct display of time-coach language such as `uncomfortable_truth`.

## Risks

- If the reminder becomes persistent or loud, it will feel like a productivity app instead of a family helper.
- If the page shows charts or ratios, it will regress toward `time_logger_game`.
- If generated automatically on page load, it can slow down the main loop and create LLM cost spikes.

## Implementation Constraints

- Treat this as a secondary invitation, never the main page action.
- Keep the core loop `开始讲 -> 整理 -> 发给家人` visually dominant.
- Use a miniapp BFF contract instead of exposing legacy `/api/v1/entries/audit/weekly` directly.
- Save a local seen/dismissed state per user and week so the reminder does not nag.
