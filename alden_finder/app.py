"""Alden Finder — Streamlit entry point."""

from __future__ import annotations

import streamlit as st

from alden_finder.core import db
from alden_finder.ui import alerts, cards, filters, guide, home, status
from alden_finder.ui.style import CSS

_VIEWS = ("search", "status", "guide", "about")

st.set_page_config(
    page_title="Alden Finder",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": (
            "Alden Finder is a free, non-profit project that aggregates publicly listed "
            "Alden footwear across authorized retailers. It is unaffiliated with Alden "
            "Shoe Company. Every listing deep-links to the retailer. "
            "Code: https://github.com/guardedgoods/alden-finder"
        ),
    },
)

st.markdown(CSS, unsafe_allow_html=True)

# Navigation (top-level tabs). Streamlit multipage would also work, but a
# single-file layout keeps mobile rendering predictable.
tab = st.query_params.get("view", "search")

cols = st.columns([4, 1])
with cols[0]:
    st.title("Alden Finder")
    st.caption("In-stock Alden footwear across authorized retailers worldwide.")
with cols[1]:
    view_choice = st.radio(
        "View",
        _VIEWS,
        index=_VIEWS.index(tab) if tab in _VIEWS else 0,
        horizontal=True,
        label_visibility="collapsed",
    )
if view_choice != tab:
    st.query_params["view"] = view_choice
    tab = view_choice


if tab == "status":
    status.render()
elif tab == "guide":
    guide.render()
elif tab == "about":
    st.markdown(
        """
### About

**Alden Finder** aggregates publicly available Alden footwear inventory from
authorized retailers worldwide. It is a volunteer, non-profit project. Every
search result deep-links to the retailer's own product page — we don't sell
anything ourselves.

**How it works.** A scheduled job scrapes each retailer's public catalog once
an hour and writes a normalized product index. The app reads from that index,
so searches are fast and we don't hammer retailer sites.

**Ethics.** We respect each site's `robots.txt`, rate-limit our crawlers, and
identify ourselves with a transparent User-Agent and contact link. Retailers
that would like to be removed can open a GitHub issue or email us — we'll
flip the `active` flag and stop scraping immediately.

**Disclaimer.** This site is unaffiliated with Alden Shoe Company. Retailer
authorization can change at any time; the official Alden dealer list at
<https://www.aldenshoe.com> is the source of truth.

**Contribute a retailer.** [Open a suggestion issue](https://github.com/guardedgoods/alden-finder/issues/new?template=retailer-suggestion.yml) or PR [`data/retailers.yaml`](https://github.com/guardedgoods/alden-finder/blob/main/data/retailers.yaml) directly.

**Dealer opt-out.** Email via a GitHub issue and we'll flip `active: false` on the next scheduled run.
        """
    )
else:
    spec = filters.render()
    home.render_new_arrivals(display_ccy=spec.display_currency, limit=6)
    products = db.search(spec, limit=240)
    st.markdown(f"**{len(products)}** matching listings")
    cards.render_grid(products, display_ccy=spec.display_currency, cols=3)
    alerts.render(spec)
    home.render_just_sold_out(display_ccy=spec.display_currency, limit=4)

st.divider()
st.caption(
    "Unaffiliated with Alden Shoe Company · All photography and pricing remains the "
    "property of the respective retailer · "
    "[source code](https://github.com/guardedgoods/alden-finder)"
)
