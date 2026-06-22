"""Tool-layer property tests, run against the loaded Supabase DB.
"""

import inspect
import json
import pathlib

import tools.rm_tools as T
from src.rmagent.db import query
from tools.rm_tools import (get_as_of_otb, get_block_vs_transient_mix,
                            get_otb_summary, get_pickup_delta, get_segment_mix)

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL_NAMES = [
    "get_otb_summary", "get_segment_mix", "get_pickup_delta",
    "get_as_of_otb", "get_block_vs_transient_mix",
]


# grain inequality: rows, reservations, and room nights are different counts
def test_grain_inequality():
    r = get_otb_summary("2025-07", exclude_cancelled=True)
    assert r["reservation_count"] < r["row_count"]
    assert r["room_nights"] >= r["reservation_count"]
    assert r["room_revenue"] <= r["total_revenue"]


# excluding cancelled changes the counts
def test_cancellation_filter_changes_counts():
    # Dataset regenerates daily, so find a month that currently has cancelled
    # Posted rows rather than hardcoding one.
    months = query(
        "select to_char(stay_date,'YYYY-MM') m from reservations_hackathon "
        "where reservation_status = 'Cancelled' and financial_status = 'Posted' "
        "group by 1 order by count(*) desc limit 1"
    )
    assert months, "no cancelled Posted rows in dataset (broken ETL)"
    month = months[0]["m"]
    inc = get_otb_summary(month, exclude_cancelled=False)
    exc = get_otb_summary(month, exclude_cancelled=True)
    assert exc["row_count"] < inc["row_count"]
    assert exc["reservation_count"] <= inc["reservation_count"]


# segment shares sum to one
def test_segment_shares_sum_to_one():
    r = get_segment_mix("2025-07")
    assert abs(sum(s["share_of_room_nights"] for s in r["segments"]) - 1.0) < 1e-6
    assert abs(sum(s["share_of_revenue"] for s in r["segments"]) - 1.0) < 1e-6
    assert all(0 <= s["share_of_revenue"] <= 1 for s in r["segments"])


# macro_group filter narrows the universe to that group
def test_macro_filter_narrows():
    full = get_segment_mix("2025-07")
    retail = get_segment_mix("2025-07", macro_group="Retail")
    assert sum(s["room_nights"] for s in retail["segments"]) <= sum(
        s["room_nights"] for s in full["segments"]
    )
    assert retail["segments"], "expected at least one Retail segment"
    assert all(s["macro_group"] == "Retail" for s in retail["segments"])


# pickup keys off the booking date (create_datetime), not stay_date
def test_pickup_uses_booking_window():
    wide = get_pickup_delta(booking_window_days=3650, future_stay_from="2025-01-01")
    narrow = get_pickup_delta(booking_window_days=1, future_stay_from="2025-01-01")
    # create_datetime defines the booking window: a 1-day window <= a 10-year window.
    assert narrow["new_reservations"] <= wide["new_reservations"]
    # future_stay_from filter: no stays exist that far out.
    far = get_pickup_delta(booking_window_days=3650, future_stay_from="2030-01-01")
    assert far["new_room_nights"] == 0


# OTA segment shows up with a sane revenue share
def test_ota_present():
    r = get_segment_mix("2025-08")
    ota = [s for s in r["segments"] if s["market_code"] == "OTA"]
    assert ota, "OTA segment missing (broken ETL or wrong month)"
    assert 0 < ota[0]["share_of_revenue"] < 1


# provisional rows are excluded from default OTB
def test_provisional_excluded_by_default():
    # Dataset regenerates daily, so discover a non-cancelled month that currently
    # holds provisional rows rather than hardcoding one.
    months = query(
        "select to_char(stay_date,'YYYY-MM') m from reservations_hackathon "
        "where financial_status = 'Provisional' and reservation_status <> 'Cancelled' "
        "order by 1 limit 1"
    )
    assert months, "no non-cancelled provisional rows in dataset (broken ETL)"
    month = months[0]["m"]
    default = get_otb_summary(month, exclude_cancelled=True)
    raw_non_cancelled = query(
        "select count(*) c from reservations_hackathon "
        "where reservation_status <> 'Cancelled' and to_char(stay_date,'YYYY-MM') = %s",
        (month,),
    )[0]["c"]
    assert default["row_count"] < raw_non_cancelled  # provisional rows removed
    proof = json.loads((ROOT / "etl/LOAD_PROOF.json").read_text())
    assert proof["aggregates"]["provisional_row_count"] > 0


