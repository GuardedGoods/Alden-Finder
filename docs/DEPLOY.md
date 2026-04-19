# Deploy Alden Finder

A click-by-click walkthrough. First-time deployment takes about 25 minutes
even if you've never used Supabase or Streamlit Cloud before. Every service
below has a free tier that comfortably fits this project.

You will end up with:

- A live Streamlit site at `https://<your-app>.streamlit.app`
- A Supabase Postgres database holding the retailer and product tables
- A scheduled GitHub Action that refreshes the data hourly
- A second scheduled Action that sends back-in-stock email alerts

You do **not** need a domain, a credit card, or a server.

---

## Before you start

You need:

- A **GitHub account** with the repo forked (or your own copy pushed).
- A computer with **git** and **Python 3.11+** available.
- A modern web browser.
- About 25 minutes of uninterrupted attention.

Optional (for email alerts only):

- A **Resend account** (simplest) or any SMTP server you already use.
- A **domain you control** for the `From:` address on outbound emails.

If you skip the optional parts, the site still works — you just don't get
email alerts. See the "Skip email alerts" callout at the bottom of step 5.

---

## Step 1 — Get the code on your machine

You already have the repository. Fork it into your own GitHub account (top
right of the repo page, click **Fork**), then clone your fork:

```bash
git clone git@github.com:<your-github-username>/alden-finder.git
cd alden-finder
python3.11 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q
```

You should see `15 passed` at the end. If you see import errors, your
Python is older than 3.11 — install 3.11+ from <https://www.python.org/downloads>.

Smoke-test the app locally (no database yet — you'll see the 3-product
sample dataset, which is expected):

```bash
streamlit run alden_finder/app.py
```

Open <http://localhost:8501>. You should see the Alden Finder UI with a
sidebar of filters and 3 sample cards. Close with Ctrl-C.

---

## Step 2 — Create the Supabase project (5 min)

Supabase is a managed Postgres host. Free tier gives you 500 MB of storage
and 2 GB of egress per month, which is 30x what this project needs at
launch scale.

1. Go to <https://supabase.com> and click **Start your project** (top right).
2. Sign in with GitHub when prompted.
3. Click **New project**. Fill in:
   - **Organization**: your personal org is fine.
   - **Name**: `alden-finder`
   - **Database Password**: click **Generate a password** and **copy it
     somewhere safe**. You need it only if you want to connect via `psql`
     directly; the Streamlit app uses API keys, not this password.
   - **Region**: pick one close to your users (US East is a reasonable
     default).
   - **Pricing Plan**: **Free**.
4. Click **Create new project**. Supabase spends 60-90 seconds provisioning.
   Grab a coffee.

When the dashboard loads, you're at `https://supabase.com/dashboard/project/<project-ref>`.

### Step 2a — Apply the schema

1. In the left nav, click the **SQL Editor** icon (looks like `</>`).
2. Click **New query** (top right of the editor).
3. Open `db/schema.sql` from your local clone, copy the entire file, paste
   it into the SQL editor.
4. Click **Run** (bottom right, or press `Ctrl`/`Cmd` + `Enter`).
5. You should see a green **"Success. No rows returned"** message.

Verify: in the left nav, click **Table Editor**. You should see six tables:
`retailers`, `scrape_runs`, `products`, `product_history`, `alerts`, plus
auth internals. All are empty — that's correct, the scraper will populate
them.

### Step 2b — Copy your API keys

1. In the left nav, click the gear icon (**Project Settings**).
2. Click **API** in the settings sub-menu.
3. You now see three critical values. Open a text file locally and paste
   each one, labelled — you'll copy them into several places later:

   - **Project URL** → labelled as `SUPABASE_URL`.
     Example: `https://abcdefghijkl.supabase.co`
   - **Project API keys → anon (public)** → labelled as `SUPABASE_KEY`.
     A long JWT starting with `eyJ...`.
   - **Project API keys → service_role (secret)** → labelled as
     `SUPABASE_SERVICE_ROLE_KEY`. Also an `eyJ...` JWT.

**Never commit any of these into git.** The service_role key bypasses
row-level security and would let anyone read subscriber emails if leaked.

### Step 2c — Seed the retailer list

From your terminal (where you're still inside the repo and the venv is
active):

```bash
export SUPABASE_URL='<paste your project URL>'
export SUPABASE_SERVICE_ROLE_KEY='<paste your service_role key>'

python -c "from alden_finder.scraping.runner import load_registry, sync_registry_to_db; \
           ids = sync_registry_to_db(load_registry()); \
           print(f'Seeded {len(ids)} retailers')"
```

Expected output: `Seeded 66 retailers`.

Verify in Supabase: **Table Editor → retailers**. You should see 66 rows
across 20 countries.

---

## Step 3 — Deploy the Streamlit UI (3 min)

