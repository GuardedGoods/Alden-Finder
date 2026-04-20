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


def _dedupe_batch(products: list[dict]) -> list[dict]:
    """Collapse rows that share (retailer_id, retailer_sku), keeping the last.

    Supabase's upsert compiles to a single INSERT ... ON CONFLICT statement
    which Postgres rejects if the same conflict target appears twice in the
    same statement (cardinality_violation). Shopify variants legitimately
    share a product URL, so the adapter may yield the same product key
    within one batch — dedupe before sending.
    """
    dedup: dict[tuple, dict] = {}
    for p in products:
        sku = p.get("retailer_sku") or ""
        key = (p.get("retailer_id"), sku)
        dedup[key] = p
    return list(dedup.values())


def upsert_products(products: list[dict]) -> int:
    """Upsert products by (retailer_id, retailer_sku). Returns count upserted."""
    if not products:
        return 0
    products = _dedupe_batch(products)
    client = _client()
    if client is None:
        existing = {(p["retailer_id"], p.get("retailer_sku")): p for p in _SAMPLE_PRODUCTS}
        now = datetime.now(UTC).isoformat()
        for p in products:
            key = (p["retailer_id"], p.get("retailer_sku"))
            p.setdefault("first_seen_at", now)
            p["last_seen_at"] = now
            p["last_checked_at"] = now
            if key in existing:
                existing[key].update(p)
            else:
                p["id"] = max((x["id"] for x in _SAMPLE_PRODUCTS), default=0) + 1
                _SAMPLE_PRODUCTS.append(p)
        return len(products)
    res = client.table("products").upsert(
        products, on_conflict="retailer_id,retailer_sku"
    ).execute()
    return len(res.data or [])


def mark_products_unseen(retailer_id: int, keep_skus: set[str]) -> None:
    """Flip stock_state to out_of_stock for products not in keep_skus this run."""
    client = _client()
    if client is None:
        for p in _SAMPLE_PRODUCTS:
            if p["retailer_id"] == retailer_id and p.get("retailer_sku") not in keep_skus:
                p["stock_state"] = "out_of_stock"
        return
    rows = (
        client.table("products")
        .select("id,retailer_sku")
        .eq("retailer_id", retailer_id)
        .execute()
        .data
        or []
    )
    stale = [r["id"] for r in rows if r.get("retailer_sku") not in keep_skus]
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
# Grouped search — one card per product listing, not per variant.
# ---------------------------------------------------------------------------

_FOOTWEAR_CATEGORIES = {
    "boot", "chukka", "indy", "oxford", "blucher",
    "loafer", "tassel", "lwb", "saddle", "slipper",
}


def _variant_label(size: float | int | None, width: str | None) -> str:
    if size is None and not width:
        return ""
    if size is None:
        return (width or "").upper()
    return f"{size:g}{(width or '').upper()}"


