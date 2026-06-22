"""Write the scrape manifest proving full pagination capture."""

from __future__ import annotations

import hashlib
import json


def reservation_ids_sha256(ids: list[str]) -> str:
    """SHA-256 of sorted reservation_id lines (one id per line)."""
    payload = "\n".join(sorted(ids)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_scrape_manifest(
    ids: list[str], pages: int, anchor: str, path: str = "etl/SCRAPE_MANIFEST.json"
) -> dict:
    """Write SCRAPE_MANIFEST.json (anchor, pages, id count + sha256) and return it."""
    manifest = {
        "anchor_date": anchor,
        "pages_scraped": pages,
        "reservation_ids_count": len(ids),
        "reservation_ids_sha256": reservation_ids_sha256(ids),
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    return manifest
