# Deploy Alden Finder

One-shot setup. Expect ~15 minutes end-to-end if you already have a GitHub
account. Everything below runs on free tiers.

---

## 1. Fork & clone

Fork <https://github.com/guardedgoods/alden-finder> into your own account, then:

```bash
git clone git@github.com:<you>/alden-finder.git
cd alden-finder
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q           # sanity check
```

## 2. Supabase (free tier → database)

1. Create an account at <https://supabase.com> and a new project (any region).
2. Copy the project URL and the **anon** and **service_role** keys from
   *Settings → API*.
3. Apply the schema:

   ```bash
   # Option A — from the CLI (needs the db password):
   psql "$SUPABASE_DB_URL" -f db/schema.sql

   # Option B — dashboard: paste db/schema.sql into the SQL editor and run.
   ```

4. (Optional) Pre-seed the retailers table from `data/retailers.yaml`:

   ```bash
   export SUPABASE_URL="https://xxxxx.supabase.co"
   export SUPABASE_SERVICE_ROLE_KEY="eyJ..."
   python -c "from alden_finder.scraping.runner import load_registry, sync_registry_to_db; sync_registry_to_db(load_registry())"
   ```

## 3. Streamlit Cloud (UI)

1. Sign in at <https://share.streamlit.io> with GitHub.
2. **New app** → pick your fork → `alden_finder/app.py`.
3. *Advanced settings → Secrets*, paste:

   ```toml
   SUPABASE_URL = "https://xxxxx.supabase.co"
   SUPABASE_KEY = "eyJ...anon-key..."
   ```

4. Deploy. The UI will come up against the Supabase read-only anon role — no
   scraping happens from the UI process.

## 4. GitHub Actions (scraper + alerts)

Add repository secrets in *Settings → Secrets and variables → Actions → New repository secret*:

| Secret                         | Required | Purpose |
|--------------------------------|----------|---------|
| `SUPABASE_URL`                 | Yes      | Scrape + alert workers need write access. |
| `SUPABASE_SERVICE_ROLE_KEY`    | Yes      | Same — server-side only. |
| `RESEND_API_KEY`               | Optional | Preferred email transport for alerts. Free tier at <https://resend.com>. |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` | Optional | Fallback email transport. |
| `ALERT_FROM_EMAIL`             | Optional | Defaults to `alerts@alden-finder.example`; set this to a domain you control. |
| `ALERT_FROM_NAME`              | Optional | Display name on outbound mail. |
| `ALERT_UNSUBSCRIBE_URL`        | Optional | Link included in every email footer. |

Then enable Actions on the repo (Actions tab → *I understand my workflows, go ahead and enable them*). The workflows will start on schedule:

- `scrape.yml` — `:07` every hour.
- `alerts.yml` — `:30` every hour (runs 23 min after the scrape).
- `ci.yml` — on every push / PR.

Trigger a first run manually: Actions → *Scrape retailers* → *Run workflow*.

## 5. Verify

Within ~10 minutes of the first successful scrape:

- `/status` in the Streamlit UI lists your retailers with recent
  `last_scrape_finished_at` timestamps and non-zero product counts.
- Hit the search view; filter by `Last = Barrie, Width = D` — you should get
  hits from Leffot, Skoaktiebolaget, etc.
- Subscribe a test email via the *🔔 Notify me* expander. Check that the row
  lands in Supabase's `alerts` table.
- Manually trigger *Back-in-stock alerts* with *Run workflow → dry_run: true*
  and confirm the workflow log shows your test subscription.

## 6. Ongoing

- **Add a retailer**: PR `data/retailers.yaml`. CI validates the file.
- **Remove a retailer** (dealer opt-out): flip `active: false` in the same file.
- **Break-glass rescrape**: Actions → *Scrape retailers* → *Run workflow* with
  an optional `retailer` substring.
- **Reset a subscriber**: `UPDATE alerts SET active=false WHERE email='x@y.z';`
  — or add a real unsubscribe endpoint (see open issues).

---

### Cost model

At the seeded scale (66 retailers, hourly scrape, hundreds of products) this
runs comfortably within the Supabase free tier (500 MB, 2 GB egress/month)
and Streamlit Community Cloud free tier. Resend free tier handles 100 emails/day
and 3 000/month, which is more than enough for early alerts. No paid services
are required.

### Security notes

- The `alerts` table has no public RLS policy — only the service role can
  read it. Subscriber emails are never exposed to the Streamlit anon role.
- The service-role key is only in GitHub Actions secrets; it never ships to
  the browser.
- Scrape workers send a descriptive User-Agent with a link back to this
  repository — retailers can always reach out to request opt-out.
