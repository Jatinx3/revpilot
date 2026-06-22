"""ETL property tests (Phase 1) — run against the loaded Supabase database.

Covers the published scenarios in tests/ETL_TEST_SCENARIOS.md:
  1. Lookup row counts
  2. Fact-table grain uniqueness
  3. Manifest <-> DB reconciliation
  4. (bonus) multi-night stay-row expansion
"""

import hashlib
import json
import pathlib

from src.rmagent.db import query

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_lookup_row_counts():
    """Scenario 1: lookup tables load to their expected fixed row counts."""
    counts = {r["t"]: r["n"] for r in query(
        "select 'room' t, count(*) n from room_type_lookup "
        "union all select 'rate', count(*) from rate_plan_lookup "
        "union all select 'market', count(*) from market_code_lookup "
        "union all select 'hist', count(*) from market_macro_group_history "
        "union all select 'chan', count(*) from channel_code_lookup"
    )}
    assert counts == {"room": 3, "rate": 8, "market": 10, "hist": 11, "chan": 4}


def test_no_duplicate_grain():
    """Scenario 2: one row per (reservation_id, stay_date) — no duplicate grain."""
    dupes = query(
        "select reservation_id, stay_date from reservations_hackathon "
        "group by 1, 2 having count(*) > 1"
    )
    assert dupes == []


def test_manifest_reconciles_with_db():
    """Scenario 3: manifest id count + sha256 reconcile with the loaded DB."""
    manifest = json.loads((ROOT / "etl/SCRAPE_MANIFEST.json").read_text())
    db_ids = [
        r["reservation_id"]
        for r in query("select distinct reservation_id from reservations_hackathon")
    ]
    assert manifest["reservation_ids_count"] == len(db_ids)
    sha = hashlib.sha256("\n".join(sorted(db_ids)).encode("utf-8")).hexdigest()
    assert manifest["reservation_ids_sha256"] == sha


def test_multi_night_expands_to_nights():
    """Scenario 4 (bonus): a multi-night reservation produces one stay row per night."""
    rows = query(
        "select reservation_id, nights, count(*) as stay_rows "
        "from reservations_hackathon group by reservation_id, nights "
        "having nights > 1 order by nights desc limit 1"
    )
    assert rows, "expected at least one multi-night reservation"
    assert rows[0]["stay_rows"] == rows[0]["nights"]
