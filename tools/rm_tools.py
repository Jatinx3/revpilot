"""Revenue Manager tool layer (Phase 2).

Five typed tools with the business rules baked in. They read ONLY from the
semantic views, never the raw fact table and never arbitrary SQL from the model:
  - vw_stay_night_base / vw_segment_stay_night : default OTB (Posted, non-cancelled)
  - vw_stay_night_posted                       : include-cancelled / point-in-time
  - vw_stay_night_with_provisional             : explicit include-provisional path
Every count and sum documents its grain.

Grain vocabulary (see tools/METRIC_DEFINITIONS.md):
  - stay row  : one row per (reservation_id, stay_date)
  - reservation: count(distinct reservation_id)
  - room night : sum(number_of_spaces) at stay-date grain
Default OTB universe = Posted, non-cancelled (vw_stay_night_base).
"""

from __future__ import annotations

from src.rmagent.db import query


def _f(value) -> float:
    """Coerce a DB numeric (or None) to float, defaulting to 0.0."""
    return float(value) if value is not None else 0.0


def _i(value) -> int:
    """Coerce a DB integer (or None) to int, defaulting to 0."""
    return int(value) if value is not None else 0


def get_otb_summary(
    stay_month: str,
    exclude_cancelled: bool = True,
    include_provisional: bool = False,
    by_room_type: bool = False,
) -> dict:
    """On-the-books summary for a calendar month of stay dates (YYYY-MM).

    Grain (one row per reservation per night): `row_count` is stay-date ROWS, which
    is NOT the reservation count. `reservation_count` = count(distinct
    reservation_id). `room_nights` = sum(number_of_spaces). `room_revenue` and
    `total_revenue` are sums of daily_room_revenue_before_tax and
    daily_total_revenue_before_tax at that same stay-row grain.

    Universe (default = Posted, non-cancelled = vw_stay_night_base):
      - exclude_cancelled=False adds cancelled reservations back into scope.
      - include_provisional=True adds tentative (Provisional) business; off by
        default per the OTB rule, so only set it when the question explicitly asks
        for tentative/provisional business. The cancelled filter still applies on
        top (provisional + non-cancelled unless exclude_cancelled is also False).

    by_room_type=True adds a `room_types` breakdown for the same universe: one entry
    per room type (joined to room_type_lookup), each with room_nights, room_revenue,
    and `adr` = room_revenue / room_nights at the room-type grain, sorted by adr
    descending (so room_types[0] is the highest-ADR room type). Use it for
    "which room type has the highest ADR".

    Returns: stay_month, row_count, reservation_count, room_nights, room_revenue,
    total_revenue, exclude_cancelled, include_provisional, by_room_type, and
    room_types[{space_type, room_class, display_name, room_nights, room_revenue,
    adr}] when by_room_type is set.
    """
    where = "to_char(stay_date,'YYYY-MM') = %(m)s"
    if include_provisional:
        view = "vw_stay_night_with_provisional"
        if exclude_cancelled:
            where += " and reservation_status <> 'Cancelled'"
    elif exclude_cancelled:
        view = "vw_stay_night_base"  # Posted, non-cancelled (filters baked in)
    else:
        view = "vw_stay_night_posted"  # Posted, cancelled rows retained
    row = query(
        f"""
        select count(*) as row_count,
               count(distinct reservation_id) as reservation_count,
               coalesce(sum(number_of_spaces), 0) as room_nights,
               coalesce(sum(daily_room_revenue_before_tax), 0) as room_revenue,
               coalesce(sum(daily_total_revenue_before_tax), 0) as total_revenue
        from {view}
        where {where}
        """,
        {"m": stay_month},
    )[0]
    result = {
        "stay_month": stay_month,
        "row_count": _i(row["row_count"]),
        "reservation_count": _i(row["reservation_count"]),
        "room_nights": _i(row["room_nights"]),
        "room_revenue": _f(row["room_revenue"]),
        "total_revenue": _f(row["total_revenue"]),
        "exclude_cancelled": exclude_cancelled,
        "include_provisional": include_provisional,
        "by_room_type": by_room_type,
    }
    if by_room_type:
        rt = query(
            f"""
            select b.space_type,
                   l.room_class,
                   l.display_name,
                   coalesce(sum(b.number_of_spaces), 0) as room_nights,
                   coalesce(sum(b.daily_room_revenue_before_tax), 0) as room_revenue
            from {view} b
            left join room_type_lookup l on l.space_type = b.space_type
            where {where}
            group by b.space_type, l.room_class, l.display_name
            """,
            {"m": stay_month},
        )
        room_types = [
            {
                "space_type": r["space_type"],
                "room_class": r["room_class"],
                "display_name": r["display_name"],
                "room_nights": _i(r["room_nights"]),
                "room_revenue": _f(r["room_revenue"]),
                "adr": (_f(r["room_revenue"]) / _i(r["room_nights"])) if _i(r["room_nights"]) else 0.0,
            }
            for r in rt
        ]
        room_types.sort(key=lambda x: x["adr"], reverse=True)
        result["room_types"] = room_types
    return result


