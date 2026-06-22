---
name: otb-summary
description: Report on-the-books revenue and rooms for a stay month. Use for "what revenue is on the books", monthly totals, room nights and ADR. Calls get_otb_summary.
---

# On-the-books summary

Call `get_otb_summary(stay_month)` for the month in question. Default universe is
Posted, non-cancelled business.

Present, in GM language:
- **Total revenue** (use `total_revenue`) and **room revenue** (`room_revenue`).
- **Room nights** (`room_nights`) and **reservation count** — never quote
  `row_count` as "bookings"; rows are stay-nights, reservations are distinct
  bookings.
- **Blended ADR** = `room_revenue / room_nights`.

Lead with the headline number, then one line on what it means for the month
(ahead/behind expectation). If the GM asks about cancellations explicitly, call
again with `exclude_cancelled=False` and report the delta. State the assumption
that provisional and cancelled business is excluded by default.
