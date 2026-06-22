---
name: pricing-adr
description: Judge ADR and rate positioning across segments and room classes, with thresholds and recommended rate actions. Use for "which room type has the highest ADR", rate dilution, discount mix. Calls get_otb_summary and get_segment_mix.
---

# Pricing / ADR judgment

Compute blended ADR from `get_otb_summary` (`room_revenue / room_nights`) and per
segment from `get_segment_mix` (`total_revenue / room_nights`). For ADR by room type
— e.g. "which room type has the highest ADR" — call
`get_otb_summary(stay_month, by_room_type=True)` and read the `room_types` list; it is
sorted by ADR descending, so `room_types[0]` is the highest-ADR room type. Compare
segments and room types.

Judgment:
- **A high-volume segment whose ADR sits more than 10% below the blended ADR** is
  diluting rate — typically OTA or promotional plans carrying the month on volume,
  not value.
- **Blended ADR below 120** on a high-demand month signals the rate ceiling is being
  left on the table or discounts are too open.

When dilution shows up, recommend rate actions: hold BAR and resist further
discounting on compression dates; close the deepest discount and promotional rate
plans where demand will fill at higher rates; protect the rate-rich segments and
steer volume to them via length-of-stay or advance-purchase fences. Always quantify
the ADR gap, name the diluting segment or room class, and finish with the specific
rate or restriction to change — not just the ADR number.

Cross-check demand before cutting. Rate dilution only costs you when the date would
fill at a higher rate, so confirm with pace (`get_pickup_delta`) first. Close the
discounted segment only where pickup shows demand will backfill at a higher rate; on
soft dates the discounted volume still beats the empty room, so keep it.
