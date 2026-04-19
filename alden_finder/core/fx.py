"""Currency conversion helpers.

Uses the open exchangerate.host API (no key required) with a 24-hour cache.
Falls back to a static rate table if the network is unavailable so the UI
still renders sensible numbers offline (critical for local dev and tests).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

CACHE_PATH = Path(os.environ.get("ALDEN_FX_CACHE", "/tmp/alden_fx.json"))
CACHE_TTL = timedelta(hours=24)
BASE = "USD"

# Sensible defaults as of early 2026; only used if the API is unreachable.
_STATIC: dict[str, float] = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.79,
    "CAD": 1.37,
    "AUD": 1.52,
    "JPY": 155.0,
    "KRW": 1350.0,
    "CNY": 7.2,
    "HKD": 7.8,
    "TWD": 32.0,
    "SGD": 1.34,
    "THB": 35.0,
    "PHP": 57.0,
    "IDR": 16000.0,
    "SEK": 10.6,
    "NOK": 10.7,
    "CHF": 0.89,
}


def _load_cache() -> dict | None:
    if not CACHE_PATH.exists():
        return None
    try:
        data = json.loads(CACHE_PATH.read_text())
        fetched_at = datetime.fromisoformat(data["fetched_at"])
        if datetime.now(UTC) - fetched_at > CACHE_TTL:
            return None
        return data
    except (OSError, ValueError, KeyError):
        return None


def _save_cache(rates: dict[str, float]) -> None:
    try:
        CACHE_PATH.write_text(
            json.dumps(
                {
                    "fetched_at": datetime.now(UTC).isoformat(),
                    "base": BASE,
                    "rates": rates,
                }
            )
        )
    except OSError as e:
        log.warning("Could not write FX cache: %s", e)


def _fetch_rates() -> dict[str, float]:
    cached = _load_cache()
    if cached:
        return cached["rates"]
    try:
        resp = httpx.get(
            "https://api.exchangerate.host/latest",
            params={"base": BASE},
            timeout=10,
        )
        resp.raise_for_status()
        rates = resp.json().get("rates", {})
        rates[BASE] = 1.0
        if rates:
            _save_cache(rates)
            return rates
    except (httpx.HTTPError, ValueError) as e:
        log.warning("FX fetch failed, using static table: %s", e)
    return dict(_STATIC)


def convert(amount: float, from_ccy: str, to_ccy: str) -> float:
    """Convert `amount` from `from_ccy` to `to_ccy`. Returns amount if rate unknown."""
    if from_ccy == to_ccy:
        return amount
    rates = _fetch_rates()
    f = rates.get(from_ccy) or _STATIC.get(from_ccy)
    t = rates.get(to_ccy) or _STATIC.get(to_ccy)
    if not f or not t:
        return amount
    return amount * (t / f)


def format_price(amount_minor: int | None, currency: str) -> str:
    if amount_minor is None:
        return "—"
    amount = amount_minor / 100
    symbol = {
        "USD": "$", "CAD": "C$", "AUD": "A$", "EUR": "€", "GBP": "£",
        "JPY": "¥", "KRW": "₩", "CNY": "¥", "HKD": "HK$", "TWD": "NT$",
        "SGD": "S$", "THB": "฿", "PHP": "₱", "IDR": "Rp", "SEK": "kr",
        "NOK": "kr", "CHF": "CHF ",
    }.get(currency, currency + " ")
    if currency in {"JPY", "KRW", "IDR"}:
        return f"{symbol}{amount:,.0f}"
    return f"{symbol}{amount:,.2f}"