# provisional is included only when explicitly requested
def test_provisional_included_when_requested():
    months = query(
        "select to_char(stay_date,'YYYY-MM') m from reservations_hackathon "
        "where financial_status = 'Provisional' and reservation_status <> 'Cancelled' "
        "order by 1 limit 1"
    )
    assert months, "no non-cancelled provisional rows in dataset (broken ETL)"
    month = months[0]["m"]
    default = get_otb_summary(month)
    incl = get_otb_summary(month, include_provisional=True)
    # the included universe is strictly larger by exactly that month's non-cancelled
    # provisional stay rows, and the flag is echoed for transparency
    added = query(
        "select count(*) c from reservations_hackathon where financial_status = 'Provisional' "
        "and reservation_status <> 'Cancelled' and to_char(stay_date,'YYYY-MM') = %s",
        (month,),
    )[0]["c"]
    assert added > 0
    assert incl["row_count"] == default["row_count"] + added
    assert incl["include_provisional"] is True and default["include_provisional"] is False


# point-in-time as-of snapshot vs current OTB
def test_as_of_snapshot():
    far = get_as_of_otb("2025-08", as_of_utc="2027-01-01T00:00:00Z")
    early = get_as_of_otb("2025-08", as_of_utc="2024-01-01T00:00:00Z")
    current = get_otb_summary("2025-08", exclude_cancelled=True)
    assert far["as_of_utc"] == "2027-01-01T00:00:00Z"
    # Far-future as-of equals the current Posted/non-cancelled OTB.
    assert far["row_count"] == current["row_count"]
    # Early as-of has fewer rows (fewer bookings created by then).
    assert early["row_count"] <= far["row_count"]


# property_date vs stay_date mismatch count matches the load proof
def test_property_date_mismatch_matches_proof():
    proof = json.loads((ROOT / "etl/LOAD_PROOF.json").read_text())
    db = query(
        "select count(*) c from reservations_hackathon where property_date <> stay_date"
    )[0]["c"]
    assert db == proof["aggregates"]["property_date_mismatch_count"]


# block vs transient mix reconciles and stays within bounds
def test_block_reconciles_and_bounds():
    b = get_block_vs_transient_mix("2025-09")
    otb = get_otb_summary("2025-09", exclude_cancelled=True)
    assert abs((b["block_room_nights"] + b["transient_room_nights"]) - otb["room_nights"]) <= 1
    assert 0 <= b["block_share_of_room_nights"] <= 1
    assert 0 <= b["block_share_of_revenue"] <= 1
    assert b["top3_company_revenue_share"] <= 1.0
    assert len(b["top_companies"]) <= 3


# room-type ADR breakdown (the "which room type has the highest ADR" question)
def test_room_type_adr_breakdown():
    default = get_otb_summary("2025-08")
    assert "room_types" not in default  # off by default, shape unchanged
    r = get_otb_summary("2025-08", by_room_type=True)
    assert r["by_room_type"] is True and r["room_types"]
    rt = r["room_types"]
    # each adr is room_revenue / room_nights at the room-type grain
    for x in rt:
        assert abs(x["adr"] - (x["room_revenue"] / x["room_nights"])) < 1e-6
    # sorted by adr descending, so [0] is the highest-ADR room type
    assert [x["adr"] for x in rt] == sorted((x["adr"] for x in rt), reverse=True)
    # the breakdown reconciles to the blended totals
    assert sum(x["room_nights"] for x in rt) == r["room_nights"]
    assert abs(sum(x["room_revenue"] for x in rt) - r["room_revenue"]) < 1e-6


# tools expose no raw-SQL parameter and document their grain
def test_tool_isolation_no_raw_sql_and_grain_documented():
    for name in TOOL_NAMES:
        fn = getattr(T, name)
        params = inspect.signature(fn).parameters
        assert not any(p in ("sql", "query", "q") for p in params), f"{name} exposes raw SQL"
        doc = (fn.__doc__ or "").lower()
        assert any(w in doc for w in ("grain", "room night", "reservation", "stay row")), name


# tools read only the semantic views, never the raw fact table
def test_tools_never_query_raw_fact_table():
    src = (ROOT / "tools/rm_tools.py").read_text().lower()
    # the raw table may only appear in prose (docstring/comment), never in a FROM/JOIN
    for line in src.splitlines():
        code = line.split("#", 1)[0]
        assert "from reservations_hackathon" not in code, line
        assert "join reservations_hackathon" not in code, line