def get_segment_mix(stay_month: str, macro_group: str | None = None) -> dict:
    """Segment mix for a stay month using vw_segment_stay_night (stay-night grain).

    Grain: room_nights = sum(number_of_spaces); total_revenue = sum of
    daily_total_revenue_before_tax. Shares use the SAME filtered population as the
    denominator (echoed in `denominator`). If macro_group is set, only that effective
    macro_group is returned and the denominator narrows to it.

    Returns: stay_month, macro_group, denominator{room_nights,total_revenue},
    segments[{market_code, market_name, macro_group, room_nights, total_revenue,
    share_of_room_nights, share_of_revenue}].
    """
    where = "to_char(stay_date,'YYYY-MM') = %(m)s"
    params: dict = {"m": stay_month}
    if macro_group is not None:
        where += " and effective_macro_group = %(g)s"
        params["g"] = macro_group
    rows = query(
        f"""
        select market_code,
               market_name,
               effective_macro_group as macro_group,
               coalesce(sum(number_of_spaces), 0) as room_nights,
               coalesce(sum(daily_total_revenue_before_tax), 0) as total_revenue
        from vw_segment_stay_night
        where {where}
        group by market_code, market_name, effective_macro_group
        order by total_revenue desc
        """,
        params,
    )
    total_rn = sum(_i(r["room_nights"]) for r in rows)
    total_rev = sum(_f(r["total_revenue"]) for r in rows)
    segments = [
        {
            "market_code": r["market_code"],
            "market_name": r["market_name"],
            "macro_group": r["macro_group"],
            "room_nights": _i(r["room_nights"]),
            "total_revenue": _f(r["total_revenue"]),
            "share_of_room_nights": (_i(r["room_nights"]) / total_rn) if total_rn else 0.0,
            "share_of_revenue": (_f(r["total_revenue"]) / total_rev) if total_rev else 0.0,
        }
        for r in rows
    ]
    return {
        "stay_month": stay_month,
        "macro_group": macro_group,
        "denominator": {"room_nights": total_rn, "total_revenue": total_rev},
        "segments": segments,
    }


def get_pickup_delta(booking_window_days: int, future_stay_from: str | None = None) -> dict:
    """Booking pace / pickup for future stays.

    The booking window uses create_datetime (NOT stay_date), bounded by
    [start_of_day(Europe/London, now - booking_window_days), now()] compared in UTC.
    Only stays with stay_date >= future_stay_from are counted (vw_stay_night_base,
    Posted non-cancelled). future_stay_from defaults to today (UTC) when omitted,
    since "future stays" means stays from today onward — so a plain "what changed in
    the last N days for future stays" needs no date. Grain: new_reservations =
    count(distinct reservation_id); new_room_nights = sum(number_of_spaces);
    new_total_revenue = sum of daily_total_revenue_before_tax over the matched rows.

    Returns: booking_window_days, future_stay_from (the resolved date),
    new_reservations, new_room_nights, new_total_revenue, by_segment[{market_code,
    new_reservations, new_room_nights, new_total_revenue}] (top markets by
    new_total_revenue, same per-segment definitions as the totals).
    """
    if future_stay_from is None:
        from datetime import date

        future_stay_from = date.today().isoformat()
    window = (
        "create_datetime >= (date_trunc('day', (now() at time zone 'Europe/London') "
        "- make_interval(days => %(d)s)) at time zone 'Europe/London') "
        "and create_datetime <= now() and stay_date >= %(f)s"
    )
    params = {"d": booking_window_days, "f": future_stay_from}
    row = query(
        f"""
        select count(distinct reservation_id) as new_reservations,
               coalesce(sum(number_of_spaces), 0) as new_room_nights,
               coalesce(sum(daily_total_revenue_before_tax), 0) as new_total_revenue
        from vw_stay_night_base
        where {window}
        """,
        params,
    )[0]
    by_segment = query(
        f"""
        select market_code,
               count(distinct reservation_id) as new_reservations,
               coalesce(sum(number_of_spaces), 0) as new_room_nights,
               coalesce(sum(daily_total_revenue_before_tax), 0) as new_total_revenue
        from vw_segment_stay_night
        where {window}
        group by market_code
        order by new_total_revenue desc
        limit 5
        """,
        params,
    )
    return {
        "booking_window_days": booking_window_days,
        "future_stay_from": future_stay_from,
        "new_reservations": _i(row["new_reservations"]),
        "new_room_nights": _i(row["new_room_nights"]),
        "new_total_revenue": _f(row["new_total_revenue"]),
        "by_segment": [
            {
                "market_code": r["market_code"],
                "new_reservations": _i(r["new_reservations"]),
                "new_room_nights": _i(r["new_room_nights"]),
                "new_total_revenue": _f(r["new_total_revenue"]),
            }
            for r in by_segment
        ],
    }


