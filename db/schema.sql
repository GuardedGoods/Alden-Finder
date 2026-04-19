-- Alden Finder — Supabase / Postgres schema.
--
-- Apply once in Supabase SQL editor:
--   psql "$SUPABASE_DB_URL" -f db/schema.sql
-- or paste into the Supabase dashboard SQL editor.
--
-- The UI uses the anon role to SELECT, the scraper uses the service role
-- to INSERT/UPDATE. Tables are locked down via RLS so the anon role cannot
-- see PII (alerts.email).

create extension if not exists "pg_trgm";

create table if not exists retailers (
  id                           bigserial primary key,
  name                         text unique not null,
  url                          text not null,
  country                      text not null,
  currency                     text not null,
  adapter_key                  text not null,
  active                       boolean not null default true,
  rate_limit_s                 double precision not null default 2.0,
  ships_to                     text[] default '{}',
  source_type                  text not null default 'authorized',
  notes                        text,
  last_scrape_started_at       timestamptz,
  last_scrape_finished_at      timestamptz,
  last_scrape_status           text,
  last_scrape_product_count    int,
  last_scrape_error            text,
  created_at                   timestamptz not null default now()
);

create index if not exists idx_retailers_country on retailers(country);
create index if not exists idx_retailers_active  on retailers(active);

create table if not exists scrape_runs (
  id             bigserial primary key,
  retailer_id    bigint not null references retailers(id) on delete cascade,
  started_at     timestamptz not null default now(),
  finished_at    timestamptz,
  status         text not null default 'running',
  product_count  int not null default 0,
  error          text
);

create index if not exists idx_runs_retailer_started on scrape_runs(retailer_id, started_at desc);

create table if not exists products (
  id                 bigserial primary key,
  retailer_id        bigint not null references retailers(id) on delete cascade,
  retailer_sku       text,
  url                text not null,
  image_url          text,
  model_number       text,
  title_raw          text not null,
  last_name          text,
  leather_name       text,
  color              text,
  category           text,
  size_us            numeric(4,1),
  size_uk            numeric(4,1),
  size_eu            numeric(4,1),
  width              text,
  price_minor        bigint,
  currency           text,
  on_sale            boolean not null default false,
  stock_state        text not null default 'in_stock',
  source_type        text not null default 'authorized',
  extra              jsonb default '{}'::jsonb,
  first_seen_at      timestamptz not null default now(),
  last_seen_at       timestamptz not null default now(),
  last_checked_at    timestamptz not null default now(),
  unique (retailer_id, url)
);

create index if not exists idx_products_last     on products(last_name);
create index if not exists idx_products_leather  on products(leather_name);
create index if not exists idx_products_size     on products(size_us);
create index if not exists idx_products_width    on products(width);
create index if not exists idx_products_stock    on products(stock_state);
create index if not exists idx_products_source   on products(source_type);
create index if not exists idx_products_model    on products(model_number);
create index if not exists idx_products_title_trgm on products using gin (title_raw gin_trgm_ops);
create index if not exists idx_products_last_seen on products(last_seen_at desc);

create table if not exists product_history (
  id           bigserial primary key,
  product_id   bigint not null references products(id) on delete cascade,
  checked_at   timestamptz not null default now(),
  stock_state  text not null,
  price_minor  bigint
);

create index if not exists idx_history_product_time on product_history(product_id, checked_at desc);

create table if not exists alerts (
  id                  bigserial primary key,
  email               text not null,
  filter_json         jsonb not null,
  created_at          timestamptz not null default now(),
  last_notified_at    timestamptz,
  active              boolean not null default true
);

create index if not exists idx_alerts_active on alerts(active) where active;

-- Row-level security: let the anon role read public tables, but never touch
-- alerts (which contains email addresses). The service role bypasses RLS.
alter table retailers       enable row level security;
alter table products        enable row level security;
alter table scrape_runs     enable row level security;
alter table product_history enable row level security;
alter table alerts          enable row level security;

drop policy if exists "public read retailers"      on retailers;
drop policy if exists "public read products"       on products;
drop policy if exists "public read runs"           on scrape_runs;
drop policy if exists "public read product_history" on product_history;

create policy "public read retailers"       on retailers       for select using (true);
create policy "public read products"        on products        for select using (true);
create policy "public read runs"            on scrape_runs     for select using (true);
create policy "public read product_history" on product_history for select using (true);
-- alerts has no public policy → anon cannot read/write it.
