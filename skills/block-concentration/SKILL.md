---
name: block-concentration
description: Judge group/block business and large-account concentration risk for a stay month, with thresholds and recommended actions. Use for "how much group business", "are we concentrated in a few bookings". Calls get_block_vs_transient_mix.
---

# Block / concentration judgment

Call `get_block_vs_transient_mix(stay_month)`. Read `block_share_of_revenue` and
`top3_company_revenue_share`.

Judgment thresholds:
- **`block_share_of_revenue` above 40%** — the month leans heavily on group
  business. Group is good base demand but carries wash risk (cut-off, attrition,
  cancellation) and can displace higher-rated transient on peak dates.
- **`top3_company_revenue_share` above 30%** — concentration risk: a few accounts
  drive the month, so one cancellation swings it materially.

When either threshold trips, recommend concrete actions: (1) review the block
cut-off and attrition dates and hold the company to contracted pickup; (2) protect
transient inventory — cap group rooms on high-demand arrival dates so you do not
displace rate-rich transient; (3) diversify the account base for future periods.
Name the top companies and their revenue, quantify the block share, and end with the
action. If group is a healthy 20–30% with no single dominant account, say so and
hold course.

Cross-check pace before acting. High block share only displaces revenue when
transient is actually picking up on the same arrival dates — read `get_pickup_delta`
for the block's peak nights. If transient demand is strong there, protect it and cap
group; if transient is soft, the group is welcome base and you should hold it, not
cut it.