def search_grouped(f: FilterSpec, limit: int = 80, footwear_only: bool = True) -> list[dict]:
    """Return one listing per (retailer_id, url), aggregating variants.

    Strategy:
      1. Run the full search WITHOUT the size/width filters so each group has
         its full set of variants. The original filter restrictions on last,
         leather, color, country, etc. still apply.
      2. Group by (retailer_id, url).
      3. For each group, compute:
           - a representative row (title, image, price, last, etc.)
           - variants: [{size_us, width, stock_state, retailer_sku, price_minor}]
           - sizes_available: sorted list of "10D", "10.5D" strings (in stock)
           - all_variants: same list including out-of-stock
           - matched_size_in_stock / matched_label: reflecting the user's size+width
             filter if one was supplied
      4. If the user supplied size or width filters, drop groups where their
         size/width combo isn't in stock.
      5. Optionally drop groups whose category isn't footwear (default on).
    """
    # Copy-minus sizes/widths so we can attach full variant context.
    unrestricted = FilterSpec(**{
        **f.model_dump(),
        "sizes_us": [],
        "widths": [],
    })
    raw = search(unrestricted, limit=limit * 12)  # headroom for grouping

    groups: dict[tuple, dict] = {}
    for p in raw:
        key = (p.get("retailer_id"), p.get("url"))
        g = groups.get(key)
        if g is None:
            g = {
                **{k: p.get(k) for k in (
                    "retailer_id", "url", "image_url", "title_raw",
                    "last_name", "leather_name", "color", "category",
                    "model_number", "currency", "source_type", "on_sale",
                    "first_seen_at", "last_seen_at", "last_checked_at",
                )},
                "_retailer": p.get("_retailer", {}),
                "variants": [],
                "price_min_minor": None,
                "price_max_minor": None,
            }
            groups[key] = g
        variant = {
            "retailer_sku": p.get("retailer_sku"),
            "size_us": p.get("size_us"),
            "width": p.get("width"),
            "stock_state": p.get("stock_state"),
            "price_minor": p.get("price_minor"),
        }
        g["variants"].append(variant)
        pm = p.get("price_minor")
        if pm is not None:
            g["price_min_minor"] = min(g["price_min_minor"], pm) if g["price_min_minor"] is not None else pm
            g["price_max_minor"] = max(g["price_max_minor"], pm) if g["price_max_minor"] is not None else pm

    wanted_sizes = set(f.sizes_us)
    wanted_widths = {w.upper() for w in f.widths}

    out: list[dict] = []
    for g in groups.values():
        if footwear_only and (g.get("category") or "other") not in _FOOTWEAR_CATEGORIES:
            continue

        in_stock = [v for v in g["variants"] if v.get("stock_state") == "in_stock"]
        g["sizes_available"] = sorted(
            {_variant_label(v["size_us"], v["width"]) for v in in_stock if v.get("size_us")}
        )
        g["n_sizes_in_stock"] = len(g["sizes_available"])
        g["n_variants"] = len(g["variants"])

        matched: list[str] = []
        for v in in_stock:
            s_ok = (not wanted_sizes) or (v.get("size_us") in wanted_sizes)
            w_ok = (not wanted_widths) or ((v.get("width") or "").upper() in wanted_widths)
            if s_ok and w_ok:
                matched.append(_variant_label(v["size_us"], v["width"]))

        # If the user asked for specific sizes/widths, hide listings that
        # don't have that combo in stock.
        if wanted_sizes or wanted_widths:
            if not matched:
                continue
            g["matched_label"] = ", ".join(sorted(set(matched)))
            g["matched_in_stock"] = True
        else:
            g["matched_label"] = ""
            g["matched_in_stock"] = None

        # Representative price = min variant price.
        g["price_minor"] = g["price_min_minor"]
        out.append(g)

    # Sorting (reuse semantics of `search`).
    if f.sort == "price_asc":
        out.sort(key=lambda g: g.get("price_minor") or 0)
    elif f.sort == "price_desc":
        out.sort(key=lambda g: -(g.get("price_minor") or 0))
    elif f.sort == "retailer":
        out.sort(key=lambda g: (g["_retailer"].get("name") or "").lower())
    else:
        out.sort(key=lambda g: g.get("last_seen_at") or "", reverse=True)

    return out[:limit]


# ---------------------------------------------------------------------------
# Home-page modules
# ---------------------------------------------------------------------------


def _attach_retailers(rows: list[dict]) -> list[dict]:
    retailers_by_id = {r["id"]: r for r in list_retailers(active_only=False)}
    for p in rows:
        p["_retailer"] = retailers_by_id.get(p.get("retailer_id"), {})
    return rows


def get_new_arrivals(days: int = 7, limit: int = 12, footwear_only: bool = True) -> list[dict]:
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
            .limit(limit * 6)
            .execute()
            .data
            or []
        )
    if footwear_only:
        rows = [r for r in rows if (r.get("category") or "other") in _FOOTWEAR_CATEGORIES]
    # Dedupe by (retailer_id, url) so we don't show four variants of the same shoe.
    seen: set[tuple] = set()
    unique: list[dict] = []
    for r in rows:
        key = (r.get("retailer_id"), r.get("url"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    unique.sort(key=lambda p: p.get("first_seen_at") or p.get("last_seen_at") or "", reverse=True)
    return _attach_retailers(unique[:limit])


def get_just_sold_out(hours: int = 48, limit: int = 8, footwear_only: bool = True) -> list[dict]:
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
            .limit(limit * 6)
            .execute()
            .data
            or []
        )
    if footwear_only:
        rows = [r for r in rows if (r.get("category") or "other") in _FOOTWEAR_CATEGORIES]
    # Dedupe by URL.
    seen: set[tuple] = set()
    unique: list[dict] = []
    for r in rows:
        key = (r.get("retailer_id"), r.get("url"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    return _attach_retailers(unique[:limit])


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
