"""Pluggable email transport for back-in-stock alerts.

Resolution order:
1. `RESEND_API_KEY` env var -> use Resend's HTTPS API (preferred; free tier).
2. `SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD` -> SMTP via smtplib.
3. No credentials -> print to stdout (dry-run; useful in CI).

Every transport returns True on success, False on failure, so the caller can
decide whether to mark the alert as notified.
"""

from __future__ import annotations

import html
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

import httpx

log = logging.getLogger(__name__)

FROM_NAME = os.environ.get("ALERT_FROM_NAME", "Alden Finder")
FROM_EMAIL = os.environ.get("ALERT_FROM_EMAIL", "alerts@alden-finder.example")
UNSUBSCRIBE_URL = os.environ.get(
    "ALERT_UNSUBSCRIBE_URL", "https://example.com/unsubscribe?id="
)


def render_email(matches: list[dict]) -> tuple[str, str, str]:
    """Return (subject, html_body, text_body)."""
    n = len(matches)
    subject = f"{n} new Alden match{'es' if n != 1 else ''} on Alden Finder"

    def _line(p: dict) -> str:
        r = p.get("_retailer") or {}
        size = p.get("size_us")
        width = p.get("width") or ""
        leather = p.get("leather_name") or ""
        color = p.get("color") or ""
        meta_bits = [b for b in (
            p.get("last_name"),
            f"{leather} {color}".strip() if (leather or color) else "",
            f"US {size:g}{width}" if size is not None else "",
        ) if b]
        return (
            f"<li style='margin-bottom:10px'>"
            f"<a href='{html.escape(p.get('url') or '#')}' "
            f"style='color:#7a2a28;font-weight:600'>{html.escape(p.get('title_raw') or '')}</a>"
            f"<br><span style='color:#555'>{html.escape(' · '.join(meta_bits))}</span>"
            f" — {html.escape(r.get('name') or '')} ({html.escape(r.get('country') or '')})"
            f"</li>"
        )

    items_html = "\n".join(_line(p) for p in matches)
    html_body = f"""\
<!doctype html>
<html><body style="font-family:system-ui,sans-serif;max-width:640px;margin:0 auto;padding:20px">
  <h2 style="color:#7a2a28">{html.escape(subject)}</h2>
  <p>New Alden listings matching your saved filter:</p>
  <ul style="padding-left:20px">
    {items_html}
  </ul>
  <p style="color:#888;font-size:0.85em;margin-top:32px">
    You're receiving this because you subscribed to alerts on Alden Finder.
    This is a non-profit project, unaffiliated with Alden Shoe Company.
    <br><a href="{UNSUBSCRIBE_URL}" style="color:#888">Unsubscribe</a>
  </p>
</body></html>"""

    text_body = "New Alden listings matching your filter:\n\n" + "\n".join(
        f"- {p.get('title_raw') or ''} — {p.get('url')}" for p in matches
    ) + f"\n\nUnsubscribe: {UNSUBSCRIBE_URL}\n"
    return subject, html_body, text_body


def send(to: str, subject: str, html_body: str, text_body: str) -> bool:
    resend_key = os.environ.get("RESEND_API_KEY")
    if resend_key:
        return _send_resend(resend_key, to, subject, html_body, text_body)

    if os.environ.get("SMTP_HOST"):
        return _send_smtp(to, subject, html_body, text_body)

    log.info("[DRY-RUN mail] to=%s subject=%s", to, subject)
    log.debug("%s", text_body)
    return True


def _send_resend(key: str, to: str, subject: str, html_body: str, text_body: str) -> bool:
    try:
        r = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "from": f"{FROM_NAME} <{FROM_EMAIL}>",
                "to": [to],
                "subject": subject,
                "html": html_body,
                "text": text_body,
            },
            timeout=15,
        )
        r.raise_for_status()
        return True
    except httpx.HTTPError as e:
        log.warning("resend send failed: %s", e)
        return False


def _send_smtp(to: str, subject: str, html_body: str, text_body: str) -> bool:
    msg = EmailMessage()
    msg["From"] = f"{FROM_NAME} <{FROM_EMAIL}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    pw = os.environ.get("SMTP_PASSWORD")
    try:
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls(context=ssl.create_default_context())
            if user and pw:
                s.login(user, pw)
            s.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException) as e:
        log.warning("smtp send failed: %s", e)
        return False