Streamlit Community Cloud hosts the UI for free, directly from your GitHub
fork.

1. Go to <https://share.streamlit.io> and click **Continue with GitHub**.
   Authorize the Streamlit app when prompted.
2. Click **New app** (top right).
3. Fill in the dialog:
   - **Repository**: `<your-github-username>/alden-finder`
   - **Branch**: `main`
   - **Main file path**: `alden_finder/app.py`
   - **App URL** (optional): something like `alden-finder.streamlit.app`
     if the name is free — otherwise Streamlit picks one for you.
4. **Before you click Deploy**, click **Advanced settings**.
5. In the **Secrets** textarea, paste (substituting your real values):

   ```toml
   SUPABASE_URL = "https://abcdefghijkl.supabase.co"
   SUPABASE_KEY = "eyJhbGciOi...anon-key-here..."
   ```

   Use the **anon** key here, not the service_role key. The UI only reads;
   it never writes. Row-level security on Supabase blocks the anon key from
   touching the `alerts` table.
6. Click **Deploy**.

Streamlit takes 2-3 minutes for the first deploy (installing dependencies).
When it's done, you'll land on your live site. At this point filters work,
but there are no products yet — that's step 4.

If the UI fails to start, click **Manage app** (bottom right) to view logs.
Most common error: typo in the secrets block — the `TOML` parser is picky
about unquoted strings.

---

## Step 4 — Configure GitHub Actions for hourly scraping (3 min)

The scrape workflow lives at `.github/workflows/scrape.yml` and runs at
`:07` every hour. It needs two secrets to write to Supabase.

1. Open your fork on GitHub. Click **Settings** (top right of the repo).
2. In the left nav: **Secrets and variables → Actions**.
3. Click **New repository secret**, then add each of these one at a time:

   | Name                          | Value                                         |
   |-------------------------------|-----------------------------------------------|
   | `SUPABASE_URL`                | The same project URL you used in Streamlit.   |
   | `SUPABASE_SERVICE_ROLE_KEY`   | The `service_role` key (write access).        |

4. Now enable workflows: click the **Actions** tab at the top of the repo.
   If you see a banner *"Workflows aren't being run on this forked
   repository"*, click **I understand my workflows, go ahead and enable
   them**.

### Step 4a — Trigger the first scrape manually

Don't wait an hour for the cron. Kick it off by hand:

1. **Actions** tab → left sidebar, click **Scrape retailers**.
2. Click **Run workflow** (top right of the workflow list).
3. Leave the inputs blank. Click the green **Run workflow** button.
4. The run appears in the list after ~10 seconds. Click into it, then into
   the `scrape` job to watch the logs stream.

Expected duration: **6 to 12 minutes** for the full 47 active retailers.
Shopify adapters are fast (~2 s each); the sitemap crawler for `alden_sf`
can take longer.

When the job turns green, go back to your Streamlit site and refresh:

- The search view should show real Alden products.
- `/status` should list every retailer with a recent `last_scrape_finished_at`.
- Any retailer that couldn't find products shows `partial` with the error
  `no products parsed` — that's fine for now, it means the adapter needs
  custom work.

---

## Step 5 — Configure email alerts (optional, 5 min)

Skip this whole step if you don't want to enable back-in-stock emails.
Users visiting your site will see the subscribe form but get a clear
message that alerts aren't available — nothing silently breaks.

### Step 5a — Create a Resend account

1. Go to <https://resend.com> and sign up (GitHub login is easiest).
2. From the dashboard, click **API Keys → Create API Key**.
3. Name it `alden-finder`, permission `Sending access`. Click **Add**.
4. Copy the key (`re_...`) — Resend shows it **once**. Save it locally.
5. Under **Domains → Add Domain**, add a domain you control. You'll need
   to add TXT and MX records at your DNS provider. Resend walks you
   through this — the whole process takes ~15 minutes including
   verification. Until the domain verifies, emails go to spam.

   If you don't own a domain, Resend gives you `onboarding@resend.dev`
   for testing — use that temporarily.

### Step 5b — Add alert secrets to GitHub

Back in your repo's **Settings → Secrets and variables → Actions**, add:

| Name                       | Value                                                       | Required |
|----------------------------|-------------------------------------------------------------|----------|
| `RESEND_API_KEY`           | `re_...` from step 5a.                                      | Yes (to send) |
| `ALERT_FROM_EMAIL`         | `alerts@<your-verified-domain>`                             | Yes      |
| `ALERT_FROM_NAME`          | `Alden Finder` (or whatever you prefer)                     | Optional |
| `ALERT_UNSUBSCRIBE_URL`    | For now: `https://<your-app>.streamlit.app/?view=about`     | Optional |

### Step 5c — Enable and dry-run the alerts workflow

