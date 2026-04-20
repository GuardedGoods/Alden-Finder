"""Bespoke adapter for https://leffot.com.

Leffot is not a Shopify store — it's a custom Next.js storefront backed by
Prismic CMS. None of the Shopify JSON endpoints (/products.json,
/collections.json, /products/<h>.js) exist there. Attempting them returns
404 or a 503 edge response. The site does, however, serve:

- /brands/alden           -> HTML listing with /products/<handle> links
- /brands/alden?page=2..  -> HTML pagination
- /products/<handle>      -> HTML product page with JSON-LD Product schema

So we:
 1. Walk /brands/alden and its paginated pages, collect handles.
 2. Hit each product page and parse JSON-LD (`@type: Product`) for
    title/image/price/availability. Fall back to OpenGraph meta tags if
    the JSON-LD is missing.

One row per product (Leffot keeps size as an on-page option; we don't
expose individual sizes). The handle becomes the retailer_sku.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator

import httpx
from selectolax.parser import HTMLParser

from alden_finder.adapters.base import RetailerAdapter

log = logging.getLogger(__name__)

_HANDLE_RE = re.compile(r"/products/([a-z0-9][a-z0-9\-]{2,})")
_MAX_PAGES = 8
_MAX_PRODUCTS = 120


class Adapter(RetailerAdapter):
    key = "leffot"

    async def fetch(self) -> AsyncIterator[dict]:
        handles = await self._collect_handles()
        for handle in list(handles)[:_MAX_PRODUCTS]:
            url = f"{self.base_url}/products/{handle}"
            try:
                r = await self.client.get(url)
            except httpx.HTTPError as e:
                log.debug("leffot product %s: %s", handle, e)
                continue
            if r.status_code != 200:
                continue
            parsed = _parse_product_html(r.text)
            if parsed is None:
                continue
            title = parsed["title"]
            # Leffot's brand landing is Alden-only, but defend against
            # scrolling past pagination into unrelated categories.
            if "alden" not in title.lower():
                continue
            yield self.make_product(
                url=url,
                title=title,
                image_url=parsed.get("image"),
                price_minor=parsed.get("price_minor"),
                in_stock=parsed.get("in_stock", True),
                retailer_sku=handle,
            )

    async def _collect_handles(self) -> set[str]:
        handles: set[str] = set()
        for page in range(1, _MAX_PAGES + 1):
            url = f"{self.base_url}/brands/alden"
            if page > 1:
                url += f"?page={page}"
            try:
                r = await self.client.get(url)
            except httpx.HTTPError:
                break
            if r.status_code != 200:
                break
            new = set(_HANDLE_RE.findall(r.text))
            # Stop paginating once a page brings no new handles.
            if not (new - handles):
                handles.update(new)
                break
            handles.update(new)
        return handles


# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------


def _parse_product_html(html: str) -> dict | None:
    dom = HTMLParser(html)
    for script in dom.css('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.text())
        except (ValueError, TypeError):
            continue
        product = _find_product_obj(data)
        if product:
            return _from_jsonld(product)

    def _meta(prop: str) -> str | None:
        el = dom.css_first(f'meta[property="{prop}"]') or dom.css_first(f'meta[name="{prop}"]')
        return el.attributes.get("content") if el else None

    h1 = dom.css_first("h1")
    title = _meta("og:title") or (h1.text(strip=True) if h1 else "")
    if not title:
        return None
    price_raw = _meta("product:price:amount") or _meta("og:price:amount")
    return {
        "title": title,
        "image": _meta("og:image"),
        "price_minor": _price_to_minor(price_raw),
        "in_stock": "sold out" not in html.lower() and "out of stock" not in html.lower(),
    }


def _find_product_obj(data) -> dict | None:
    """JSON-LD can arrive as a dict, list, or @graph wrapper."""
    if isinstance(data, dict):
        if data.get("@type") == "Product" or "Product" in (data.get("@type") or []):
            return data
        if isinstance(data.get("@graph"), list):
            for item in data["@graph"]:
                found = _find_product_obj(item)
                if found:
                    return found
    elif isinstance(data, list):
        for item in data:
            found = _find_product_obj(item)
            if found:
                return found
    return None


def _from_jsonld(obj: dict) -> dict:
    offers = obj.get("offers") or {}
    if isinstance(offers, list) and offers:
        offer = offers[0]
    elif isinstance(offers, dict):
        offer = offers
    else:
        offer = {}
    price_minor = _price_to_minor(offer.get("price") or offer.get("lowPrice"))
    availability = str(offer.get("availability") or "").lower()
    in_stock = "instock" in availability or availability.endswith("/instock")

    image = obj.get("image")
    if isinstance(image, list) and image:
        image = image[0]
    if isinstance(image, dict):
        image = image.get("url")

    return {
        "title": obj.get("name") or "",
        "image": image,
        "price_minor": price_minor,
        "in_stock": in_stock,
    }


def _price_to_minor(raw) -> int | None:
    if raw is None:
        return None
    try:
        return round(float(str(raw).replace(",", "")) * 100)
    except (ValueError, TypeError):
        return None
