-- Migration 001: dedupe Shopify variants on (retailer_id, retailer_sku).
--
-- Problem: the original schema used UNIQUE (retailer_id, url). Shopify
-- returns N variants per product, all sharing the same product URL. A
-- single upsert batch with multiple variants of one product therefore
-- hit the Postgres cardinality_violation:
--     "ON CONFLICT DO UPDATE command cannot affect row a second time"
-- and every such scrape failed.
--
-- This migration swaps the unique key to (retailer_id, retailer_sku),
-- which is what it should have been all along — each variant has its own
-- SKU (or a synthesized one from the adapter).
--
-- Safe to re-run: every statement is either IF EXISTS / IF NOT EXISTS
-- or tolerant of the target state already being in place.

begin;

-- Drop any failed-run partial rows that might have NULL retailer_sku,
-- so we can enforce NOT NULL without failing.
delete from product_history
 where product_id in (select id from products where retailer_sku is null);
delete from products where retailer_sku is null;

-- Drop the old unique constraint. In Supabase the auto-generated name is
-- typically products_retailer_id_url_key. We probe both possibilities.
alter table products drop constraint if exists products_retailer_id_url_key;
alter table products drop constraint if exists products_retailer_id_retailer_sku_key;

-- Enforce the invariant the adapters now uphold.
alter table products alter column retailer_sku set not null;

-- Re-add the new unique constraint. Skip if it already exists.
do $$
begin
  if not exists (
    select 1 from pg_constraint
     where conname = 'products_retailer_id_retailer_sku_key'
  ) then
    alter table products
      add constraint products_retailer_id_retailer_sku_key
      unique (retailer_id, retailer_sku);
  end if;
end
$$;

commit;
