"""`/guide` view: per-last sizing and fit notes sourced from data/lasts.yaml."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import yaml

DATA = Path(__file__).resolve().parents[2] / "data" / "lasts.yaml"


def render() -> None:
    st.header("Alden sizing guide")
    st.caption(
        "Fit notes per last, compiled from public sources (retailer pages, "
        "StyleForum threads, the Alden FAQ). Use these as a starting point — "
        "always confirm with your retailer before committing to a purchase."
    )

    lasts = yaml.safe_load(DATA.read_text()) or []

    for entry in lasts:
        with st.expander(entry["name"], expanded=False):
            notes = entry.get("fit_notes") or "—"
            st.markdown(f"**Fit.** {notes}")
            models = entry.get("models") or []
            if models:
                st.markdown("**Known models on this last:** " + ", ".join(f"`{m}`" for m in models))
            aliases = entry.get("aliases") or []
            if aliases:
                st.caption("Aliases matched in product titles: " + ", ".join(aliases))

    st.divider()
    st.markdown(
        "### Size conversion cheat sheet\n"
        "| US | UK  | EU   |\n"
        "|----|-----|------|\n"
        "| 7  | 6   | 39.5 |\n"
        "| 8  | 7   | 40.5 |\n"
        "| 9  | 8   | 42   |\n"
        "| 10 | 9   | 43   |\n"
        "| 11 | 10  | 44   |\n"
        "| 12 | 11  | 45   |\n"
        "\n"
        "These are approximate — Alden US sizes generally correspond to 1 full size "
        "smaller UK and ~3 sizes larger EU."
    )
