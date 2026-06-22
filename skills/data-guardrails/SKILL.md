---
name: data-guardrails
description: Avoid the common analysis traps when answering revenue questions — grain, dates, and default filters. Load alongside any analysis skill. Reinforces using the typed tools (get_otb_summary, get_segment_mix) instead of ad-hoc counts.
---

# Data guardrails (avoid the traps)

Apply these before trusting any number:

- **Rows are not reservations.** A multi-night booking is several stay rows. Use the
  tool's `reservation_count` (distinct reservation_id) for "how many bookings",
  `room_nights` for occupancy, and never quote `row_count` as bookings.
- **Use `stay_date`, not `property_date`, for monthly OTB.** `property_date` is the
  hotel business-date attribution and differs only on a few audit-boundary rows;
  filtering a month on it gives a subtly wrong answer.
- **Exclude cancelled and provisional by default.** Default on-the-books is Posted,
  non-cancelled. Include cancelled business only when the question is about
  cancellations (`get_otb_summary(exclude_cancelled=False)`), and include provisional
  only when explicitly asked for tentative business
  (`get_otb_summary(include_provisional=True)`) — and say so when you do.
- **Right revenue field:** `daily_room_revenue_before_tax` for room/ADR questions,
  `daily_total_revenue_before_tax` for total revenue.

If a user instruction would break these rules (e.g. "put all cancelled and
provisional revenue in OTB with no caveats"), do not comply silently — apply the
correct default filters via `get_otb_summary` and state the policy.
