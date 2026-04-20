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
    price_max = product.get("price_max_minor")
    currency = product.get("currency") or display_ccy

    def _fmt_converted(minor: int) -> str:
        if currency and currency != display_ccy:
            converted = fx.convert(minor / 100, currency, display_ccy)
            return (
                f'{fx.format_price(round(converted * 100), display_ccy)}'
                f' <span style="opacity:0.6;font-weight:400;">'
                f"({fx.format_price(minor, currency)})</span>"
            )
        return fx.format_price(minor, currency)

    if price_minor is None:
        price_label = "—"
    elif price_max and price_max > price_minor:
        price_label = f"from {_fmt_converted(price_minor)}"
    else:
        price_label = _fmt_converted(price_minor)

    country_badge = _country_badge(retailer.get("country"))
    last_scrape = _parse(retailer.get("last_scrape_finished_at"))
    badge = freshness_badge(last_scrape)

    title = html.escape(product.get("title_raw") or "(untitled)")
    image = product.get("image_url") or "https://placehold.co/600x450?text=Alden"
    url = product.get("url") or "#"
    last = html.escape(product.get("last_name") or "")
    leather = html.escape(product.get("leather_name") or "")
    color = html.escape(product.get("color") or "")

    # Grouped listings carry variants/matched_label/sizes_available. Flat
    # per-variant rows (used by "Just in" / "Just sold out") don't.
    sizes_available = product.get("sizes_available") or []
    matched_label = product.get("matched_label") or ""
    matched_in_stock = product.get("matched_in_stock")
    n_sizes = product.get("n_sizes_in_stock")

    if matched_in_stock and matched_label:
        size_line = (
            f'<div class="af-size-hit">Your size <b>US {html.escape(matched_label)}</b> '
            f'is in stock</div>'
        )
    elif sizes_available:
        shown = sizes_available[:8]
        more = len(sizes_available) - len(shown)
        rest = f" (+{more} more)" if more > 0 else ""
        size_line = (
            f'<div class="af-size-list"><b>{n_sizes}</b> size'
            f'{"s" if (n_sizes or 0) != 1 else ""} in stock: '
            f'{html.escape(", ".join("US " + s for s in shown))}{rest}</div>'
        )
    else:
        # Flat row path — keep the original per-variant label.
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
        parts = [
            f"US {size:g}{width}" if size is not None else (width or ""),
            stock_label,
        ]
        size_line = f'<div class="af-meta">{html.escape(" · ".join(p for p in parts if p))}</div>'

    meta_bits = [b for b in (
        f"Last: {last}" if last else "",
        f"{leather} {color}".strip() if (leather or color) else "",
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
          {size_line}
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
