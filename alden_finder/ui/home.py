"""Homepage modules rendered above the filtered search grid."""

from __future__ import annotations

import streamlit as st

from alden_finder.core import db
from alden_finder.ui.cards import render_card


def render_new_arrivals(display_ccy: str, limit: int = 6) -> None:
    rows = db.get_new_arrivals(days=7, limit=limit)
    if not rows:
        return
    st.subheader(f"🆕 Just in — last 7 days ({len(rows)})")
    cols = st.columns(min(len(rows), 3))
    for slot, prod in zip(cols, rows, strict=False):
        with slot:
            render_card(prod, display_ccy)


def render_just_sold_out(display_ccy: str, limit: int = 4) -> None:
    rows = db.get_just_sold_out(hours=48, limit=limit)
    if not rows:
        return
    with st.expander(f"Just sold out — last 48 h ({len(rows)})", expanded=False):
        cols = st.columns(min(len(rows), 4))
        for slot, prod in zip(cols, rows, strict=False):
            with slot:
                render_card(prod, display_ccy)
