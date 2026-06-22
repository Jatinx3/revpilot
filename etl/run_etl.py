"""Orchestrate the full ETL: scrape -> transform -> load -> manifests.

Run: python -m etl.run_etl
Requires DATABASE_URL (Supabase) with schema.sql + sql/views.sql already applied.
"""

import asyncio

from playwright.async_api import async_playwright

from src.rmagent.config import DATA_SITE_URL
from etl.load import integrity_report, load
from etl.manifest import write_scrape_manifest
from etl.scrape import (scrape_reference, scrape_reservation_detail,
                        scrape_reservation_ids, scrape_verify)
from etl.transform import transform_detail_to_stay_rows


async def scrape_everything():
    """Drive Playwright once to scrape verify targets, lookups, ids, and all stay rows."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        verify = await scrape_verify(page)
        lookups = await scrape_reference(page)
        ids, pages = await scrape_reservation_ids(page)

        stay_rows = []
        for n, rid in enumerate(ids, 1):
            detail = await scrape_reservation_detail(page, rid)
            stay_rows.extend(transform_detail_to_stay_rows(detail))
            if n % 50 == 0 or n == len(ids):
                print(f"  scraped {n}/{len(ids)} details, {len(stay_rows)} stay rows")

        await browser.close()
    return verify, lookups, ids, pages, stay_rows


def main():
    """Run the full ETL: scrape -> write manifest -> integrity report -> load -> verify hash."""
    verify, lookups, ids, pages, stay_rows = asyncio.run(scrape_everything())

    manifest = write_scrape_manifest(ids, pages, verify["anchor_date"])
    print("Wrote etl/SCRAPE_MANIFEST.json:", manifest)

    report = integrity_report(lookups, stay_rows)
    for dim, unmapped in report.items():
        if unmapped:
            print(f"  integrity: {dim} has {len(unmapped)} code(s) not in lookup: {unmapped}")
        else:
            print(f"  integrity: {dim} fully mapped to lookup ✓")

    row_hash = load(
        lookups=lookups,
        stay_rows=stay_rows,
        dataset_revision=verify["dataset_revision"],
        source_url=DATA_SITE_URL,
    )
    print(f"Loaded {len(stay_rows)} stay rows / {len(ids)} reservations. row_hash={row_hash}")

    target = verify.get("reservation_stay_status_sha256")
    if target and target != row_hash:
        print(f"WARNING: row_hash != /verify sha256\n  ours  ={row_hash}\n  verify={target}")
    elif target:
        print("row_hash matches /verify reservation_stay_status_sha256 ✓")


if __name__ == "__main__":
    main()
