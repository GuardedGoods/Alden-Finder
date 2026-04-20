"""Bespoke adapter for https://www.thearmoury.com (Hong Kong).

The Armoury runs a headless Shopify frontend. Every public JSON endpoint
(/products.json, /collections.json, /products/<h>.js) returns 404 —
locked down at the app layer. Their /collections/alden HTML is public
and lists ~8 products with URLs in the non-canonical form
`/collections/alden/<handle>` (not `/products/<handle>`).
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator

import httpx

from alden_finder.adapters.base import RetailerAdapter, parse_product_html

log = logging.getLogger(__name__)

_HANDLE_RE = re.compile(r"/collections/alden/([a-z0-9][a-z0-9\-]{2,})")
_MAX_PRODUCTS = 80


class Adapter(RetailerAdapter):
    key = "armoury"

    async def fetch(self) -> AsyncIterator[dict]:
        try:
            r = await self.client.get(f"{self.base_url}/collections/alden")
        except httpx.HTTPError as e:
            log.debug("armoury listing: %s", e)
            return
        if r.status_code != 200:
            return

        handles = set(_HANDLE_RE.findall(r.text))
        for handle in list(handles)[:_MAX_PRODUCTS]:
            url = f"{self.base_url}/collections/alden/{handle}"
            try:
                p = await self.client.get(url)
            except httpx.HTTPError:
                continue
            if p.status_code != 200:
                continue
            parsed = parse_product_html(p.text)
            if parsed is None or "alden" not in parsed["title"].lower():
                continue
            yield self.make_product(
                url=url,
                title=parsed["title"],
                image_url=parsed.get("image"),
                price_minor=parsed.get("price_minor"),
                in_stock=parsed.get("in_stock", True),
                retailer_sku=handle,
            )
