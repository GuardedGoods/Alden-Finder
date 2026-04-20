"""Bespoke adapter for https://aldenmadison.com (Alden Madison Avenue).

Alden Madison is a Shopify store that stocks only Alden. They don't have
a per-brand collection (there's no `alden` handle); instead the entire
catalog is Alden. We iterate site-wide `/products.json?page=N` and
dedupe by product.id.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import httpx

from alden_finder.adapters.base import ShopifyAdapter

log = logging.getLogger(__name__)

_MAX_PAGES = 8


class Adapter(ShopifyAdapter):
    key = "aldenmadison"

    async def fetch(self) -> AsyncIterator[dict]:
        seen_ids: set[int] = set()
        for page in range(1, _MAX_PAGES + 1):
            url = f"{self.base_url}/products.json?limit=250&page={page}"
            try:
                r = await self.client.get(url)
            except httpx.HTTPError as e:
                log.debug("aldenmadison page %d: %s", page, e)
                break
            if r.status_code != 200:
                break
            try:
                products = r.json().get("products") or []
            except (ValueError, KeyError):
                break
            if not products:
                break

            for p in products:
                pid = p.get("id")
                if pid is None or pid in seen_ids:
                    continue
                seen_ids.add(pid)

                handle = p.get("handle")
                title = p.get("title") or ""
                body_html = p.get("body_html") or ""
                image = (p.get("image") or {}).get("src") or (
                    (p.get("images") or [{}])[0].get("src") if p.get("images") else None
                )
                prod_url = f"{self.base_url}/products/{handle}"
                for variant in p.get("variants") or []:
                    variant_title = variant.get("title") or ""
                    price_f = float(variant.get("price") or 0)
                    available = bool(variant.get("available", True))
                    sku = str(
                        variant.get("sku") or variant.get("id")
                        or f"{handle}::{variant_title or 'default'}"
                    )
                    yield self.make_product(
                        url=prod_url,
                        title=title,
                        image_url=image,
                        price_minor=round(price_f * 100) if price_f else None,
                        in_stock=available,
                        retailer_sku=sku,
                        body=body_html,
                        variant=variant_title,
                    )

            if len(products) < 250:
                break
