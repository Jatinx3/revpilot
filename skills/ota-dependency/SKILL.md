---
name: ota-dependency
description: Judge OTA channel dependency and commission risk for a stay month, with thresholds and recommended actions. Use for "are we too dependent on OTA". Calls get_segment_mix.
---

# OTA dependency judgment

Call `get_segment_mix(stay_month)` and read the OTA segment's `share_of_revenue`.

Judgment thresholds (share of revenue):
- **Below 25%** — healthy. OTA is doing useful need-period filling; no action.
- **25%–35%** — watch. Note it and protect direct channels.
- **Above 35%** — over-dependent. The hotel is paying ~15–20% commission on more
  than a third of revenue and is exposed to OTA rate-parity and ranking changes.

When OTA `share_of_revenue` is above 35%, recommend concrete actions: (1) shift
demand to direct — push brand.com, loyalty and metasearch; (2) tighten OTA
allocation and close OTA on high-demand/compression dates where direct will fill;
(3) protect BAR parity so OTAs are not undercutting the direct rate. Always quantify
the OTA revenue figure and its share, compare against the healthy band, and end with
the single highest-value action — never report the share in isolation.

Cross-check cancellations. OTA business cancels more than direct, so a high OTA share
and an elevated cancellation rate (see cancellation-watch) compound: the book is
softer than gross OTB suggests. When both are high, weight the recommendation toward
non-refundable or deposit OTA rates before chasing more OTA volume.
