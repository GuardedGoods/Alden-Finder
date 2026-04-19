"""Scrape orchestrator.

Reads data/retailers.yaml, dispatches the right adapter per entry, honors
robots.txt and per-domain rate limits, and writes results to the DB (or the
in-memory sample store when no DB is configured).

Entry points:
    python -m alden_finder.scraping.runner            # scrape all active retailers
    python -m alden_finder.scraping.runner --retailer leffot
    python -m alden_finder.scraping.runner --once --retailer leffot   # CI dry run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

import httpx
import yaml

from alden_finder.adapters.base import load_adapter
from alden_finder.core import db
from alden_finder.core.models import Retailer

log = logging.getLogger("alden_finder.scrape")

USER_AGENT = (
    "AldenFinder/0.1 (+https://github.com/guardedgoods/alden-finder; "
    "non-profit; contact via GitHub issues)"
)

RETAILERS_YAML = Path(__file__).resolve().parents[2] / "data" / "retailers.yaml"


# ---------------------------------------------------------------------------
# Per-domain rate limiter
# ---------------------------------------------------------------------------


class _DomainLimiter:
    """Tiny async-safe minimum-interval gate per host."""

    def __init__(self) -> None:
        self._last: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, host: str) -> asyncio.Lock:
        lock = self._locks.get(host)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[host] = lock
        return lock

    async def wait(self, host: str, min_interval_s: float) -> None:
        async with self._lock(host):
            last = self._last.get(host, 0.0)
            delta = time.monotonic() - last
            if delta < min_interval_s:
                await asyncio.sleep(min_interval_s - delta)
            self._last[host] = time.monotonic()


# ---------------------------------------------------------------------------
# Retailer registry loader
# ---------------------------------------------------------------------------


def load_registry() -> list[dict]:
    raw = yaml.safe_load(RETAILERS_YAML.read_text()) or []
    for r in raw:
        r.setdefault("active", True)
        r.setdefault("rate_limit_s", 2.0)
        r.setdefault("source_type", "authorized")
    return raw


def sync_registry_to_db(registry: list[dict]) -> dict[str, int]:
    """Upsert every registry entry; return name → id."""
    ids: dict[str, int] = {}
    for entry in registry:
        retailer = Retailer(**{k: v for k, v in entry.items() if k not in {"id"}})
        rid = db.upsert_retailer(retailer)
        ids[entry["name"]] = rid
        entry["id"] = rid
    return ids


# ---------------------------------------------------------------------------
# Scrape one retailer
# ---------------------------------------------------------------------------


async def _scrape_one(entry: dict, client: httpx.AsyncClient, limiter: _DomainLimiter) -> None:
    name = entry["name"]
    if not entry.get("active", True):
        log.info("skip %s (inactive)", name)
        return

    host = entry["url"].split("//", 1)[-1].split("/", 1)[0]
    adapter = load_adapter(entry["adapter_key"], entry, client)
    if adapter is None:
        log.info("skip %s (no adapter)", name)
        return

    run_id = db.start_scrape_run(entry["id"])
    count = 0
    status = "ok"
    error: str | None = None
    seen_urls: set[str] = set()
    try:
        await limiter.wait(host, entry["rate_limit_s"])
        products_batch: list[dict] = []
        async for product in adapter.fetch():
            seen_urls.add(product["url"])
            products_batch.append(product)
            if len(products_batch) >= 50:
                db.upsert_products(products_batch)
                count += len(products_batch)
                products_batch = []
                await limiter.wait(host, entry["rate_limit_s"])
        if products_batch:
            db.upsert_products(products_batch)
            count += len(products_batch)
        db.mark_products_unseen(entry["id"], seen_urls)
        if count == 0:
            status = "partial"
            error = "no products parsed"
    except Exception as exc:
        status = "error"
        error = f"{type(exc).__name__}: {exc}"
        log.exception("scrape failed for %s", name)
    finally:
        db.finish_scrape_run(run_id, entry["id"], status, count, error)
        log.info("done %s: status=%s count=%d", name, status, count)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run(only: str | None = None, parallel: int = 4) -> int:
    registry = load_registry()
    sync_registry_to_db(registry)

    if only:
        registry = [r for r in registry if only.lower() in r["name"].lower() or only == r["adapter_key"]]
        if not registry:
            log.error("no retailers matched %r", only)
            return 2

    limiter = _DomainLimiter()
    headers = {"User-Agent": USER_AGENT}
    timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(
        headers=headers, timeout=timeout, follow_redirects=True, http2=True
    ) as client:
        sem = asyncio.Semaphore(parallel)

        async def _bounded(entry: dict) -> None:
            async with sem:
                await _scrape_one(entry, client, limiter)

        await asyncio.gather(*[_bounded(r) for r in registry])
    return 0


def cli() -> None:
    parser = argparse.ArgumentParser(prog="alden-scrape")
    parser.add_argument("--retailer", help="Match by name substring or adapter_key")
    parser.add_argument("--once", action="store_true", help="Exit after one pass (default).")
    parser.add_argument("--parallel", type=int, default=4)
    parser.add_argument("-v", "--verbose", action="count", default=0)
    args = parser.parse_args()

    level = logging.WARNING - args.verbose * 10
    logging.basicConfig(level=max(level, logging.DEBUG), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    sys.exit(asyncio.run(run(only=args.retailer, parallel=args.parallel)))


if __name__ == "__main__":
    cli()
