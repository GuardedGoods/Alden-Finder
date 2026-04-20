"""Bespoke adapter for https://www.ealdwineraleigh.com (Squarespace).

Squarespace exposes `?format=json` on any page and returns the full
rendered store payload. We use `/alden?format=json` for the Alden
category and `/alden/p/<slug>?format=json` for product detail.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import httpx

from alden_finder.adapters.base import RetailerAdapter, price_to_minor

log = logging.getLogger(__name__)

_PATHS = ("/alden", "/alden-preorders", "/alden-last-call")
_MAX_PRODUCTS = 120


class Adapter(RetailerAdapter):
    key = "ealdwine"

    async def fetch(self) -> AsyncIterator[dict]:
        for path in _PATHS:
            try:
                r = await self.client.get(f"{self.base_url}{path}?format=json")
            except httpx.HTTPError as e:
                log.debug("ealdwine %s: %s", path, e)
                continue
            if r.status_code != 200:
                continue
            try:
                data = r.json()
            except (ValueError, TypeError):
                continue
            items = (data.get("items") or [])[:_MAX_PRODUCTS]
            for item in items:
                title = item.get("title") or ""
                if "alden" not in title.lower():
                    # Defense-in-depth: the Alden collection page occasionally
                    # includes cross-sells from related collections.
                    continue
                url_path = item.get("fullUrl") or f"{path}/p/{item.get('urlId')}"
                url = self.base_url + url_path
                image = item.get("assetUrl") or (item.get("mainImage") or {}).get("assetUrl")
                yield self.make_product(
                    url=url,
                    title=title,
                    image_url=image,
                    price_minor=_structured_price(item),
                    in_stock=not bool(item.get("structuredContent", {}).get("isSoldOut")),
                    retailer_sku=str(item.get("id") or item.get("urlId") or url),
                )


def _structured_price(item: dict) -> int | None:
    """Squarespace stores variant prices as integer cents."""
    sc = item.get("structuredContent") or {}
    variants = sc.get("variants") or []
    if variants:
        raw = variants[0].get("price")
        if isinstance(raw, int):
            return raw
        return price_to_minor(raw)
    return price_to_minor(sc.get("onSalePrice") or sc.get("price"))
