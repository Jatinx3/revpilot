---
name: pickup-pace
description: Judge booking pace and recent pickup for future stays from pickup velocity and on-the-books position, with thresholds and recommended rate/inventory actions. Use for "what changed in the last 7 days", booking pace, pickup. Calls get_pickup_delta and get_otb_summary.
---

# Pickup / pace judgment

Pace is judged from two things the tools give you directly: **how fast the book is
moving right now** (pickup velocity) and **where the month already stands** (OTB
position). The booking window is on `create_datetime`, never on stay date.

The primary tool is `get_pickup_delta`, and it answers a "what changed recently"
question on its own across all future stays — **no stay month is required**.
"Future stays" means stays from today onward, so default `future_stay_from` to
today's date (it is given to you in context) and "last N days" to
`booking_window_days = N`; never ask the user for these. Only use a different
`future_stay_from` if the user names a specific horizon (e.g. "for August stays").

**Always run two windows — the recent one (e.g. 7-day) and double it (14-day),
same `future_stay_from`.** Velocity is the comparison between them; a single window
is just a count. Never call pace "strong", "healthy", "soft", or "stalling" from one
window alone — that verdict comes from comparing the most recent week to the week
before it (see below).

Pull `get_otb_summary(stay_month)` only as optional context when the question is
about a specific month's position — never ask for a month just to answer a general
"what changed" question.

## Read the velocity (recent week vs the week before)

The 14-day window *contains* the 7-day one, so don't compare them directly — derive
the prior week. With `p7` = `new_room_nights` in the last 7 days and `p14` = the last
14 days: `recent = p7` and the **week before** = `p14 - p7`. Compare those two:

- **Accelerating** — `recent` is clearly larger than the prior week: most of the
  fortnight's pickup landed in the last 7 days. Demand is building.
- **Steady** — the two weeks are roughly equal.
- **Stalling** — `recent` is clearly smaller than the prior week: booking slowed this
  week relative to last. Demand is going quiet.

(Worked example: `p7 = 115`, `p14 = 120` → prior week = 5, so 115 this week vs 5 last
week is strongly **accelerating**, not stalling — even though 115 and 120 look close.)
State both numbers, e.g. "115 room nights this week vs 5 the week before".

Use `by_segment` from the 7-day window to say *which* segments are picking up or
have gone silent — pace is never uniform across segments.

## Recommend the lever

- **Accelerating** (especially if OTB is already healthy for the month): yield up —
  raise BAR, add a MinLOS on peak arrival dates, and close the deepest discount rate
  plans to protect ADR while demand is willing.
- **Stalling** with the month still far from where it needs to be: stimulate — open
  promotional rates, relax restrictions, and lean on OTA for the soft need-dates
  only (not the whole month).

Always quantify the recent room nights and revenue added (from `get_pickup_delta`),
state the recent-week-vs-prior-week comparison that justifies the verdict, name the segments doing
the work (`by_segment`), and say where the month stands (`get_otb_summary`, only if a
specific month is in scope). Finish with a concrete **rate or inventory** lever —
BAR move, MinLOS on named peak dates, open/close a specific discount plan — not soft
advice like "nurture relationships" or "monitor contribution".

## On "versus last year"

Pickup velocity answers *is demand building or fading right now*, which is what most
pace questions need. A precise **same-time-last-year** comparison — what the book
looked like at the same lead time a year ago — is a point-in-time rebuild via
`get_as_of_otb('<last-year month>', as_of=<one year ago>)`. That tool is gated
behind human approval (it is an expensive rebuild), so offer it as a follow-up when
the GM specifically wants STLY pace, rather than asserting a last-year delta the
velocity read does not establish.
