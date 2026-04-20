# Weekly Things Design Review (v2 — full 7-dimension pass)

Date: 2026-04-19
Skill: /plan-design-review
Branch: week_function

## Feature

Add `重新理一理` regeneration button, stale visual hint, regen loading/disabled states,
and remove daily share card. Builds on the existing weekly-detail page (designed in v1 review).

## Rating Before Review: 5/10 → After: 8/10

The existing weekly-detail layout was already solid. The 4 new interaction moments
(regen button, stale hint, loading state, disabled state) were unspecified in the plan.

## Final Decisions

### `重新理一理` button
- Position: `.bottom-actions`, between `发给屋里人看看` and `再讲一段`
- Condition: `wx:if="{{summary.stale}}"`
- Style: `.secondary-action` class (white bg, border, red-dark text)
- Loading: button-level only — `loading="true"` + copy `正在重新理`; rest of page stays visible
- Disabled: when `summary.regen_count >= 5` or after 429; copy `今礼拜理好几次了`; `.secondary-action[disabled]`

### Stale hint
- `<text wx:if="{{summary.stale}}" class="muted">讲过新的以后，可以重新理一理</text>`
- Below `{{summary.date_range}}`, before opening-note
- 34rpx, `--color-muted`; makes regen button discoverable before scrolling

### Regen count persistence
- Backend adds `regen_count: int` to `WeeklySummaryResponse`
- Count = `COUNT(*) WHERE user_id=X AND week_start=Y AND audit_type="miniapp_weekly"` (stale+fresh)
- Frontend disables button when `summary.regen_count >= 5`

### CSS additions (`weekly-detail.wxss`)
```css
.secondary-action[disabled] {
  color: #5F6673;
  opacity: 0.6;
  border-color: #E7D7D2;
}
.bottom-actions {
  padding-bottom: calc(32rpx + env(safe-area-inset-bottom, 0));
}
```

### LLM output
- Strip `*`, `_`, `#` from `opening` on backend before storing

### Daily share card
- Remove `<view class="share-area">` block from `day.wxml` (line 130–132)
- Remove `prepareShare()` from `day.ts`

## Dimension Ratings

| Dimension | Before | After |
|---|---|---|
| Information Architecture | 6/10 | 9/10 |
| Interaction State Coverage | 4/10 | 9/10 |
| User Journey | 7/10 | 9/10 |
| AI Slop Risk | 7/10 | 8/10 |
| Design System Alignment | 7/10 | 9/10 |
| Responsive / Accessibility | 6/10 | 9/10 |
| Unresolved Decisions | 3/10 | 9/10 |

## Risks

- Kimi may return opening text > 50 chars; the `opening-note` panel expands gracefully but sanitize markdown
- Stale hint is muted/small — if user is visually impaired, they may still miss it; acceptable given scope
- Three-button bottom-actions area on small phones (320px) — test on iPhone SE

## Implementation Constraints

- Never show full-page loading during regen — only button-level
- `regen_count` must be populated on BOTH GET and POST responses
- Disabled button copy must change (`今礼拜理好几次了`), not just grey — DESIGN.md: "don't rely on color alone for state"
- `重新理一理` must use `.secondary-action`, not a custom style
- `.bottom-actions` needs `padding-bottom` safe area or bottom button is cut off on iPhone
