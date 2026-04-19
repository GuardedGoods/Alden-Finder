"""Adapter for https://www.aldensf.com.

Alden of San Francisco's storefront isn't standard Shopify. As a placeholder
this adapter tries the Shopify JSON endpoints (they'll 404) and then falls
back to parsing /sitemap.xml for product URLs. A real bespoke parser that
extracts variants + sizes from the product pages is a follow-up.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import httpx
from selectolax.parser import HTMLParser

from alden_finder.adapters.base import ShopifyAdapter, _parse_price_minor

log = logging.getLogger(__name__)


class Adapter(ShopifyAdapter):
    key = "alden_sf"

    async def fetch(self) -> AsyncIterator[dict]:
        # Try Shopify first — cheap and covers potential platform migrations.
        shopify_batch = [p async for p in super().fetch()]
        if shopify_batch:
            for p in shopify_batch:
                yield p
            return

        # Sitemap fallback.
        try:
            r = await self.client.get(f"{self.base_url}/sitemap.xml")
            if r.status_code != 200:
                return
        except httpx.HTTPError as e:
            log.debug("alden_sf sitemap fetch failed: %s", e)
            return

        tree = HTMLParser(r.text)
        urls = [loc.text() for loc in tree.css("loc") if "/product" in loc.text()]
        for url in urls[:200]:
            try:
                page = await self.client.get(url)
                if page.status_code != 200:
                    continue
            except httpx.HTTPError:
                continue
            dom = HTMLParser(page.text)
            title_el = dom.css_first("h1, .product-name, .product__title")
            if not title_el:
                continue
            title = title_el.text(strip=True)
            img_el = dom.css_first("meta[property='og:image']") or dom.css_first(".product img")
            image = (
                img_el.attributes.get("content") or img_el.attributes.get("src")
                if img_el
                else None
            )
            price_el = dom.css_first(".price, .product-price, [itemprop='price']")
            price_minor = _parse_price_minor(price_el.text() if price_el else "")
            in_stock = "out of stock" not in page.text.lower()
            yield self.make_product(
                url=url, title=title, image_url=image,
                price_minor=price_minor, in_stock=in_stock,
            )
