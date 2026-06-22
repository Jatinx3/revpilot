---
name: cancellation-watch
description: Judge cancellation exposure and on-the-books reliability for a stay month, with a threshold and recommended actions. Use for "how much business was cancelled", OTB reliability. Calls get_otb_summary and get_as_of_otb.
---

# Cancellation watch judgment

Call `get_otb_summary(stay_month, exclude_cancelled=True)` and again with
`exclude_cancelled=False`; the difference is the cancelled business. Express the
cancellation rate as cancelled reservations over total reservations for the month.

Judgment:
- **Cancellation rate above 15%** for a month is high — the on-the-books number is
  soft and may overstate what will actually materialise, especially if OTA-heavy.
- A rising rate in the recent booking window is an early warning even below 15%.

When the rate is above 15%, recommend actions: (1) review cancellation and deposit
policy — move high-risk segments (notably OTA) toward non-refundable or deposit
rates; (2) re-forecast the month on a net-of-expected-wash basis rather than gross
OTB; (3) hold a small transient allocation back to resell cancelled peak-date rooms.
For point-in-time reliability checks, use `get_as_of_otb` (human-approved) to see how
the book looked at a past date. Quantify the cancelled revenue and the rate, then
give the action.
