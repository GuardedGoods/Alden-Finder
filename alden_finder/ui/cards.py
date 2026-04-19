"""Product card + freshness badge rendering."""

from __future__ import annotations

import html
from datetime import UTC, datetime

import streamlit as st
from dateutil import parser as dateparser

from alden_finder.core import fx


def _country_badge(code: str | None) -> str:
    if not code:
        return ""
    return (
        f'<span style="display:inline-block;font-size:0.7rem;padding:1px 6px;'
        f'border:1px solid rgba(120,120,120,0.35);border-radius:4px;'
        f'margin-right:4px;opacity:0.8">{html.escape(code.upper())}</span>'
    )


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = dateparser.isoparse(ts) if isinstance(ts, str) else ts
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _humanize(delta_seconds: float) -> str:
    if delta_seconds < 60:
        return "just now"
    if delta_seconds < 3600:
        return f"{int(delta_seconds // 60)}m ago"
    if delta_seconds < 86400:
        return f"{int(delta_seconds // 3600)}h ago"
    return f"{int(delta_seconds // 86400)}d ago"


def freshness_badge(last_scrape: datetime | None) -> str:
    if last_scrape is None:
        return '<span class="af-badge error">no data</span>'
    age = (datetime.now(UTC) - last_scrape).total_seconds()
    label = _humanize(age)
    if age < 6 * 3600:
        cls = "fresh"
    elif age < 24 * 3600:
        cls = "stale"
    else:
        cls = "error"
    return f'<span class="af-badge {cls}">scraped {html.escape(label)}</span>'


def render_card(product: dict, display_ccy: str) -> None:
    retailer = product.get("_retailer") or {}
    price_minor = product.get("price_minor")
    if price_minor is not None and product.get("currency") and product["currency"] != display_ccy:
        converted = fx.convert(price_minor / 100, product["currency"], display_ccy)
        price_label = fx.format_price(round(converted * 100), display_ccy)
        price_label += (
            f' <span style="opacity:0.6;font-weight:400;">'
            f"({fx.format_price(price_minor, product['currency'])})</span>"
        )
    else:
        price_label = fx.format_price(price_minor, product.get("currency") or display_ccy)

    country_badge = _country_badge(retailer.get("country"))
    last_scrape = _parse(retailer.get("last_scrape_finished_at"))
    badge = freshness_badge(last_scrape)

    title = html.escape(product.get("title_raw") or "(untitled)")
    image = product.get("image_url") or "https://placehold.co/600x450?text=Alden"
    url = product.get("url") or "#"
    last = html.escape(product.get("last_name") or "")
    leather = html.escape(product.get("leather_name") or "")
    color = html.escape(product.get("color") or "")
    size = product.get("size_us")
    width = product.get("width") or ""
    stock = product.get("stock_state") or ""
    stock_label = {
        "in_stock": "In stock",
        "preorder": "Pre-order",
        "mto": "MTO",
        "seconds": "Seconds",
        "pre_owned": "Pre-owned",
        "out_of_stock": "Out of stock",
    }.get(stock, stock)

    meta_bits = [b for b in (
        f"Last: {last}" if last else "",
        f"{leather} {color}".strip() if (leather or color) else "",
        f"US {size:g}{width}" if size is not None else (width or ""),
        stock_label,
    ) if b]
    meta = " · ".join(meta_bits)

    retailer_line = f"{country_badge}{html.escape(retailer.get('name') or '')} {badge}"

    st.markdown(
        f"""
        <div class="af-card">
          <a href="{html.escape(url)}" target="_blank" rel="noopener">
            <img src="{html.escape(image)}" alt="{title}" loading="lazy" />
          </a>
          <div class="af-title">{title}</div>
          <div class="af-meta">{html.escape(meta)}</div>
          <div class="af-price">{price_label}</div>
          <div class="af-retailer">{retailer_line}</div>
          <a class="af-buy" href="{html.escape(url)}" target="_blank" rel="noopener">
            Buy at {html.escape(retailer.get('name') or 'retailer')}
          </a>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_grid(products: list[dict], display_ccy: str, cols: int = 3) -> None:
    if not products:
        st.info("No matching Alden products at the moment. Try relaxing the filters.")
        return
    for i in range(0, len(products), cols):
        row = products[i : i + cols]
        columns = st.columns(cols)
        for slot, prod in zip(columns, row, strict=False):
            with slot:
                render_card(prod, display_ccy)
