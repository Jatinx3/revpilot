# Data-site structure notes

Site: https://otel-hackathon-data-site.vercel.app, the "Grand Harbour Hotel" portal.
Every page is client-rendered (Next.js RSC, with the data embedded in `self.__next_f`
script payloads). A plain `curl` just returns an empty shell, so you have to drive
Playwright and wait for `networkidle` plus a short timeout. There is no JSON API and no
`_next/data` fetch; the data sits inline in the rendered HTML. The anchor regenerates
daily, so reconcile on the same day you scrape.

## Reconciliation snapshot (anchor 2026-06-22)
`total_reservations=254`, `total_stay_rows=535`, `dataset_revision=2026.06.12.2`,
`cancelled_reservations=21`, `provisional_row_count=5`, `property_date_mismatch_count=3`,
`reservation_stay_status_sha256=1f3acd2af5c53ffdeec317f18c10f92db6c78a82b03144097a98c3347b58de7d`.
(These shift when the anchor changes, so re-read on scrape day.)

## /reservations (list page)
- Paginated table, 100 rows per page, footer shows `Page X of N` (currently 3 pages).
- Each row links `href="/reservations/<id>"` where ids are `R0001`, `R0002`, and so on.
- Pagination: buttons labelled `Prev` / `Next` (`Next` goes disabled on the last page).
- Collect ids by reading all `a[href^="/reservations/"]` on a page, then click `Next`
  until it is disabled or gone. The `R####` ids look sequential, but don't assume that;
  scrape every page and dedupe.

## /reservations/<id> (detail page, the grain source)
- Reservation-level fields live in `[data-testid="reservation-fields"]`.
  Each field is `<div data-field="NAME"><dt>NAME</dt><dd>VALUE</dd></div>`, read via
  `[data-field="NAME"] dd`. A value of `—` (em dash) means NULL.
  Fields present: `arrival_date`, `departure_date`, `nights`, `reservation_status`,
  `create_datetime` (UTC, e.g. `2026-02-24T19:14:00Z`), `cancellation_datetime`
  (`—` if none), `guest_country`, `is_block` (true/false), `is_walk_in`,
  `number_of_spaces`, `space_type`, `market_code`, `channel_code`, `source_name`,
  `rate_plan_code`, `adr_room`, `lead_time`, `company_name`, `travel_agent_name`.
  (It also shows `commercial_rate_code`, which isn't in the schema, so ignore it.)
- Stay-rows table: `[data-testid="stay-rows-table"]`, one row per night, columns
  `stay_date`, `property_date`, `financial_status`, `daily_room_revenue_before_tax`,
  `daily_total_revenue_before_tax`.
- Grain build: for each stay-row, combine the reservation-level fields with that row's
  `stay_date/property_date/financial_status/daily_*`. `reservation_status` is
  reservation-level (the same for every row); `financial_status` is per stay row.

## /reference (lookups, tabbed)
- Tabs (`role="tab"`): `Room types`, `Markets`, `Channels`, `Rate plans`, `Macro history`.
  Only the active tab's table is in the DOM, so click each tab before reading its table.
- Each table: the `<th>` cells are the column names (they match the schema exactly) and
  the `<tbody>` rows are the values. Expected counts: room_type 3, market_code 10,
  channel 4, rate_plan 8, market_macro_group_history 11.
  - Room types → `room_type_lookup` (space_type, room_class, display_name, number_of_rooms)
  - Markets → `market_code_lookup` (market_code, market_name, macro_group, description)
  - Channels → `channel_code_lookup` (channel_code, channel_name, channel_group)
  - Rate plans → `rate_plan_lookup` (rate_plan_code, plan_family, is_commissionable)
  - Macro history → `market_macro_group_history` (market_code, valid_from, valid_to, macro_group)

## /verify (reconciliation)
- The full JSON object is embedded in the RSC payload. Pull it out by regex from the page
  content (keys: `anchor_date`, `dataset_revision`, `total_reservations`, `total_stay_rows`,
  `reservation_stay_status_sha256`, `cancelled_reservations`, `provisional_row_count`,
  `property_date_mismatch_count`, `posted_stay_rows`, `posted_otb_room_nights`,
  `posted_room_revenue_before_tax`, `posted_total_revenue_before_tax`, `stly_*`).
- Use `anchor_date` for `SCRAPE_MANIFEST.anchor_date` and `dataset_revision` for
  `load_manifest.dataset_revision`.

## Transform rules
- `—` → NULL for `cancellation_datetime`, `company_name`, `travel_agent_name`,
  `guest_country`.
- Booleans: `true`/`false` strings become bools. Numerics: strip commas. Timestamps:
  keep the ISO `...Z` (UTC) form. One output row per `(reservation_id, stay_date)`.
- Load every row (Cancelled and Provisional included) into `reservations_hackathon`;
  the semantic views apply the OTB filters. Counts depend on the anchor, so reconcile
  against `/verify` on scrape day (e.g. anchor 2026-06-22 gives 254 reservations / 535
  stay rows).

## Data-quality finding: the rate_plan_code FK can't hold
The reference Rate plans table has exactly 8 curated codes
(`BOOKBAR, GROUPBB, DLY1, FITBB, CORP10BB, PROMO1, ZEPHYR-CORP-25, WALKIN`), but the
reservations carry 16 distinct granular booking codes (e.g. `OCHEARLY`, `EXPBARB`,
`BARCBB`, `BOOKBARB`, `BOOKPROM`, `DLYBB`, `EXPBARH`, `EXPP`, `GOORO`, `OCHPERKRO`).
`/verify` still expects `rate_plan_lookup` to be 8 rows, so the brief's
`reservations_hackathon.rate_plan_code → rate_plan_lookup` FK is unsatisfiable against
the real data. The decision: drop only that one FK (`sql/relax_fk.sql`), keep the 8-row
reference, and load every booking row. `space_type`, `market_code`, and `channel_code`
all map cleanly to their lookups (verified by `integrity_report`).
