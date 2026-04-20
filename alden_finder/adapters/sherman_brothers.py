"""Bespoke adapter for https://www.shermanbrothers.com (BigCommerce Stencil).

Sherman Brothers lists Alden at /brands/alden/ with classic BigCommerce
pagination (?page=N). Product detail URLs live at depth=1 off root like
`/alden-indy-workboot-original-brown-leather-405/`. No JSON-LD, so we
pull title/price out of the BigCommerce Stencil DOM.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from urllib.parse import urljoin

import httpx
from selectolax.parser import HTMLParser

from alden_finder.adapters.base import RetailerAdapter, parse_product_html, price_to_minor

log = logging.getLogger(__name__)

_LISTING = "/brands/alden/"
_MAX_PAGES = 10
_MAX_PRODUCTS = 240
_PRICE_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{2})?)")


class Adapter(RetailerAdapter):
    key = "sherman_brothers"

    async def fetch(self) -> AsyncIterator[dict]:
        urls: set[str] = set()
        for page in range(1, _MAX_PAGES + 1):
            listing = f"{self.base_url}{_LISTING}"
            if page > 1:
                listing += f"?page={page}"
            try:
                r = await self.client.get(listing)
            except httpx.HTTPError:
                break
            if r.status_code != 200:
                break
            before = len(urls)
            urls.update(_parse_listing_urls(r.text, self.base_url))
            if len(urls) == before:
                break

        for url in list(urls)[:_MAX_PRODUCTS]:
            try:
                r = await self.client.get(url)
            except httpx.HTTPError:
                continue
            if r.status_code != 200:
                continue
            parsed = parse_product_html(r.text) or _bc_stencil_fallback(r.text)
            if parsed is None or "alden" not in parsed["title"].lower():
                continue
            yield self.make_product(
                url=url,
                title=parsed["title"],
                image_url=parsed.get("image"),
                price_minor=parsed.get("price_minor"),
                in_stock=parsed.get("in_stock", True),
                retailer_sku=url.rsplit("/", 2)[-2],
            )


def _parse_listing_urls(html: str, base_url: str) -> set[str]:
    tree = HTMLParser(html)
    out: set[str] = set()
    for a in tree.css(".card a.card-figure, .card-title a"):
        href = a.attributes.get("href") or ""
        if _looks_like_product(href):
            out.add(urljoin(base_url, href))
    return out


def _looks_like_product(path: str) -> bool:
    if not path.startswith("/"):
        return False
    parts = [p for p in path.split("/") if p]
    if len(parts) != 1:
        return False
    return "alden" in parts[0].lower()


def _bc_stencil_fallback(html: str) -> dict | None:
    """BigCommerce Stencil product page parser — when JSON-LD is absent."""
    tree = HTMLParser(html)
    title_el = tree.css_first("h1.productView-title, h1.page-heading, h1")
    if not title_el:
        return None
    title = title_el.text(strip=True)
    img_el = tree.css_first("img.productView-image--default, .productView-image img")
    image = (
        img_el.attributes.get("src") or img_el.attributes.get("data-src")
    ) if img_el else None
    price_el = tree.css_first(
        ".productView-price .price--withoutTax, "
        ".productView-price .price, "
        "[itemprop='price']"
    )
    price_minor = None
    if price_el:
        content = price_el.attributes.get("content") or price_el.text(strip=True)
        if content:
            m = _PRICE_RE.search(content)
            price_minor = price_to_minor(m.group(1)) if m else price_to_minor(content)
    in_stock = "out of stock" not in html.lower()
    return {"title": title, "image": image, "price_minor": price_minor, "in_stock": in_stock}
