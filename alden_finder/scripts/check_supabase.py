"""Verify your Supabase project is configured correctly.

Usage:
    export SUPABASE_URL='https://xxxxx.supabase.co'
    export SUPABASE_SERVICE_ROLE_KEY='eyJ...'
    python -m alden_finder.scripts.check_supabase

Prints a green line for every OK and a red line for every failure. Exits
non-zero if anything is wrong so you can use this in CI.
"""

from __future__ import annotations

import os
import sys

EXPECTED_TABLES = ["alerts", "product_history", "products", "retailers", "scrape_runs"]


def _fail(msg: str) -> None:
    print(f"  FAIL  {msg}")


def _ok(msg: str) -> None:
    print(f"  OK    {msg}")


def main() -> int:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")

    print("Checking Supabase configuration")
    print("-" * 50)

    if not url:
        _fail("SUPABASE_URL env var is not set")
        return 1
    _ok(f"SUPABASE_URL = {url}")

    if not key:
        _fail("SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_KEY) env var is not set")
        return 1
    _ok(f"key length = {len(key)} chars (good)")

    try:
        from supabase import create_client
    except ImportError:
        _fail("supabase-py is not installed; run: pip install -e .")
        return 1

    try:
        client = create_client(url, key)
    except Exception as e:
        _fail(f"create_client() raised: {type(e).__name__}: {e}")
        return 1
    _ok("client created")

    missing: list[str] = []
    for table in EXPECTED_TABLES:
        try:
            client.table(table).select("*", count="exact").limit(0).execute()
            _ok(f"table 'public.{table}' is reachable")
        except Exception as e:
            _fail(f"table 'public.{table}' is missing or unreachable: {e}")
            missing.append(table)

    if missing:
        print()
        print("The expected tables are not in place. Re-run db/schema.sql")
        print("against this project (Supabase dashboard -> SQL Editor -> New query ->")
        print("paste the file contents -> Run).")
        return 2

    try:
        res = client.table("retailers").select("id", count="exact").limit(1).execute()
        n = getattr(res, "count", None)
        if n is None:
            n = len(res.data or [])
        _ok(f"retailers row count = {n}")
        if n == 0:
            print()
            print("Tables exist but retailers is empty. Seed with:")
            print("    python -c \"from alden_finder.scraping.runner import load_registry, sync_registry_to_db; sync_registry_to_db(load_registry())\"")
    except Exception as e:
        _fail(f"count retailers: {e}")

    print()
    print("Supabase looks good. Safe to trigger the scrape workflow.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
