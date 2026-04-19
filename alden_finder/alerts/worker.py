"""Alert worker CLI.

Intended cadence: run immediately after each scrape workflow. A single pass:

    python -m alden_finder.alerts.worker

- Loads every active alert from the `alerts` table.
- For each one, runs the saved FilterSpec through `db.search` with a time
  cutoff at the last_notified_at.
- If there are new matches, renders an email and dispatches it via the
  configured transport (Resend > SMTP > dry-run).
- On successful send, updates `last_notified_at` so the same products
  aren't emailed twice.

Safeguards:
- `--dry-run` forces the no-send path regardless of environment.
- `--max-per-alert` caps how many products appear in a single email.
- Any exception from the mailer is logged but doesn't poison the loop.
"""

from __future__ import annotations

import argparse
import logging
import sys

from alden_finder.alerts import mailer, matcher

log = logging.getLogger("alden_finder.alerts")


def run(dry_run: bool = False, max_per_alert: int = 10) -> int:
    groups = matcher.pending_matches(per_alert_limit=max_per_alert)
    if not groups:
        log.info("no pending matches across any alert")
        return 0

    sent = 0
    for group in groups:
        alert = group["alert"]
        matches = group["matches"]
        subject, html_body, text_body = mailer.render_email(matches)

        if dry_run:
            log.info(
                "[DRY-RUN] alert=%s email=%s matches=%d",
                alert.get("id"), alert.get("email"), len(matches),
            )
            continue

        ok = mailer.send(alert["email"], subject, html_body, text_body)
        if ok:
            matcher.mark_notified(alert["id"])
            sent += 1
            log.info("sent alert=%s email=%s matches=%d", alert["id"], alert["email"], len(matches))
        else:
            log.warning("send failed; not marking alert=%s notified", alert["id"])

    log.info("done; sent=%d skipped=%d", sent, len(groups) - sent)
    return 0


def cli() -> None:
    parser = argparse.ArgumentParser(prog="alden-alerts")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-per-alert", type=int, default=10)
    parser.add_argument("-v", "--verbose", action="count", default=0)
    args = parser.parse_args()

    level = logging.WARNING - args.verbose * 10
    logging.basicConfig(
        level=max(level, logging.DEBUG),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    sys.exit(run(dry_run=args.dry_run, max_per_alert=args.max_per_alert))


if __name__ == "__main__":
    cli()
