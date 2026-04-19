"""Back-in-stock alert subscribe form.

Persists the user's current `FilterSpec` + email to the `alerts` table.
A separate worker (not yet written) consumes this table and sends email
notifications when new products matching a filter appear.
"""

from __future__ import annotations

import re

import streamlit as st

from alden_finder.core import db
from alden_finder.core.models import FilterSpec

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def render(current_spec: FilterSpec) -> None:
    with st.expander("🔔 Notify me when matching Alden comes in stock", expanded=False):
        st.caption(
            "We'll email you when a product matching your current filters appears. "
            "One click to unsubscribe (link in every email). Alerts require a configured "
            "database — if you're seeing the sample-data demo, subscribing is disabled."
        )
        col_e, col_b = st.columns([4, 1])
        with col_e:
            email = st.text_input(
                "Email",
                key="alert_email",
                placeholder="you@example.com",
                label_visibility="collapsed",
            )
        with col_b:
            submit = st.button("Subscribe", use_container_width=True)

        if submit:
            if not email or not _EMAIL_RE.match(email):
                st.error("Enter a valid email address.")
                return
            ok = db.save_alert(email, current_spec)
            if ok:
                st.success("Subscribed. Check your inbox to confirm.")
            else:
                st.warning(
                    "Alerts aren't available right now (no database configured). "
                    "Set SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY to enable."
                )
