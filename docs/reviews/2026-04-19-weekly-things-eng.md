# Weekly Things Engineering Review

Date: 2026-04-19

## Feature

Engineering plan for a hidden weekly reminder and `上个礼拜的事体` detail page.

## Final Recommendation

Implement lightweight eligibility detection and user-triggered generation.

The homepage or daily page must not auto-generate weekly content. It should only ask the backend whether a reminder is eligible. The expensive weekly LLM path runs only after the user taps `帮我理一理`.

## Accepted Decisions

- Add miniapp BFF endpoints for weekly summary behavior.
- Keep the Mini Program inside `/miniapp/*`; do not call legacy `/api/v1/entries/audit/weekly` directly from the client.
- Add a lightweight suggestion endpoint that returns whether to show the reminder.
- Pass an explicit `week_start` for "上个礼拜" to avoid UTC/local-week confusion.
- Store seen/dismissed state locally per user and week.
- The weekly detail page consumes a miniapp-friendly schema, not the old coach-letter schema.

## Deferred Or Out Of Scope

- No background generation.
- No notification scheduling.
- No global weekly archive.
- No automatic sharing.
- No sharing of full transcript, raw audio, or complete private details.

## Risks And Edge Cases

- Week boundary bugs on Monday morning if backend guesses the week using UTC.
- 204 or empty cached responses can crash frontend code if treated as an object.
- LLM failures must not break the daily recording page.
- Dismissed reminders must not come back repeatedly in the same week.
- Newly added entries should invalidate stale weekly cache for the affected week.
- Share text must be short and privacy-safe.

## Implementation Constraints

- Suggested endpoints:
  - `GET /miniapp/weekly/suggestion?week_start=YYYY-MM-DD`
  - `GET /miniapp/weekly/{week_start}`
  - `POST /miniapp/weekly`
- First version may compute weekly text deterministically from completed entries and classifications rather than reusing the old time-coach letter directly.
- If generation fails, show gentle copy such as `不急，等会儿再理`.
- Tests must cover fewer than 3 entries, 3+ prior-week entries, cached retrieval, and local-week date range behavior.
