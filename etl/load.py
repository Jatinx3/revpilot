"""Load: idempotent truncate-and-reload of scraped data into Postgres.

Re-running produces an identical database (idempotent). Writes one
load_manifest row per run. row_hash matches the brief's
reservation_stay_status_sha256 (sorted reservation_id|stay_date|financial_status).
"""

from __future__ import annotations

import hashlib

from src.rmagent.db import get_conn
from etl.transform import FACT_COLUMNS

# Lookup tables in FK-safe insert order, with their column tuples.
LOOKUP_ORDER = [
    ("room_type_lookup", ["space_type", "room_class", "display_name", "number_of_rooms"]),
    ("rate_plan_lookup", ["rate_plan_code", "plan_family", "is_commissionable"]),
    ("market_code_lookup", ["market_code", "market_name", "macro_group", "description"]),
    ("market_macro_group_history", ["market_code", "valid_from", "valid_to", "macro_group"]),
    ("channel_code_lookup", ["channel_code", "channel_name", "channel_group"]),
]

# Truncate order: fact first, then history (FK to market_code), then the rest.
TRUNCATE_TABLES = (
    "reservations_hackathon, market_macro_group_history, market_code_lookup, "
    "rate_plan_lookup, room_type_lookup, channel_code_lookup"
)

# Fact dimension column -> (lookup table, lookup key). Used for referential checks.
DIMENSION_FKS = {
    "space_type": ("room_type_lookup", "space_type"),
    "market_code": ("market_code_lookup", "market_code"),
    "channel_code": ("channel_code_lookup", "channel_code"),
    "rate_plan_code": ("rate_plan_lookup", "rate_plan_code"),
}


def integrity_report(lookups: dict[str, list[dict]], stay_rows: list[dict]) -> dict[str, list[str]]:
    """For each dimension, list fact codes missing from its lookup (unmapped)."""
    report: dict[str, list[str]] = {}
    for fact_col, (table, key) in DIMENSION_FKS.items():
        valid = {row[key] for row in lookups[table]}
        used = {row[fact_col] for row in stay_rows}
        report[fact_col] = sorted(used - valid)
    return report


def compute_row_hash(stay_rows: list[dict]) -> str:
    """SHA-256 of sorted reservation_id|stay_date|financial_status lines."""
    ordered = sorted(
        stay_rows,
        key=lambda r: (r["reservation_id"], r["stay_date"], r["financial_status"]),
    )
    payload = "\n".join(
        f'{r["reservation_id"]}|{r["stay_date"]}|{r["financial_status"]}'
        for r in ordered
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _insert_rows(cur, table: str, columns: list[str], rows: list[dict]) -> None:
    """Bulk-insert dict rows into a table for the given column order (no-op if empty)."""
    if not rows:
        return
    placeholders = ", ".join(f"%({c})s" for c in columns)
    collist = ", ".join(columns)
    cur.executemany(
        f"insert into {table} ({collist}) values ({placeholders})",
        rows,
    )


def load(
    lookups: dict[str, list[dict]],
    stay_rows: list[dict],
    dataset_revision: str,
    source_url: str,
) -> str:
    """Replace all data in one transaction. Returns the row_hash written."""
    row_hash = compute_row_hash(stay_rows)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"truncate table {TRUNCATE_TABLES} restart identity cascade")
        for table, columns in LOOKUP_ORDER:
            _insert_rows(cur, table, columns, lookups[table])
        _insert_rows(cur, "reservations_hackathon", FACT_COLUMNS, stay_rows)
        cur.execute(
            "insert into load_manifest (dataset_revision, scraped_at, source_url, row_hash) "
            "values (%(rev)s, now(), %(src)s, %(hash)s)",
            {"rev": dataset_revision, "src": source_url, "hash": row_hash},
        )
        conn.commit()
    return row_hash
