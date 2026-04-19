"""Sidebar filter widget bound to FilterSpec and query params."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import yaml

from alden_finder.core import db
from alden_finder.core.models import FilterSpec

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _names(path: Path, key: str = "name") -> list[str]:
    rows = yaml.safe_load(path.read_text()) or []
    return [r[key] for r in rows]


def _qp_list(name: str) -> list[str]:
    val = st.query_params.get(name)
    if not val:
        return []
    if isinstance(val, list):
        return val
    return [v for v in val.split(",") if v]


def _write_qp(spec: FilterSpec) -> None:
    qp: dict[str, str] = {}
    if spec.lasts:
        qp["last"] = ",".join(spec.lasts)
    if spec.sizes_us:
        qp["size"] = ",".join(str(s) for s in spec.sizes_us)
    if spec.widths:
        qp["width"] = ",".join(spec.widths)
    if spec.leathers:
        qp["leather"] = ",".join(spec.leathers)
    if spec.colors:
        qp["color"] = ",".join(spec.colors)
    if spec.categories:
        qp["cat"] = ",".join(spec.categories)
    if spec.countries:
        qp["country"] = ",".join(spec.countries)
    if spec.source_types:
        qp["source"] = ",".join(spec.source_types)
    if spec.stock_states:
        qp["stock"] = ",".join(spec.stock_states)
    if spec.model_number:
        qp["model"] = spec.model_number
    if spec.on_sale:
        qp["sale"] = "1"
    if spec.display_currency != "USD":
        qp["ccy"] = spec.display_currency
    if spec.q:
        qp["q"] = spec.q
    if spec.sort != "new":
        qp["sort"] = spec.sort
    st.query_params.clear()
    for k, v in qp.items():
        st.query_params[k] = v


ALL_SIZES = [float(s) / 2 for s in range(10, 33)]   # 5.0 .. 16.0
ALL_WIDTHS = ["A", "B", "C", "D", "E", "EE", "EEE"]
ALL_CATEGORIES = ["boot", "chukka", "indy", "oxford", "blucher", "loafer", "tassel", "lwb", "saddle", "slipper"]
ALL_SOURCE = ["authorized", "seconds", "mto", "resale"]
ALL_STOCK = ["in_stock", "preorder", "mto", "seconds", "pre_owned"]
DISPLAY_CCYS = ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "KRW", "SEK"]


def render() -> FilterSpec:
    """Render the sidebar and return the FilterSpec the user selected."""
    lasts = _names(DATA_DIR / "lasts.yaml")
    leathers = _names(DATA_DIR / "leathers.yaml")
    colors = _names(DATA_DIR / "colors.yaml")
    retailers = db.list_retailers(active_only=False)
    countries = sorted({r["country"] for r in retailers})

    with st.sidebar:
        st.markdown("### Find Alden")
        q = st.text_input(
            "Search",
            value=st.query_params.get("q", "") or "",
            placeholder="e.g. 405 Color 8 Indy",
        )
        model = st.text_input(
            "Model number",
            value=st.query_params.get("model", "") or "",
            placeholder="405, 990, 975 …",
        )

        sel_lasts = st.multiselect("Last", lasts, default=_qp_list("last"))
        sel_sizes_raw = st.multiselect(
            "US size",
            [f"{s:g}" for s in ALL_SIZES],
            default=_qp_list("size"),
        )
        sel_sizes = [float(s) for s in sel_sizes_raw]
        sel_widths = st.multiselect("Width", ALL_WIDTHS, default=_qp_list("width"))
        sel_leathers = st.multiselect("Leather", leathers, default=_qp_list("leather"))
        sel_colors = st.multiselect("Color", colors, default=_qp_list("color"))
        sel_cats = st.multiselect("Category", ALL_CATEGORIES, default=_qp_list("cat"))

        st.markdown("### Source")
        sel_sources = st.multiselect("Source type", ALL_SOURCE, default=_qp_list("source") or ALL_SOURCE)
        sel_stock = st.multiselect(
            "Stock state",
            ALL_STOCK,
            default=_qp_list("stock") or ["in_stock", "preorder", "mto"],
        )
        on_sale = st.toggle("On sale only", value=bool(st.query_params.get("sale")))

        st.markdown("### Geography")
        sel_countries = st.multiselect("Country", countries, default=_qp_list("country"))

        st.markdown("### Display")
        ccy = st.selectbox(
            "Show prices in",
            DISPLAY_CCYS,
            index=DISPLAY_CCYS.index(st.query_params.get("ccy", "USD")) if st.query_params.get("ccy") in DISPLAY_CCYS else 0,
        )
        sort = st.selectbox(
            "Sort",
            ["new", "price_asc", "price_desc", "retailer"],
            index=["new", "price_asc", "price_desc", "retailer"].index(
                st.query_params.get("sort", "new")
            )
            if st.query_params.get("sort") in {"new", "price_asc", "price_desc", "retailer"}
            else 0,
            format_func=lambda s: {
                "new": "Recently added",
                "price_asc": "Price: low → high",
                "price_desc": "Price: high → low",
                "retailer": "Retailer name",
            }[s],
        )

    spec = FilterSpec(
        lasts=sel_lasts,
        sizes_us=sel_sizes,
        widths=sel_widths,
        leathers=sel_leathers,
        colors=sel_colors,
        categories=sel_cats,
        countries=sel_countries,
        source_types=sel_sources,
        stock_states=sel_stock,
        model_number=model or None,
        on_sale=on_sale,
        display_currency=ccy,
        q=q or None,
        sort=sort,
    )
    _write_qp(spec)
    return spec
