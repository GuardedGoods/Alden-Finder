# Alden Finder

A free, non-profit Streamlit web app that aggregates publicly listed Alden
footwear across authorized retailers worldwide. Filter by last, US size,
width, leather, color, country, and source (authorized / factory seconds /
MTO / resale). Every result deep-links to the retailer — we drive traffic
to dealers, we never sell anything ourselves.

**Unaffiliated with Alden Shoe Company.** The official Alden dealer list at
<https://www.aldenshoe.com> is the source of truth for authorization.

---

## How it works

```
GitHub Actions (hourly) ──▶ scraper workers ──▶ Supabase (Postgres)
                                                      │
                                                      ▼
                                         Streamlit Cloud (reads only)
```

- One **adapter per retailer** behind a shared interface (`alden_finder/adapters/`).
- A **normalization layer** (`alden_finder/core/normalize.py`) parses titles and
  variant strings into canonical `{last, leather, color, category, size_us, width, model_number}`.
- All scraping is scheduled — user queries hit a warm cache so the UI stays
  under 500 ms on mobile.

## Quick start (local)

```bash
git clone https://github.com/guardedgoods/alden-finder
cd alden-finder
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run the Streamlit UI with the in-memory sample dataset (no DB needed):
streamlit run alden_finder/app.py

# Run one retailer scrape against the live sample store:
python -m alden_finder.scraping.runner --retailer leffot -vv

# Tests
pytest -q
```

The app runs without Supabase credentials — it falls back to an in-memory
sample dataset so first-time contributors see a populated UI immediately.

## Deploy

First-time deployment takes about 25 minutes end-to-end, no credit card
required. Click-by-click walkthrough in **[docs/DEPLOY.md](docs/DEPLOY.md)**,
which covers:

1. **Fork + local smoke test** (5 min) — clone, install, run `streamlit` to
   confirm the sample UI works.
2. **Supabase setup** (5 min) — create a project, run `db/schema.sql` in
   the SQL editor, copy the three API keys, seed the retailer registry
   with a one-liner.
3. **Streamlit Cloud deploy** (3 min) — New app, point at
   `alden_finder/app.py`, paste two secrets.
4. **GitHub Actions secrets + first scrape** (3 min) — add
   `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` as repo secrets, enable
   workflows, trigger the scrape manually.
5. **Email alerts** (optional, 5 min) — Resend account + DNS verification
   + four secret env vars. Skip this and the site still runs; subscribers
   just see a clear "alerts not configured" notice.
6. **Ongoing operations** — adding retailers, dealer opt-out, rescrapes,
   troubleshooting.

Cost model: **$0/month** at launch scale (Supabase free tier handles
30x our storage needs; Streamlit Cloud is free for public apps; GitHub
Actions are free for public repos; Resend free tier is 3,000 emails/month).

## Features

- **Filter** by last · size · width · leather · color · country · source · price · on-sale · retailer.
- **Model-number search** (405, 990, 975, D8810H, …) as a first-class field.
- **Freshness badges** per card and a `/status` page showing the last scrape
  time and product count for every retailer (green < 6 h, yellow < 24 h, red older).
- **Currency conversion** — display prices in USD/EUR/GBP/CAD/AUD/JPY/KRW/SEK
  with the retailer's native price shown in a tooltip.
- **Shareable URLs** — filters are encoded in query params.
- **Mobile-first** — cards collapse to a single column, tap targets ≥44 px.
- **Sitemap**: `search` · `status` · `about`.

### Shipped

- **Back-in-stock email alerts** — inline subscribe form on the search page,
  scheduled dispatch via `alden_finder.alerts.worker`, Resend / SMTP / dry-run
  transports (`.github/workflows/alerts.yml`, hourly at `:30`).
- **Sizing guide page** (`/guide`) with per-last fit notes, known model
  numbers, and a US↔UK↔EU cheat sheet.
- **"Just in" / "Just sold out"** homepage modules.
- **Freshness badges** per card and a `/status` freshness page.

### Coming soon

- RSS / Atom feed per saved filter
- Price-history sparklines on each card
- Resale integration (eBay + Grailed + StyleForum best-effort)

## Add or remove a retailer

Every retailer is declared in [`data/retailers.yaml`](data/retailers.yaml).
Open a PR editing that file — that's it. Each entry supports:

```yaml
- name: Your Shop
  url: https://yourshop.com
  country: US          # ISO-3166 alpha-2
  currency: USD        # ISO-4217
  adapter_key: shopify # "shopify" | "woo" | "static" | <bespoke module name>
  active: true
  rate_limit_s: 2.0
  ships_to: [US, CA]
  source_type: authorized   # authorized | seconds | mto | resale
  notes: optional tooltip text
```

**Dealer opt-out.** Retailers who would like their inventory removed from
Alden Finder can open a GitHub issue. We'll flip `active: false` and the
next scheduled scrape will stop touching the site. Existing cached rows
are purged within 24 h.

## Ethics

- Crawlers respect each site's `robots.txt` (`alden_finder/scraping/robots.py`).
- Per-domain rate limit (≥ 2 s between requests; configurable per retailer).
- Descriptive User-Agent with a contact link.
- We **never re-host** retailer imagery — cards load the retailer's own URL
  so attribution and bandwidth stay with them.
- Every card is a deep link to the retailer's own product page.

## Repository layout

```
alden_finder/
  app.py                # Streamlit entry
  core/
    models.py           # Pydantic models
    normalize.py        # title → canonical fields
    db.py               # Supabase client + search
    fx.py               # currency conversion
  adapters/
    base.py             # RetailerAdapter ABC + ShopifyAdapter + WooAdapter
    <key>.py            # bespoke retailer adapters
  scraping/
    runner.py           # async orchestrator
    robots.py           # robots.txt cache
  ui/
    filters.py cards.py status.py style.py
data/
  retailers.yaml lasts.yaml leathers.yaml colors.yaml
db/schema.sql
tests/
.github/workflows/      # ci.yml + scrape.yml
```

## License

MIT. Attribution appreciated but not required.
