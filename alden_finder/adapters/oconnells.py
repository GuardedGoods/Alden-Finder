"""Bespoke adapter for https://oconnellsclothing.com (Magento 2).

O'Connell's runs Magento 2 with a Sucuri/Cloudflare WAF that 403s bare
HTTP clients. Our standard Accept headers may or may not get through.
We walk `/brands/alden-shoe.html` (the Magento category page) and parse
Magento JSON-LD Product schemas on each PDP. If the listing page 403s,
we exit cleanly (status=partial) rather than pretending to have data.
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

_LISTING = "/brands/alden-shoe.html"
_MAX_PAGES = 6
_MAX_PRODUCTS = 160


class Adapter(RetailerAdapter):
    key = "oconnells"

    async def fetch(self) -> AsyncIterator[dict]:
        urls: set[str] = set()
        for page in range(1, _MAX_PAGES + 1):
            listing = f"{self.base_url}{_LISTING}"
            if page > 1:
                listing += f"?p={page}"
            try:
                r = await self.client.get(listing)
            except httpx.HTTPError as e:
                log.debug("oconnells listing page %d: %s", page, e)
                break
            if r.status_code != 200:
                break
            before = len(urls)
            urls.update(_parse_listing(r.text, self.base_url))
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
                retailer_sku=_sku_from_url(url),
            )


_PROD_RE = re.compile(r'href="(https?://[^"]+?\.html)"', re.IGNORECASE)


def _parse_listing(html: str, base_url: str) -> set[str]:
    out: set[str] = set()
    tree = HTMLParser(html)
    for a in tree.css("a.product-item-link, li.product a.product-item-photo"):
        href = a.attributes.get("href") or ""
        if href.endswith(".html") and "alden" in href.lower():
            out.add(urljoin(base_url, href))
    if not out:
        # Regex scan as fallback.
        for href in _PROD_RE.findall(html):
            if "alden" in href.lower() and "/brands/" not in href:
                out.add(href)
    return out


def _sku_from_url(url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return slug.removesuffix(".html")