1. **Actions** tab → left sidebar, click **Back-in-stock alerts**.
2. Click **Run workflow**, set **dry_run** to `true`, click the green button.
3. The workflow should report `no pending matches across any alert` —
   expected, you haven't subscribed to anything yet.

### Step 5d — Subscribe a test email

1. On your live Streamlit site, use the filters to define a search (e.g.
   Last = Barrie, Width = D).
2. Scroll below the grid, expand **Notify me when matching Alden comes in
   stock**, enter your email, click **Subscribe**.
3. You should see a green `Subscribed.` confirmation.
4. In Supabase **Table Editor → alerts**, verify the row exists.
5. Run the alerts workflow again with `dry_run=false`. If there are
   products newer than the alert's `created_at`, you'll receive an email
   within a minute. (If not, there's nothing matching — try a broader
   filter and re-subscribe.)

### Skip email alerts

If you want to skip this step entirely, do nothing. The
`.github/workflows/alerts.yml` workflow still runs hourly but without a
`RESEND_API_KEY` it falls into dry-run mode and exits 0 without sending
anything. The UI's subscribe form shows the "alerts require a configured
database / email provider" notice.

---

## Step 6 — Ongoing

You now have a self-running site. Day-to-day operations:

- **Add a retailer**: edit `data/retailers.yaml`, open a PR, merge. CI
  validates the file on every PR. The next scheduled scrape picks it up.
- **Remove a retailer** (dealer opt-out): flip `active: false` for that
  entry in `data/retailers.yaml`. The scraper stops touching the site on
  the next run; the UI shows the retailer with the `inactive` badge. Old
  product rows stay in the database — drop them manually with
  `DELETE FROM products WHERE retailer_id = X;` if you want them gone.
- **Ad-hoc rescrape**: Actions → *Scrape retailers* → *Run workflow*,
  optionally fill `retailer` with a substring (e.g. `leffot`) to scrape
  one site.
- **Unsubscribe a user**: `UPDATE alerts SET active = false WHERE
  email = 'x@y.z';` in the Supabase SQL editor. (A proper unsubscribe
  endpoint is on the roadmap.)
- **Watch freshness**: the `/status` page on your site shows each
  retailer's last scrape time and product count. Yellow badges (> 6h)
  indicate a scrape is overdue; red (> 24h) means the adapter is
  probably broken.

---

## Troubleshooting

### The UI boots but shows 3 sample products no matter what I filter

Supabase credentials aren't reaching the Streamlit process. Double-check:
- The secrets block in Streamlit Cloud uses `SUPABASE_KEY` (anon), not
  `SUPABASE_SERVICE_ROLE_KEY`.
- There are no trailing spaces or stray quotes in the secret values.
- The URL is `https://<ref>.supabase.co` — no trailing slash.
- Click **Manage app → Reboot** after editing secrets; they don't hot-reload.

### The scrape workflow runs but all retailers end up as `partial`

That means adapters ran but found zero products. Common causes:
- First-run race: the workflow ran before you seeded retailers in step 2c.
  Re-run step 2c from your terminal, then re-trigger the workflow.
- Network timeouts on slow retailers. Re-run the workflow; it should
  converge over 2-3 runs.
- A retailer blocked our User-Agent. Visit `/status`, note which retailer
  is failing, and check its `last_scrape_error`.

### I see `ModuleNotFoundError` in the Actions logs

Pin your Python version. The workflows use 3.11 — if you changed that,
revert or update `pyproject.toml`'s `requires-python`.

### Alerts send twice for the same product

The `last_notified_at` field didn't update. Check that the mailer is
actually reporting success (look at the Actions log for the alert run —
should see `sent alert=<id> email=<addr>`). If Resend is misconfigured the
mailer returns False and the alert correctly retries on the next run.

### Someone emailed saying they're a dealer and want out

Do the right thing:
1. Edit `data/retailers.yaml`, set `active: false`, add a `notes:` line
   recording the opt-out date.
2. Commit and push to `main`.
3. Within 1 hour the next scrape skips them; within 24 hours stale product
   rows flip to `out_of_stock`.
4. Reply to the dealer confirming.

---

## Cost model

Running this as described, monthly cost is **$0** for the first ~500 MB of
product data and up to 3,000 alert emails. You can monitor usage:

- **Supabase**: dashboard → *Database → Usage*. Free tier includes 500 MB
  storage, 2 GB egress, unlimited API requests.
- **Streamlit Cloud**: free tier includes unlimited public apps with
  1 GB RAM each; this app uses ~200 MB.
- **GitHub Actions**: public repos get unlimited minutes. (Private repos
  get 2,000 min/month free; this project uses ~10 min/day, well under.)
- **Resend**: free tier is 100 emails/day, 3,000/month — more than enough
  for a niche enthusiast audience.

If/when you grow past these tiers, each provider has a clear upgrade
path. None of them require you to migrate off their platform.
