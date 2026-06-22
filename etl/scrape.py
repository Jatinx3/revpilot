"""Extract: scrape the client-rendered data site with Playwright.

Selectors and page structure are documented in etl/SITE_NOTES.md.
All functions take an open Playwright async `page`. Data is inline in the
rendered HTML (no JSON API), so we wait for content to render before reading.
"""

from __future__ import annotations

import re

from src.rmagent.config import DATA_SITE_URL

# Reference tabs → (table name, ordered schema columns).
REFERENCE_TABS = {
    "Room types": ("room_type_lookup", ["space_type", "room_class", "display_name", "number_of_rooms"]),
    "Markets": ("market_code_lookup", ["market_code", "market_name", "macro_group", "description"]),
    "Channels": ("channel_code_lookup", ["channel_code", "channel_name", "channel_group"]),
    "Rate plans": ("rate_plan_lookup", ["rate_plan_code", "plan_family", "is_commissionable"]),
    "Macro history": ("market_macro_group_history", ["market_code", "valid_from", "valid_to", "macro_group"]),
}

# Reservation-level fields read from [data-field="..."] dd on the detail page.
RESERVATION_FIELDS = [
    "arrival_date", "departure_date", "nights", "reservation_status",
    "create_datetime", "cancellation_datetime", "guest_country", "is_block",
    "is_walk_in", "number_of_spaces", "space_type", "market_code",
    "channel_code", "source_name", "rate_plan_code", "adr_room", "lead_time",
    "company_name", "travel_agent_name",
]

EM_DASH = "—"


def _clean(value: str | None) -> str | None:
    """Normalise a cell: strip, treat em-dash as NULL."""
    if value is None:
        return None
    v = value.strip()
    return None if v in ("", EM_DASH) else v


async def scrape_reference(page) -> dict[str, list[dict]]:
    """Scrape the 5 reference tables. Returns {table_name: [row dicts]}."""
    await page.goto(f"{DATA_SITE_URL}/reference", wait_until="networkidle")
    out: dict[str, list[dict]] = {}
    for tab_label, (table, columns) in REFERENCE_TABS.items():
        await page.get_by_role("tab", name=tab_label).click()
        await page.wait_for_selector("table tbody tr")
        rows = await page.query_selector_all("table tbody tr")
        parsed: list[dict] = []
        for tr in rows:
            cells = await tr.query_selector_all("td")
            values = [(_clean(await c.inner_text())) for c in cells]
            if not any(values):
                continue
            parsed.append(_coerce_lookup(table, dict(zip(columns, values))))
        out[table] = parsed
    return out


def _coerce_lookup(table: str, row: dict) -> dict:
    """Type-coerce lookup values to match schema.sql."""
    if table == "room_type_lookup":
        row["number_of_rooms"] = int(row["number_of_rooms"])
    elif table == "rate_plan_lookup":
        row["is_commissionable"] = str(row["is_commissionable"]).lower() == "true"
    # market_macro_group_history valid_to may be NULL (open-ended) — already cleaned.
    return row


async def scrape_reservation_ids(page) -> tuple[list[str], int]:
    """Paginate the reservation list, return (sorted unique ids, pages_scraped)."""
    await page.goto(f"{DATA_SITE_URL}/reservations", wait_until="networkidle")
    await page.wait_for_selector('a[href^="/reservations/"]')
    body = await page.content()
    m = re.search(r"Page\s+\d+\s+of\s+(\d+)", body)
    total_pages = int(m.group(1)) if m else 1

    ids: set[str] = set()
    for page_num in range(1, total_pages + 1):
        # Pagination is client-side (no network call), so wait for the page
        # indicator to reflect the current page, then wait for the row list to
        # finish painting (its count stabilises) before reading.
        await page.wait_for_selector(f"text=Page {page_num} of {total_pages}")
        for href in await _stable_reservation_hrefs(page):
            m = re.match(r"/reservations/([^/?#]+)$", href or "")
            if m:
                ids.add(m.group(1))
        if page_num < total_pages:
            await page.get_by_role("button", name="Next").click()
    return sorted(ids), total_pages


async def _stable_reservation_hrefs(page) -> list[str]:
    """Poll reservation links until their count stops changing (render settled)."""
    prev = -1
    hrefs: list[str] = []
    for _ in range(40):
        hrefs = await page.eval_on_selector_all(
            'a[href^="/reservations/"]',
            "els => els.map(e => e.getAttribute('href'))",
        )
        if hrefs and len(hrefs) == prev:
            return hrefs
        prev = len(hrefs)
        await page.wait_for_timeout(250)
    return hrefs


async def scrape_reservation_detail(page, rid: str) -> dict:
    """Scrape one reservation detail page → {reservation fields, 'stay_rows': [...]}."""
    await page.goto(f"{DATA_SITE_URL}/reservations/{rid}", wait_until="networkidle")
    await page.wait_for_selector('[data-testid="stay-rows-table"]')

    detail: dict = {"reservation_id": rid}
    for field in RESERVATION_FIELDS:
        el = await page.query_selector(f'[data-field="{field}"] dd')
        detail[field] = _clean(await el.inner_text()) if el else None

    stay_rows: list[dict] = []
    trs = await page.query_selector_all('[data-testid="stay-rows-table"] tbody tr')
    for tr in trs:
        cells = [(_clean(await c.inner_text())) for c in await tr.query_selector_all("td")]
        stay_rows.append({
            "stay_date": cells[0],
            "property_date": cells[1],
            "financial_status": cells[2],
            "daily_room_revenue_before_tax": cells[3],
            "daily_total_revenue_before_tax": cells[4],
        })
    detail["stay_rows"] = stay_rows
    return detail


async def scrape_verify(page) -> dict:
    """Scrape /verify reconciliation targets from the embedded JSON payload."""
    await page.goto(f"{DATA_SITE_URL}/verify", wait_until="networkidle")
    await page.wait_for_selector("text=Verification targets")
    body = await page.content()

    def s(key):
        """Extract a string value for `key` from the embedded JSON payload."""
        m = re.search(rf'"{key}":\s*"([^"]+)"', body)
        return m.group(1) if m else None

    def i(key):
        """Extract an integer value for `key` from the embedded JSON payload."""
        m = re.search(rf'"{key}":\s*(\d+)', body)
        return int(m.group(1)) if m else None

    return {
        "anchor_date": s("anchor_date"),
        "dataset_revision": s("dataset_revision"),
        "reservation_stay_status_sha256": s("reservation_stay_status_sha256"),
        "total_reservations": i("total_reservations"),
        "total_stay_rows": i("total_stay_rows"),
        "cancelled_reservations": i("cancelled_reservations"),
        "provisional_row_count": i("provisional_row_count"),
        "property_date_mismatch_count": i("property_date_mismatch_count"),
    }
