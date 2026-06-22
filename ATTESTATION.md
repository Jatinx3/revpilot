# ATTESTATION.md (Phase 0)

## Candidate

- Name: Jatin Assudani
- Repository URL: https://github.com/Jatinx3/revpilot
- Date: 2026-06-15

---

## Comprehension prompts

### 1. Fact-table grain

In one sentence, what is the grain of `reservations_hackathon`?

> One row per reservation per stay date. Each night of a reservation gets its own
> row, and `number_of_spaces` records how many rooms that reservation holds for that
> night, so rows, reservations, and room nights are three different counts.

### 2. Revenue columns

Name the two revenue columns and when to use each.

> `daily_room_revenue_before_tax` is room-only revenue for that stay-date row. That's
> the column behind ADR and any pure room-revenue number. `daily_total_revenue_before_tax`
> adds package and breakfast effects, so it's the one that answers a broader "total
> revenue on the books" question. Room revenue is always at or below total for the same
> scope.

### 3. Row vs reservation

Give one example question where counting rows would be wrong.

> "How many reservations do we have for July?" A 3-night booking is three rows, so
> counting rows over-counts. The right answer is `count(distinct reservation_id)`
> over July stay dates.

### 4. Schema fields

Is there an `otel_challenge_token` column in the official schema? If so, what is it used for?

> No. There is no `otel_challenge_token` column in `schema.sql`. I checked the file
> directly, so there is nothing it is used for.

### 5. Default OTB filters

Which `reservation_status` and `financial_status` values are excluded from default OTB?

> Exclude `reservation_status = 'Cancelled'` and `financial_status = 'Provisional'`.
> Default on-the-books is Posted and non-cancelled. Cancellations come in only when
> the question is about cancellations, and provisional only when the question
> explicitly asks for tentative or unposted business.

### 6. Stay date vs property date

When can `property_date` differ from `stay_date`, and which field drives monthly OTB?

> `property_date` usually equals `stay_date`, but it can differ on night-boundary or
> audit rows (Appendix B). Monthly OTB is driven by `stay_date`, not `property_date`.
> Property date only matters as the hotel business-date attribution when the two
> diverge.

### 7. Point-in-time OTB

How does `as_of_utc` change which cancelled rows are included in `get_as_of_otb`?

> It rebuilds the book as it was known at that instant. A reservation that is
> Cancelled now still counts as on-the-books at `as_of_utc` if its
> `cancellation_datetime` is after `as_of_utc`, because it had not been cancelled yet.
> It drops out once `cancellation_datetime` is at or before `as_of_utc`. Same idea on
> the create side: only rows with `create_datetime` at or before `as_of_utc` count.

### 8. Block vs transient

How does `is_block` affect a "group vs transient mix" question?

> `is_block = true` rows are group/block business; `is_block = false` is transient. A
> group-vs-transient mix splits room nights and revenue on that flag (room nights
> from `sum(number_of_spaces)`), giving each side's share of the month.

### 9. List pagination

How many reservations does the data site show per list page?

> 100 reservations per list page.

### 10. Pagination completeness

How will you prove you did not miss the last list page during ETL?

> I page through the list until there is no next page, collecting every
> `reservation_id` as I go, then write the page count and a sha256 of the sorted ids
> into `SCRAPE_MANIFEST.json`. The check is that the id count agrees in three places:
> the manifest, `count(distinct reservation_id)` in the loaded DB, and
> `total_reservations` on `/verify` for that anchor date. If those line up and the hash
> matches, I know nothing fell off the last page.

### 11. Tool grain

For `get_otb_summary`, what is the difference between `row_count` and `reservation_count`?

> `row_count` is the number of stay-date rows in scope (one per reservation per night,
> after filters). `reservation_count` is `count(distinct reservation_id)`. `row_count`
> is always at least `reservation_count` because a multi-night reservation spans several
> rows, so they are two different numbers. Counting rows when you mean reservations is
> exactly the over-counting trap.

### 12. Human-in-the-loop

Why must `get_as_of_otb` be gated behind approval, and what goes wrong if it is not?

> It is an expensive point-in-time rebuild: it re-derives the whole book at an
> arbitrary instant, and the agent can fire it over and over. Putting it behind approval
> stops that accidental, costly recomputation and keeps latency predictable. It also
> makes the "as of" assumption something the GM signs off on instead of a silent
> default. Without the gate the agent could kick off heavy reconstructions on its own
> and hand the GM a point-in-time figure they mistake for current OTB.

### 13. Skill vs tool

Name one revenue-manager question that should load a **skill** but call **`get_segment_mix`**, not raw SQL.

> "Are we too dependent on OTA?" It loads the OTA-dependency skill, which calls
> `get_segment_mix`, reads OTA's `share_of_revenue`, applies a concentration
> threshold, and recommends an action. No raw SQL involved.

---

## ETL design (one line)

Describe pagination strategy + idempotency approach + **anchor date** you will
scrape against (must match `/verify` on load day).

> Paginate `/reservations` (100 per page) until there is no next page, drill into each
> `/reservations/<id>` for the detail-only fields, transform to reservation-by-stay-date
> grain, then do an idempotent truncate-and-reload inside one transaction keyed to the
> scraped `dataset_revision` (writing a `load_manifest` row each run). Scrape against an
> anchor date equal to the calendar day of the load, and reconcile the counts and the
> reservation-id hash with `/verify` that same day.
