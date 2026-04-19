"""Supabase / Postgres client and query helpers.

The Streamlit UI and the scraping runner both go through this module.
When SUPABASE_URL / SUPABASE_KEY are not set, we transparently fall back to a
read-only in-memory sample dataset so `streamlit run` works out of the box
for first-time contributors.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

from alden_finder.core.models import FilterSpec, Retailer, ScrapeRun

log = logging.getLogger(__name__)


def _env(name: str) -> str | None:
    val = os.environ.get(name)
    if val:
        return val
    # Streamlit Cloud: secrets come through st.secrets, surfaced as env via:
    try:
        import streamlit as st

        return st.secrets.get(name)  # type: ignore[no-any-return]
    except Exception:
        return None


@lru_cache(maxsize=1)
def _client() -> Any | None:
    url = _env("SUPABASE_URL")
    key = _env("SUPABASE_SERVICE_ROLE_KEY") or _env("SUPABASE_KEY")
    if not url or not key:
        log.info("Supabase credentials not configured; using in-memory sample data.")
        return None
    from supabase import create_client

    return create_client(url, key)


# ---------------------------------------------------------------------------
# In-memory sample data (used when no DB is configured)
# ---------------------------------------------------------------------------

_SAMPLE_RETAILERS: list[dict] = [
    {
        "id": 1, "name": "Alden of San Francisco", "url": "https://www.aldensf.com",
        "country": "US", "currency": "USD", "adapter_key": "alden_sf",
        "active": True, "rate_limit_s": 2.0, "source_type": "authorized",
        "last_scrape_finished_at": datetime.now(UTC).isoformat(),
        "last_scrape_status": "ok", "last_scrape_product_count": 42,
    },
    {
        "id": 2, "name": "Leffot", "url": "https://leffot.com",
        "country": "US", "currency": "USD", "adapter_key": "shopify",
        "active": True, "rate_limit_s": 2.0, "source_type": "authorized",
        "last_scrape_finished_at": datetime.now(UTC).isoformat(),
        "last_scrape_status": "ok", "last_scrape_product_count": 18,
    },
    {
        "id": 3, "name": "Skoaktiebolaget", "url": "https://www.skoaktiebolaget.se",
        "country": "SE", "currency": "SEK", "adapter_key": "shopify",
        "active": True, "rate_limit_s": 2.0, "source_type": "authorized",
        "last_scrape_finished_at": datetime.now(UTC).isoformat(),
        "last_scrape_status": "ok", "last_scrape_product_count": 9,
    },
]

_SAMPLE_PRODUCTS: list[dict] = [
    {
        "id": 1, "retailer_id": 1, "retailer_sku": "990",
        "url": "https://www.aldensf.com/products/990",
        "image_url": "https://placehold.co/600x400?text=Alden+990",
        "model_number": "990", "title_raw": "Alden 990 Chromexcel Plain Toe Blucher",
        "last_name": "Barrie", "leather_name": "Chromexcel", "color": "Brown",
        "category": "blucher", "size_us": 10, "width": "D",
        "price_minor": 72000, "currency": "USD", "on_sale": False,
        "stock_state": "in_stock", "source_type": "authorized",
        "last_seen_at": datetime.now(UTC).isoformat(),
    },
    {
        "id": 2, "retailer_id": 2, "retailer_sku": "405",
        "url": "https://leffot.com/products/alden-405",
        "image_url": "https://placehold.co/600x400?text=Alden+405+Indy",
        "model_number": "405", "title_raw": "Alden 405 Indy Boot Color 8 Shell Cordovan",
        "last_name": "Trubalance", "leather_name": "Shell Cordovan", "color": "Color 8",
        "category": "indy", "size_us": 9.5, "width": "D",
        "price_minor": 98000, "currency": "USD", "on_sale": False,
        "stock_state": "in_stock", "source_type": "authorized",
        "last_seen_at": datetime.now(UTC).isoformat(),
    },
    {
        "id": 3, "retailer_id": 3, "retailer_sku": "975",
        "url": "https://www.skoaktiebolaget.se/products/alden-975",
        "image_url": "https://placehold.co/600x400?text=Alden+975",
        "model_number": "975", "title_raw": "Alden 975 Longwing Blucher Color 8 Shell",
        "last_name": "Barrie", "leather_name": "Shell Cordovan", "color": "Color 8",
        "category": "lwb", "size_us": 10, "width": "D",
        "price_minor": 1250000, "currency": "SEK", "on_sale": False,
        "stock_state": "in_stock", "source_type": "authorized",
        "last_seen_at": datetime.now(UTC).isoformat(),
    },
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_retailers(active_only: bool = True) -> list[dict]:
    client = _client()
    if client is None:
        rows = list(_SAMPLE_RETAILERS)
    else:
        q = client.table("retailers").select("*")
        if active_only:
            q = q.eq("active", True)
        rows = q.order("name").execute().data or []
    if active_only:
        rows = [r for r in rows if r.get("active", True)]
    return rows


def upsert_retailer(retailer: Retailer) -> int:
    """Insert or update a retailer by name. Returns its id."""
    client = _client()
    if client is None:
        for r in _SAMPLE_RETAILERS:
            if r["name"] == retailer.name:
                return r["id"]
        new_id = max((r["id"] for r in _SAMPLE_RETAILERS), default=0) + 1
        _SAMPLE_RETAILERS.append({**retailer.model_dump(mode="json"), "id": new_id})
        return new_id
    payload = retailer.model_dump(mode="json", exclude={"id"})
    res = client.table("retailers").upsert(payload, on_conflict="name").execute()
    return res.data[0]["id"]


def upsert_products(products: list[dict]) -> int:
    """Upsert products by (retailer_id, url). Returns count upserted."""
    if not products:
        return 0
    client = _client()
    if client is None:
        existing = {(p["retailer_id"], p["url"]): p for p in _SAMPLE_PRODUCTS}
        now = datetime.now(UTC).isoformat()
        for p in products:
            key = (p["retailer_id"], p["url"])
            p.setdefault("first_seen_at", now)
            p["last_seen_at"] = now
            p["last_checked_at"] = now
            if key in existing:
                existing[key].update(p)
            else:
                p["id"] = max((x["id"] for x in _SAMPLE_PRODUCTS), default=0) + 1
                _SAMPLE_PRODUCTS.append(p)
        return len(products)
    res = client.table("products").upsert(products, on_conflict="retailer_id,url").execute()
    return len(res.data or [])


def mark_products_unseen(retailer_id: int, keep_urls: set[str]) -> None:
    """Flip stock_state to out_of_stock for products not in keep_urls this run."""
    client = _client()
    if client is None:
        for p in _SAMPLE_PRODUCTS:
            if p["retailer_id"] == retailer_id and p["url"] not in keep_urls:
                p["stock_state"] = "out_of_stock"
        return
    rows = client.table("products").select("id,url").eq("retailer_id", retailer_id).execute().data or []
    stale = [r["id"] for r in rows if r["url"] not in keep_urls]
    if stale:
        client.table("products").update({"stock_state": "out_of_stock"}).in_("id", stale).execute()


def start_scrape_run(retailer_id: int) -> int | None:
    client = _client()
    now = datetime.now(UTC).isoformat()
    if client is None:
        return None
    res = client.table("scrape_runs").insert(
        {"retailer_id": retailer_id, "started_at": now, "status": "running"}
    ).execute()
    client.table("retailers").update(
        {"last_scrape_started_at": now, "last_scrape_status": "running"}
    ).eq("id", retailer_id).execute()
    return res.data[0]["id"] if res.data else None


def finish_scrape_run(
    run_id: int | None,
    retailer_id: int,
    status: str,
    product_count: int,
    error: str | None = None,
) -> None:
    client = _client()
    now = datetime.now(UTC).isoformat()
    if client is None:
        for r in _SAMPLE_RETAILERS:
            if r["id"] == retailer_id:
                r["last_scrape_finished_at"] = now
                r["last_scrape_status"] = status
                r["last_scrape_product_count"] = product_count
                r["last_scrape_error"] = error
        return
    if run_id is not None:
        client.table("scrape_runs").update(
            {"finished_at": now, "status": status, "product_count": product_count, "error": error}
        ).eq("id", run_id).execute()
    client.table("retailers").update(
        {
            "last_scrape_finished_at": now,
            "last_scrape_status": status,
            "last_scrape_product_count": product_count,
            "last_scrape_error": error,
        }
    ).eq("id", retailer_id).execute()


def recent_scrape_runs(limit: int = 50) -> list[ScrapeRun]:
    client = _client()
    if client is None:
        return []
    rows = (
        client.table("scrape_runs")
        .select("*")
        .order("started_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    return [ScrapeRun(**r) for r in rows]


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def _matches(p: dict, f: FilterSpec, retailers_by_id: dict[int, dict]) -> bool:
    if f.lasts and (p.get("last_name") or "").lower() not in {x.lower() for x in f.lasts}:
        return False
    if f.sizes_us and (p.get("size_us") not in f.sizes_us):
        return False
    if f.widths and (p.get("width") or "").upper() not in {w.upper() for w in f.widths}:
        return False
    if f.leathers and (p.get("leather_name") or "").lower() not in {x.lower() for x in f.leathers}:
        return False
    if f.colors and (p.get("color") or "").lower() not in {x.lower() for x in f.colors}:
        return False
    if f.categories and (p.get("category") or "").lower() not in {x.lower() for x in f.categories}:
        return False
    if f.source_types and (p.get("source_type") or "") not in f.source_types:
        return False
    if f.stock_states and (p.get("stock_state") or "") not in f.stock_states:
        return False
    if f.retailer_ids and p.get("retailer_id") not in f.retailer_ids:
        return False
    if f.countries:
        r = retailers_by_id.get(p.get("retailer_id"))
        if not r or r.get("country") not in f.countries:
            return False
    if f.model_number and (p.get("model_number") or "") != f.model_number:
        return False
    if f.on_sale and not p.get("on_sale"):
        return False
    if f.q:
        needle = f.q.lower()
        hay = " ".join(
            str(p.get(k) or "") for k in ("title_raw", "model_number", "last_name", "leather_name", "color")
        ).lower()
        if needle not in hay:
            return False
    return True


def search(f: FilterSpec, limit: int = 200) -> list[dict]:
    retailers = list_retailers(active_only=False)
    retailers_by_id = {r["id"]: r for r in retailers}
    client = _client()
    if client is None:
        rows = [p for p in _SAMPLE_PRODUCTS if _matches(p, f, retailers_by_id)]
    else:
        # Do broad filtering server-side; refine the rest in Python.
        q = client.table("products").select("*").neq("stock_state", "out_of_stock")
        if f.lasts:
            q = q.in_("last_name", f.lasts)
        if f.widths:
            q = q.in_("width", [w.upper() for w in f.widths])
        if f.sizes_us:
            q = q.in_("size_us", f.sizes_us)
        if f.source_types:
            q = q.in_("source_type", f.source_types)
        if f.stock_states:
            q = q.in_("stock_state", f.stock_states)
        if f.retailer_ids:
            q = q.in_("retailer_id", f.retailer_ids)
        if f.model_number:
            q = q.eq("model_number", f.model_number)
        if f.on_sale:
            q = q.eq("on_sale", True)
        rows = q.limit(limit * 3).execute().data or []
        rows = [p for p in rows if _matches(p, f, retailers_by_id)]

    for p in rows:
        p["_retailer"] = retailers_by_id.get(p.get("retailer_id"), {})

    if f.sort == "price_asc":
        rows.sort(key=lambda p: p.get("price_minor") or 0)
    elif f.sort == "price_desc":
        rows.sort(key=lambda p: -(p.get("price_minor") or 0))
    elif f.sort == "retailer":
        rows.sort(key=lambda p: (p["_retailer"].get("name") or "").lower())
    else:  # "new"
        rows.sort(key=lambda p: p.get("last_seen_at") or "", reverse=True)

    return rows[:limit]


# ---------------------------------------------------------------------------
# Home-page modules
# ---------------------------------------------------------------------------


def _attach_retailers(rows: list[dict]) -> list[dict]:
    retailers_by_id = {r["id"]: r for r in list_retailers(active_only=False)}
    for p in rows:
        p["_retailer"] = retailers_by_id.get(p.get("retailer_id"), {})
    return rows


def get_new_arrivals(days: int = 7, limit: int = 12) -> list[dict]:
    """Products whose first_seen_at falls within the last `days` days."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    client = _client()
    if client is None:
        rows = [
            p for p in _SAMPLE_PRODUCTS
            if p.get("stock_state") != "out_of_stock"
            and (p.get("first_seen_at") or p.get("last_seen_at") or "") >= cutoff.isoformat()
        ]
    else:
        rows = (
            client.table("products")
            .select("*")
            .gte("first_seen_at", cutoff.isoformat())
            .neq("stock_state", "out_of_stock")
            .order("first_seen_at", desc=True)
            .limit(limit)
            .execute()
            .data
            or []
        )
    rows.sort(key=lambda p: p.get("first_seen_at") or p.get("last_seen_at") or "", reverse=True)
    return _attach_retailers(rows[:limit])


