"""Mobile-first CSS injected via st.markdown.

Keeps the cards responsive, enlarges tap targets, collapses the sidebar into
a bottom sheet on narrow viewports, and applies the light/dark theme.
"""

from __future__ import annotations

CSS = """
<style>
:root {
  --af-card-radius: 14px;
  --af-card-border: rgba(120, 120, 120, 0.22);
  --af-accent: #7a2a28;  /* Color 8 */
}

/* Center the main content and cap width for readability. */
.main .block-container {
  max-width: 1200px;
  padding-top: 1rem;
  padding-bottom: 4rem;
}

/* Cards */
.af-card {
  border: 1px solid var(--af-card-border);
  border-radius: var(--af-card-radius);
  padding: 12px;
  margin-bottom: 16px;
  background: rgba(255, 255, 255, 0.02);
  display: flex;
  flex-direction: column;
  height: 100%;
}
.af-card img {
  border-radius: 8px;
  width: 100%;
  aspect-ratio: 4 / 3;
  object-fit: cover;
  background: #f0ebe6;
}
.af-card .af-title { font-weight: 600; margin-top: 10px; line-height: 1.3; }
.af-card .af-meta { font-size: 0.85rem; opacity: 0.85; margin-top: 4px; }
.af-card .af-price {
  margin-top: 8px;
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--af-accent);
}
.af-card .af-retailer { font-size: 0.8rem; opacity: 0.75; margin-top: 4px; }
.af-card .af-size-hit {
  margin-top: 8px;
  font-size: 0.88rem;
  padding: 6px 10px;
  background: rgba(42, 122, 61, 0.14);
  color: #1f5f2c;
  border-radius: 6px;
  border-left: 3px solid #2a7a3d;
}
.af-card .af-size-list {
  margin-top: 8px;
  font-size: 0.82rem;
  opacity: 0.85;
  line-height: 1.4;
}
.af-card a.af-buy {
  display: inline-block;
  margin-top: auto;
  padding: 12px 14px;      /* >=44px tap target */
  background: var(--af-accent);
  color: white !important;
  text-decoration: none;
  border-radius: 10px;
  text-align: center;
  font-weight: 600;
}
.af-card a.af-buy:hover { filter: brightness(1.08); }

/* Freshness badges */
.af-badge {
  display: inline-block;
  font-size: 0.72rem;
  padding: 2px 8px;
  border-radius: 999px;
  margin-left: 6px;
  vertical-align: middle;
}
.af-badge.fresh  { background: #2a7a3d33; color: #2a7a3d; }
.af-badge.stale  { background: #b88c2f33; color: #8a6820; }
.af-badge.error  { background: #a9333333; color: #a93333; }

/* Mobile: single column, sticky filter button */
@media (max-width: 640px) {
  .main .block-container { padding-left: 0.5rem; padding-right: 0.5rem; }
  [data-testid="stSidebar"] { min-width: 80vw !important; width: 80vw !important; }
}
</style>
"""
