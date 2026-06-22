# Metric definitions

The tool layer enforces these rules in code, so the agent never has to recover them from raw SQL.

## Stay rows, reservations, room nights

A stay row is one row per `(reservation_id, stay_date)`, so a 3-night booking is 3 rows; `row_count` counts stay rows, not bookings. A reservation is `count(distinct reservation_id)` over the filtered rows, so a multi-night, multi-room booking still counts once. Room nights are `sum(number_of_spaces)`, where `number_of_spaces` is the rooms held that night: 1 room for 3 nights is 3, 2 rooms for 3 nights is 6. Room nights are therefore always at least the reservation count.

## Default OTB filters

The default universe is the view `vw_stay_night_base`: `financial_status = 'Posted'` and `reservation_status <> 'Cancelled'`. Cancelled business counts only when a question is about cancellations (`get_otb_summary(exclude_cancelled=False)`), and provisional (tentative) business counts only when explicitly asked for (`get_otb_summary(include_provisional=True)`). Months filter on `stay_date`, not `property_date`; the two differ only on a few audit-boundary rows. The dataset regenerates daily from a forward-looking anchor date, so counts depend on the anchor and reconcile against `/verify` on the scrape day. Use `daily_room_revenue_before_tax` for room and ADR figures, `daily_total_revenue_before_tax` for total revenue; room revenue is never above total.

## Pickup window (Europe/London vs UTC)

`get_pickup_delta` bounds the booking window on `create_datetime`, from London-local midnight `booking_window_days` ago up to now. The lower bound is computed in Europe/London and compared in UTC, because `create_datetime` is stored in UTC. The window is on the booking date, never the stay date; stays are also filtered to `stay_date >= future_stay_from`.

## Effective macro group

A segment's macro group is effective as of the stay date. `vw_segment_stay_night` joins `market_macro_group_history` on `stay_date` between `valid_from` and `valid_to` instead of reading the static `market_code_lookup.macro_group`. So when a market is reclassified mid-year, the same `market_code` rolls up to whichever macro group applied on the night in question.
