"""Adapter for https://www.theshoemart.com.

The Shoe Mart runs on a non-Shopify platform with an /alden/ category page.
This placeholder crawls that category page and extracts product links, titles,
prices, and in-stock state from the listing markup. Variant-level sizing is
not yet extracted — each listing maps to a single canonical product row.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import httpx
from selectolax.parser import HTMLParser

from alden_finder.adapters.base import RetailerAdapter, _parse_price_minor

log = logging.getLogger(__name__)


class Adapter(RetailerAdapter):
    key = "shoemart"

    async def fetch(self) -> AsyncIterator[dict]:
        try:
            r = await self.client.get(f"{self.base_url}/brands/alden/")
            if r.status_code != 200:
                r = await self.client.get(f"{self.base_url}/alden/")
        except httpx.HTTPError as e:
            log.debug("shoemart category fetch failed: %s", e)
            return
        if r.status_code != 200:
            return

        dom = HTMLParser(r.text)
        for card in dom.css("li.product, .product-item, article.product"):
            link = card.css_first("a")
            if not link:
                continue
            href = link.attributes.get("href") or ""
            url = href if href.startswith("http") else self.base_url + href
            title_el = card.css_first("h2, h3, .product-title, .name")
            title = (title_el.text(strip=True) if title_el else link.text(strip=True)) or ""
            img_el = card.css_first("img")
            image = (img_el.attributes.get("src") or img_el.attributes.get("data-src")) if img_el else None
            price_el = card.css_first(".price, .product-price")
            price_minor = _parse_price_minor(price_el.text() if price_el else "")
            in_stock = "out of stock" not in card.text().lower()
            yield self.make_product(
                url=url, title=title, image_url=image,
                price_minor=price_minor, in_stock=in_stock,
            )
