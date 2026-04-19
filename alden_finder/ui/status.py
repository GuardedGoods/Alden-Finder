"""`/status` view: per-retailer freshness table."""

from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st
from dateutil import parser as dateparser

from alden_finder.core import db


def _age(ts: str | None) -> str:
    if not ts:
        return "—"
    try:
        dt = dateparser.isoparse(ts)
    except (TypeError, ValueError):
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta = (datetime.now(UTC) - dt).total_seconds()
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)}m"
    if delta < 86400:
        return f"{int(delta // 3600)}h"
    return f"{int(delta // 86400)}d"


def render() -> None:
    st.header("Data freshness")
    st.caption(
        "Scrapers run hourly via GitHub Actions. "
        "Retailers whose last successful scrape is older than 6h are flagged yellow; over 24h, red."
    )
    retailers = db.list_retailers(active_only=False)
    rows = []
    for r in retailers:
        rows.append(
            {
                "Retailer": r.get("name"),
                "Country": r.get("country"),
                "Active": "✅" if r.get("active") else "—",
                "Adapter": r.get("adapter_key"),
                "Last scrape": _age(r.get("last_scrape_finished_at")),
                "Status": r.get("last_scrape_status") or "—",
                "Products": r.get("last_scrape_product_count") or 0,
                "Error": (r.get("last_scrape_error") or "")[:80],
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)
