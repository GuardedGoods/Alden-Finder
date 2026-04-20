"""Bespoke adapter for https://thebureaubelfast.com.

Not a Shopify store. Custom platform that serves the Alden brand page at
`/shop/brand/alden-for-the-bureau` with product detail URLs under
`/shop/<id>/<slug>`. No public JSON endpoints — we parse HTML and rely on
JSON-LD Product schemas where available, falling back to OpenGraph tags.
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

_BRAND_PATH = "/shop/brand/alden-for-the-bureau"
# Bureau product links look like /shop/12345/black-cordovan-long-wing
_HANDLE_RE = re.compile(r"/shop/(\d+)/([a-z0-9][a-z0-9\-]{2,})")
_MAX_PAGES = 6
_MAX_PRODUCTS = 80


class Adapter(RetailerAdapter):
    key = "bureau_belfast"

    async def fetch(self) -> AsyncIterator[dict]:
        pairs = await self._collect_pairs()
        for pid, slug in list(pairs)[:_MAX_PRODUCTS]:
            url = f"{self.base_url}/shop/{pid}/{slug}"
            try:
                r = await self.client.get(url)
            except httpx.HTTPError:
                continue
            if r.status_code != 200:
                continue
            parsed = _parse_product(r.text)
            if parsed is None or "alden" not in parsed["title"].lower():
                continue
            yield self.make_product(
                url=url,
                title=parsed["title"],
                image_url=parsed.get("image"),
                price_minor=parsed.get("price_minor"),
                in_stock=parsed.get("in_stock", True),
                retailer_sku=str(pid),
            )

    async def _collect_pairs(self) -> set[tuple[str, str]]:
        pairs: set[tuple[str, str]] = set()
        for page in range(1, _MAX_PAGES + 1):
            url = self.base_url + _BRAND_PATH
            if page > 1:
                url += f"?page={page}"
            try:
                r = await self.client.get(url)
            except httpx.HTTPError:
                break
            if r.status_code != 200:
                break
            new = set(_HANDLE_RE.findall(r.text))
            if not (new - pairs):
                pairs.update(new)
                break
            pairs.update(new)
        return pairs


def _parse_product(html: str) -> dict | None:
    dom = HTMLParser(html)

    for script in dom.css('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.text())
        except (ValueError, TypeError):
            continue
        prod = _find_product(data)
        if prod:
            return _from_jsonld(prod)

    h1 = dom.css_first("h1")
    title = _meta(dom, "og:title") or (h1.text(strip=True) if h1 else "")
    if not title:
        return None
    return {
        "title": title,
        "image": _meta(dom, "og:image"),
        "price_minor": _price_minor(_meta(dom, "product:price:amount")),
        "in_stock": "sold out" not in html.lower() and "out of stock" not in html.lower(),
    }


def _meta(dom: HTMLParser, prop: str) -> str | None:
    el = dom.css_first(f'meta[property="{prop}"]') or dom.css_first(f'meta[name="{prop}"]')
    return el.attributes.get("content") if el else None


def _find_product(data) -> dict | None:
    if isinstance(data, dict):
        t = data.get("@type")
        if t == "Product" or (isinstance(t, list) and "Product" in t):
            return data
        if isinstance(data.get("@graph"), list):
            for item in data["@graph"]:
                found = _find_product(item)
                if found:
                    return found
    elif isinstance(data, list):
        for item in data:
            found = _find_product(item)
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
    image = obj.get("image")
    if isinstance(image, list) and image:
        image = image[0]
    if isinstance(image, dict):
        image = image.get("url")
    availability = str(offer.get("availability") or "").lower()
    return {
        "title": obj.get("name") or "",
        "image": image,
        "price_minor": _price_minor(offer.get("price") or offer.get("lowPrice")),
        "in_stock": "instock" in availability or availability.endswith("/instock"),
    }


def _price_minor(raw) -> int | None:
    if raw is None:
        return None
    try:
        return round(float(str(raw).replace(",", "")) * 100)
    except (ValueError, TypeError):
        return None
