# Data-site structure notes (from inspection — plan Task 1.3)

Site: https://otel-hackathon-data-site.vercel.app — "Grand Harbour Hotel" portal.
All pages are **client-rendered** (Next.js RSC; data embedded in `self.__next_f`
script payloads). Plain `curl` returns an empty shell — drive Playwright, wait for
`networkidle` + a short timeout. **No JSON API / no `_next/data` fetch** — data is
inline in the rendered HTML. Anchor regenerates daily; reconcile same day.

## Reconciliation snapshot (anchor 2026-06-15)
`total_reservations=254`, `total_stay_rows=516`, `dataset_revision=2026.06.12.2`,
`cancelled_reservations=18`, `provisional_row_count=5`, `property_date_mismatch_count=3`,
`reservation_stay_status_sha256=e98695ff7148e8579b26ed482597c2e06d59d724056a4dcb8b2a23823819ebb8`.
(These shift when the anchor changes — re-read on scrape day.)

## /reservations — list
- Paginated table, **100 rows/page**, footer shows `Page X of N` (currently 3 pages).
- Each row links `href="/reservations/<id>"` where ids are `R0001`, `R0002`, …
- Pagination: buttons with text `Prev` / `Next` (Next becomes disabled on last page).
- Collect ids by reading all `a[href^="/reservations/"]` per page, then clicking
  `Next` until it is disabled/absent. (`R####` are sequential but DO NOT assume —
  scrape every page and dedupe.)

## /reservations/<id> — detail (the grain source)
- Reservation-level fields container: `[data-testid="reservation-fields"]`.
  Each field: `<div data-field="NAME"><dt>NAME</dt><dd>VALUE</dd></div>`.
  Read with selector `[data-field="NAME"] dd`. A value of `—` (em dash) means NULL.
  Fields present: `arrival_date`, `departure_date`, `nights`, `reservation_status`,
  `create_datetime` (UTC, e.g. `2026-02-24T19:14:00Z`), `cancellation_datetime`
  (`—` if none), `guest_country`, `is_block` (true/false), `is_walk_in`,
  `number_of_spaces`, `space_type`, `market_code`, `channel_code`, `source_name`,
  `rate_plan_code`, `adr_room`, `lead_time`, `company_name`, `travel_agent_name`.
  (Also shows `commercial_rate_code` — NOT in schema, ignore.)
- Stay-rows table: `[data-testid="stay-rows-table"]`, columns (one row per night):
  `stay_date`, `property_date`, `financial_status`, `daily_room_revenue_before_tax`,
  `daily_total_revenue_before_tax`.
- **Grain build:** for each stay-row, combine the reservation-level fields with that
  row's `stay_date/property_date/financial_status/daily_*`. `reservation_status` is
  reservation-level (same for all rows); `financial_status` is **per stay row**.

## /reference — lookups (tabbed)
- Tabs `role="tab"`: `Room types`, `Markets`, `Channels`, `Rate plans`, `Macro history`.
  Only the active tab's table is in the DOM — **click each tab**, then read its table.
- Each table: `<th>` cells are the column names (match schema exactly), `<tbody>` rows
  are values. Expected counts: room_type 3, market_code 10, channel 4, rate_plan 8,
  market_macro_group_history 11.
  - Room types → `room_type_lookup` (space_type, room_class, display_name, number_of_rooms)
  - Markets → `market_code_lookup` (market_code, market_name, macro_group, description)
  - Channels → `channel_code_lookup` (channel_code, channel_name, channel_group)
  - Rate plans → `rate_plan_lookup` (rate_plan_code, plan_family, is_commissionable)
  - Macro history → `market_macro_group_history` (market_code, valid_from, valid_to, macro_group)

## /verify — reconciliation
- Full JSON object is embedded in the RSC payload. Extract by regex from page content
  (keys: `anchor_date`, `dataset_revision`, `total_reservations`, `total_stay_rows`,
  `reservation_stay_status_sha256`, `cancelled_reservations`, `provisional_row_count`,
  `property_date_mismatch_count`, `posted_stay_rows`, `posted_otb_room_nights`,
  `posted_room_revenue_before_tax`, `posted_total_revenue_before_tax`, `stly_*`).
- Use `anchor_date` for `SCRAPE_MANIFEST.anchor_date` and `dataset_revision` for
  `load_manifest.dataset_revision`.

## Transform rules
- `—` → NULL for `cancellation_datetime`, `company_name`, `travel_agent_name`,
  `guest_country`.
- Booleans: `true`/`false` strings → bool. Numerics: strip commas. Timestamps: keep
  ISO `...Z` (UTC). One output row per `(reservation_id, stay_date)`.
- Load **all** rows (including Cancelled and Provisional) into `reservations_hackathon`;
  the semantic views apply OTB filters. Counts are anchor-dependent — reconcile against
  `/verify` on scrape day (e.g. anchor 2026-06-17 → 254 reservations / 531 stay rows).

## Data-quality finding: rate_plan_code FK cannot hold
The reference **Rate plans** table has exactly **8** curated codes
(`BOOKBAR, GROUPBB, DLY1, FITBB, CORP10BB, PROMO1, ZEPHYR-CORP-25, WALKIN`), but
reservations carry **16** distinct granular booking rate codes (e.g. `OCHEARLY`,
`EXPBARB`, `BARCBB`, `BOOKBARB`, `BOOKPROM`, `DLYBB`, `EXPBARH`, `EXPP`, `GOORO`,
`OCHPERKRO`). `/verify` still expects `rate_plan_lookup` = 8 rows, so the brief's
`reservations_hackathon.rate_plan_code → rate_plan_lookup` FK is **unsatisfiable**
against the real data. Decision: drop only that FK (`sql/relax_fk.sql`), keep the
8-row reference, and load every booking row. `space_type`, `market_code`,
`channel_code` map cleanly to their lookups (verified by `integrity_report`).
