"""Bespoke adapter for https://www.theshoemart.com (BigCommerce Stencil).

BigCommerce stores don't expose a public products.json. The Shoe Mart
lists Alden at /alden-shoes/. We walk that page (plus ?page=N
pagination), collect product URLs, and parse each with JSON-LD + OG
fallback. Each product here is uniquely a footwear listing; no brand
filter is needed.
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

_LISTING_PATHS = ("/alden-shoes/", "/shop-by-brand/alden/")
_MAX_PAGES = 8
_MAX_PRODUCTS = 200
# BigCommerce product detail URLs are slugged off root: /alden-<model>-.../
# Listing card links to `/<slug>/` (trailing slash, depth=1, no /products/).
_PROD_ANCHOR_CLS = "card-figure, .card a"


class Adapter(RetailerAdapter):
    key = "shoemart"

    async def fetch(self) -> AsyncIterator[dict]:
        urls = await self._collect_product_urls()
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
                retailer_sku=_slug_from_url(url),
            )

    async def _collect_product_urls(self) -> set[str]:
        found: set[str] = set()
        for path in _LISTING_PATHS:
            for page in range(1, _MAX_PAGES + 1):
                listing = f"{self.base_url}{path}"
                if page > 1:
                    listing += f"?page={page}"
                try:
                    r = await self.client.get(listing)
                except httpx.HTTPError:
                    break
                if r.status_code != 200:
                    break
                before = len(found)
                found.update(_links_from_listing(r.text, self.base_url))
                if len(found) == before:
                    break
            if found:
                break
        return found


_BC_LINK_RE = re.compile(r'href="(/[a-z0-9][a-z0-9\-/]+/)"', re.IGNORECASE)


def _links_from_listing(html: str, base_url: str) -> set[str]:
    """Extract probable BigCommerce product detail URLs from a category page."""
    tree = HTMLParser(html)
    out: set[str] = set()

    for a in tree.css(".card-title a, a.card-figure, .productView a, h4.card-title a"):
        href = a.attributes.get("href") or ""
        if _looks_like_product_path(href):
            out.add(urljoin(base_url, href))

    if not out:
        # Fallback: regex-scan hrefs that look like `/alden-...-boot/` etc.
        for href in _BC_LINK_RE.findall(html):
            if _looks_like_product_path(href):
                out.add(urljoin(base_url, href))
    return out


def _looks_like_product_path(path: str) -> bool:
    if not path.startswith("/"):
        return False
    # Skip navigation / category pages.
    skip = ("/cart", "/account", "/login", "/search", "/alden-shoes/", "/shop-by-brand/")
    if any(path.startswith(s) for s in skip):
        return False
    # BigCommerce products are typically slugged with depth=1, end with "/".
    parts = [p for p in path.split("/") if p]
    if len(parts) != 1:
        return False
    return "alden" in parts[0].lower()


def _slug_from_url(url: str) -> str:
    parts = [p for p in url.rsplit("/", 2) if p]
    return parts[-1] if parts else url
