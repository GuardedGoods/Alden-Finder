"""Bespoke adapter for https://www.jgilbertfootwear.com (WordPress).

J. Gilbert is a WordPress site using the legacy WP e-Commerce plugin's
`/products-page/<cat>/<slug>/` URL pattern. There's no /products.json,
no WP REST API exposed. We walk the category landing pages, collect
product links, and parse each with JSON-LD + OG fallback.

Origin is known to 503 aggressively. If the listing page fails we exit
cleanly rather than pretend.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from urllib.parse import urljoin

import httpx
from selectolax.parser import HTMLParser

from alden_finder.adapters.base import RetailerAdapter, parse_product_html

log = logging.getLogger(__name__)

_LISTING_PATHS = (
    "/products-page/alden-boots/",
    "/products-page/alden-shoes/",
    "/products-page/alden/",
)
_MAX_PAGES = 4
_MAX_PRODUCTS = 120
_PROD_RE = re.compile(r"/products-page/[a-z0-9\-/]+/([a-z0-9][a-z0-9\-]{2,})/", re.IGNORECASE)


class Adapter(RetailerAdapter):
    key = "j_gilbert"

    async def fetch(self) -> AsyncIterator[dict]:
        urls: set[str] = set()
        for path in _LISTING_PATHS:
            for page in range(1, _MAX_PAGES + 1):
                listing = f"{self.base_url}{path}"
                if page > 1:
                    listing += f"page/{page}/"
                try:
                    r = await self.client.get(listing)
                except httpx.HTTPError:
                    break
                if r.status_code != 200:
                    break
                before = len(urls)
                urls.update(_listing_product_urls(r.text, self.base_url))
                if len(urls) == before:
                    break

        for url in list(urls)[:_MAX_PRODUCTS]:
            try:
                r = await self.client.get(url)
            except httpx.HTTPError:
                continue
            if r.status_code != 200:
                continue
            parsed = parse_product_html(r.text)
            if parsed is None or "alden" not in parsed["title"].lower():
                continue
            yield self.make_product(
                url=url,
                title=parsed["title"],
                image_url=parsed.get("image"),
                price_minor=parsed.get("price_minor"),
                in_stock=parsed.get("in_stock", True),
                retailer_sku=url.rstrip("/").rsplit("/", 1)[-1],
            )


def _listing_product_urls(html: str, base_url: str) -> set[str]:
    tree = HTMLParser(html)
    out: set[str] = set()
    for a in tree.css("a"):
        href = a.attributes.get("href") or ""
        if (
            "/products-page/" in href
            and href.count("/") >= 4
            and "alden" in href.lower()
            and _PROD_RE.search(href)
            and not href.rstrip("/").endswith(("/alden-boots", "/alden-shoes", "/alden"))
        ):
            out.add(urljoin(base_url, href))
    return out
