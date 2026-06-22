"""Dry-run: scrape + transform the whole dataset and validate against /verify.

Does NOT touch the database. Used to prove the scraper/transform before load.
Run: python -m etl.dryrun
"""

import asyncio

from playwright.async_api import async_playwright

from etl.manifest import reservation_ids_sha256
from etl.scrape import (scrape_reference, scrape_reservation_detail,
                        scrape_reservation_ids, scrape_verify)
from etl.transform import transform_detail_to_stay_rows

EXPECTED_LOOKUP_COUNTS = {
    "room_type_lookup": 3, "market_code_lookup": 10, "channel_code_lookup": 4,
    "rate_plan_lookup": 8, "market_macro_group_history": 11,
}


async def main():
    """Scrape + transform the whole dataset and validate counts against /verify (no DB)."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        verify = await scrape_verify(page)
        print("VERIFY targets:", verify)

        lookups = await scrape_reference(page)
        lookup_counts = {k: len(v) for k, v in lookups.items()}
        print("Lookup counts:", lookup_counts)

        ids, pages = await scrape_reservation_ids(page)
        print(f"Reservation ids: {len(ids)} across {pages} pages; sha={reservation_ids_sha256(ids)[:16]}…")

        all_rows = []
        for n, rid in enumerate(ids, 1):
            detail = await scrape_reservation_detail(page, rid)
            all_rows.extend(transform_detail_to_stay_rows(detail))
            if n % 50 == 0 or n == len(ids):
                print(f"  scraped {n}/{len(ids)} details, {len(all_rows)} stay rows so far")

        await browser.close()

    print("\n==== VALIDATION ====")
    ok = True
    for table, expected in EXPECTED_LOOKUP_COUNTS.items():
        got = lookup_counts.get(table)
        flag = "OK" if got == expected else "FAIL"
        ok &= got == expected
        print(f"  [{flag}] {table}: {got} (expected {expected})")

    checks = [
        ("reservation_ids_count", len(ids), verify["total_reservations"]),
        ("total_stay_rows", len(all_rows), verify["total_stay_rows"]),
        ("pages_scraped", pages, 3),
    ]
    for name, got, expected in checks:
        flag = "OK" if got == expected else "FAIL"
        ok &= got == expected
        print(f"  [{flag}] {name}: {got} (expected {expected})")

    distinct = len({(r["reservation_id"], r["stay_date"]) for r in all_rows})
    flag = "OK" if distinct == len(all_rows) else "FAIL"
    ok &= distinct == len(all_rows)
    print(f"  [{flag}] grain uniqueness: {distinct} distinct == {len(all_rows)} rows")

    cancelled = len({r["reservation_id"] for r in all_rows if r["reservation_status"] == "Cancelled"})
    provisional = sum(1 for r in all_rows if r["financial_status"] == "Provisional")
    print(f"  info  cancelled_reservations={cancelled} (verify {verify['cancelled_reservations']}), "
          f"provisional_rows={provisional} (verify {verify['provisional_row_count']})")

    print("\nRESULT:", "ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")


if __name__ == "__main__":
    asyncio.run(main())
