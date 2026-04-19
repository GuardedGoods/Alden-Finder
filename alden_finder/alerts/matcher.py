"""Match subscribed alert filters against recently-added products."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from alden_finder.core import db
from alden_finder.core.models import FilterSpec

log = logging.getLogger(__name__)


def _spec_from_json(raw: dict) -> FilterSpec:
    """Tolerant FilterSpec loader — drops unknown keys instead of raising."""
    known = FilterSpec.model_fields.keys()
    return FilterSpec(**{k: v for k, v in raw.items() if k in known})


def pending_matches(lookback_hours: int = 48, per_alert_limit: int = 10) -> list[dict]:
    """Return a list of {alert, matches} dicts for alerts with new hits.

    A match is a product whose `first_seen_at` is later than the alert's
    `last_notified_at` (or the alert's `created_at` if never notified) AND
    matches the alert's saved FilterSpec AND isn't out-of-stock.

    Runs entirely through the `db` module so it works against Supabase or
    the in-memory sample dataset.
    """
    client = db._client()
    if client is None:
        log.info("alerts.matcher: no DB configured; nothing to do")
        return []

    alerts = (
        client.table("alerts").select("*").eq("active", True).execute().data or []
    )
    if not alerts:
        return []

    default_since = datetime.now(UTC) - timedelta(hours=lookback_hours)
    out: list[dict] = []
    for alert in alerts:
        spec = _spec_from_json(alert.get("filter_json") or {})
        since_raw = alert.get("last_notified_at") or alert.get("created_at")
        try:
            since = datetime.fromisoformat(since_raw) if since_raw else default_since
        except (TypeError, ValueError):
            since = default_since
        if since.tzinfo is None:
            since = since.replace(tzinfo=UTC)

        matches = db.search(spec, limit=per_alert_limit * 4)
        fresh = [
            p for p in matches
            if (p.get("first_seen_at") or p.get("last_seen_at") or "") >= since.isoformat()
            and p.get("stock_state") != "out_of_stock"
        ][:per_alert_limit]

        if fresh:
            out.append({"alert": alert, "matches": fresh})
    return out


def mark_notified(alert_id: int) -> None:
    client = db._client()
    if client is None:
        return
    client.table("alerts").update(
        {"last_notified_at": datetime.now(UTC).isoformat()}
    ).eq("id", alert_id).execute()
