"""Transform: turn scraped reservation details into typed stay-date rows.

Output grain = one dict per (reservation_id, stay_date), matching the columns of
public.reservations_hackathon (excluding the generated reservation_stay_id).
"""

from __future__ import annotations

# Column order used for INSERT into reservations_hackathon (see etl/load.py).
FACT_COLUMNS = [
    "reservation_id", "arrival_date", "departure_date", "stay_date",
    "property_date", "reservation_status", "financial_status", "create_datetime",
    "cancellation_datetime", "guest_country", "is_block", "is_walk_in",
    "number_of_spaces", "space_type", "market_code", "channel_code",
    "source_name", "rate_plan_code", "daily_room_revenue_before_tax",
    "daily_total_revenue_before_tax", "nights", "adr_room", "lead_time",
    "company_name", "travel_agent_name",
]


def _num(value: str | None) -> str | None:
    """Strip thousands separators from a numeric string; keep None as None."""
    return value.replace(",", "") if value is not None else None


def _int(value: str | None) -> int | None:
    """Parse an integer from a scraped string (comma-stripped); None stays None."""
    return int(_num(value)) if value is not None else None


def _bool(value: str | None) -> bool:
    """Parse a scraped 'true'/'false' string into a bool."""
    return str(value).strip().lower() == "true"


def transform_detail_to_stay_rows(detail: dict) -> list[dict]:
    """Expand one reservation detail into per-night fact rows."""
    base = {
        "reservation_id": detail["reservation_id"],
        "arrival_date": detail["arrival_date"],
        "departure_date": detail["departure_date"],
        "reservation_status": detail["reservation_status"],
        "create_datetime": detail["create_datetime"],
        "cancellation_datetime": detail["cancellation_datetime"],
        "guest_country": detail["guest_country"],
        "is_block": _bool(detail["is_block"]),
        "is_walk_in": _bool(detail["is_walk_in"]),
        "number_of_spaces": _int(detail["number_of_spaces"]),
        "space_type": detail["space_type"],
        "market_code": detail["market_code"],
        "channel_code": detail["channel_code"],
        "source_name": detail["source_name"],
        "rate_plan_code": detail["rate_plan_code"],
        "nights": _int(detail["nights"]),
        "adr_room": _num(detail["adr_room"]),
        "lead_time": _int(detail["lead_time"]),
        "company_name": detail["company_name"],
        "travel_agent_name": detail["travel_agent_name"],
    }

    rows: list[dict] = []
    for sr in detail["stay_rows"]:
        rows.append({
            **base,
            "stay_date": sr["stay_date"],
            "property_date": sr["property_date"],
            "financial_status": sr["financial_status"],
            "daily_room_revenue_before_tax": _num(sr["daily_room_revenue_before_tax"]),
            "daily_total_revenue_before_tax": _num(sr["daily_total_revenue_before_tax"]),
        })
    return rows
