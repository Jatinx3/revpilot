"""Live /health fingerprint computed from the database (not the committed file).

Returns the four fields the brief requires so reviewers can confirm the live DB
matches the submitted etl/LOAD_PROOF.json.
"""

from __future__ import annotations

import hashlib

from src.rmagent.db import query


def health_fingerprint() -> dict:
    """Compute the four /health fields live from the DB (db_fingerprint,
    dataset_revision, row_hash, financial_status_posted_only_rows)."""
    pairs = query(
        "select reservation_id, stay_date::text as sd, financial_status "
        "from reservations_hackathon order by reservation_id, stay_date, financial_status"
    )
    payload = "\n".join(f"{r['reservation_id']}|{r['sd']}|{r['financial_status']}" for r in pairs)
    db_fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    manifest = query(
        "select dataset_revision, row_hash from load_manifest order by load_id desc limit 1"
    )
    posted = query(
        "select count(*) c from reservations_hackathon "
        "where reservation_status <> 'Cancelled' and financial_status = 'Posted'"
    )[0]["c"]

    return {
        "db_fingerprint": db_fingerprint,
        "dataset_revision": manifest[0]["dataset_revision"] if manifest else None,
        "row_hash": manifest[0]["row_hash"] if manifest else None,
        "financial_status_posted_only_rows": posted,
    }