def get_as_of_otb(stay_month: str, as_of_utc: str) -> dict:
    """Point-in-time on-the-books for a stay month, as known at as_of_utc.

    A stay row is included when: create_datetime <= as_of_utc, AND
    (reservation_status <> 'Cancelled' OR cancellation_datetime > as_of_utc), AND
    financial_status = 'Posted'. Same grain/shape as get_otb_summary plus an
    as_of_utc echo. This is an expensive point-in-time rebuild — gate it behind HITL.
    Reads vw_stay_night_posted (Posted, cancelled rows retained for as-of logic).
    """
    row = query(
        """
        select count(*) as row_count,
               count(distinct reservation_id) as reservation_count,
               coalesce(sum(number_of_spaces), 0) as room_nights,
               coalesce(sum(daily_room_revenue_before_tax), 0) as room_revenue,
               coalesce(sum(daily_total_revenue_before_tax), 0) as total_revenue
        from vw_stay_night_posted
        where to_char(stay_date,'YYYY-MM') = %(m)s
          and create_datetime <= %(asof)s
          and (reservation_status <> 'Cancelled' or cancellation_datetime > %(asof)s)
          and financial_status = 'Posted'
        """,
        {"m": stay_month, "asof": as_of_utc},
    )[0]
    return {
        "stay_month": stay_month,
        "as_of_utc": as_of_utc,
        "row_count": _i(row["row_count"]),
        "reservation_count": _i(row["reservation_count"]),
        "room_nights": _i(row["room_nights"]),
        "room_revenue": _f(row["room_revenue"]),
        "total_revenue": _f(row["total_revenue"]),
    }


def get_block_vs_transient_mix(stay_month: str) -> dict:
    """Block vs transient mix for a stay month (vw_stay_night_base, Posted non-cancelled).

    Grain: room_nights = sum(number_of_spaces); block/transient_total_revenue =
    sum of daily_total_revenue_before_tax over the stay rows on each side. Block =
    is_block true; transient = is_block false. top_companies = top 3 company_name by
    total_revenue (null -> 'Transient'); top3_company_revenue_share = their share of
    the month total revenue.

    Returns: stay_month, block_room_nights, transient_room_nights,
    block_total_revenue, transient_total_revenue, block_share_of_room_nights,
    block_share_of_revenue, top_companies[{company_name,total_revenue}],
    top3_company_revenue_share.
    """
    split = query(
        """
        select is_block,
               coalesce(sum(number_of_spaces), 0) as room_nights,
               coalesce(sum(daily_total_revenue_before_tax), 0) as total_revenue
        from vw_stay_night_base
        where to_char(stay_date,'YYYY-MM') = %(m)s
        group by is_block
        """,
        {"m": stay_month},
    )
    block_rn = next((_i(r["room_nights"]) for r in split if r["is_block"]), 0)
    trans_rn = next((_i(r["room_nights"]) for r in split if not r["is_block"]), 0)
    block_rev = next((_f(r["total_revenue"]) for r in split if r["is_block"]), 0.0)
    trans_rev = next((_f(r["total_revenue"]) for r in split if not r["is_block"]), 0.0)
    total_rn = block_rn + trans_rn
    total_rev = block_rev + trans_rev

    companies = query(
        """
        select coalesce(company_name, 'Transient') as company_name,
               coalesce(sum(daily_total_revenue_before_tax), 0) as total_revenue
        from vw_stay_night_base
        where to_char(stay_date,'YYYY-MM') = %(m)s
        group by coalesce(company_name, 'Transient')
        order by total_revenue desc
        limit 3
        """,
        {"m": stay_month},
    )
    top3_rev = sum(_f(c["total_revenue"]) for c in companies)
    return {
        "stay_month": stay_month,
        "block_room_nights": block_rn,
        "transient_room_nights": trans_rn,
        "block_total_revenue": block_rev,
        "transient_total_revenue": trans_rev,
        "block_share_of_room_nights": (block_rn / total_rn) if total_rn else 0.0,
        "block_share_of_revenue": (block_rev / total_rev) if total_rev else 0.0,
        "top_companies": [
            {"company_name": c["company_name"], "total_revenue": _f(c["total_revenue"])}
            for c in companies
        ],
        "top3_company_revenue_share": (top3_rev / total_rev) if total_rev else 0.0,
    }