def get_just_sold_out(hours: int = 48, limit: int = 8) -> list[dict]:
    """Products that flipped to out_of_stock in the last `hours` hours."""
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    client = _client()
    if client is None:
        rows = [
            p for p in _SAMPLE_PRODUCTS
            if p.get("stock_state") == "out_of_stock"
            and (p.get("last_checked_at") or "") >= cutoff.isoformat()
        ]
    else:
        rows = (
            client.table("products")
            .select("*")
            .eq("stock_state", "out_of_stock")
            .gte("last_checked_at", cutoff.isoformat())
            .order("last_checked_at", desc=True)
            .limit(limit)
            .execute()
            .data
            or []
        )
    return _attach_retailers(rows[:limit])


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


def save_alert(email: str, filter_spec: FilterSpec) -> bool:
    """Persist an alert subscription. Returns True on success.

    In sample mode (no DB), this is a no-op that returns False so the UI can
    surface "alerts require a configured database" rather than silently
    pretending to work.
    """
    client = _client()
    if client is None:
        return False
    try:
        client.table("alerts").insert(
            {
                "email": email.strip().lower(),
                "filter_json": filter_spec.model_dump(mode="json"),
                "active": True,
            }
        ).execute()
        return True
    except Exception as e:
        log.warning("save_alert failed: %s", e)
        return False
