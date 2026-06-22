---
name: segment-mix
description: Break a stay month down by market segment and macro group to explain what is driving it. Use for "what's driving July", "what share is corporate", segment composition. Calls get_segment_mix; route this work to the segment subagent.
---

# Segment mix analysis

Delegate segment/mix work to the focused segment subagent, which calls
`get_segment_mix(stay_month)` (optionally filtered by `macro_group`).

To explain "what is driving" a month:
- Rank segments by `share_of_revenue`; name the top 2-3 and their revenue.
- Contrast revenue share with room-night share — a segment with high revenue but
  low room-night share is rate-rich (protect it); the reverse is volume that may be
  diluting ADR.
- Use the **effective** macro group (stay-date-effective), not a static label — a
  market like `PROM` can reclassify mid-year.

Give the GM the mix, the one or two segments actually moving the month, and whether
the shift is healthy (rate-rich demand) or a risk (low-rate volume). Hand off to
`ota-dependency` or `block-concentration` if one segment or account looks dominant.
