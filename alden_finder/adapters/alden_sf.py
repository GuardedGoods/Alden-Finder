"""Adapter for https://www.aldensf.com.

Alden of San Francisco's platform isn't publicly documented. This adapter
tries, in order:

1. Standard Shopify JSON (/collections/alden/products.json) — covers potential
   platform migrations.
2. BigCommerce API (/api/catalog/products?keyword=alden) — some boutique
   shops on BigCommerce expose this without auth.
3. Magento 2 REST (/rest/V1/products) — behind auth on most stores, so this
   is a cheap 401/403 probe.
4. Sitemap (/sitemap_products.xml, /sitemap.xml) → visit each product URL
   and parse OG/microdata tags.

If every strategy yields zero, the scrape run is recorded as `partial` with
the error "no products parsed", which surfaces in the /status page so a human
can triage. That's the correct failure mode — we'd rather show nothing than
fabricate data.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import httpx
from selectolax.parser import HTMLParser

from alden_finder.adapters.base import ShopifyAdapter, _parse_price_minor

log = logging.getLogger(__name__)


_PRODUCT_SITEMAPS = (
    "/sitemap_products.xml",
    "/sitemap-products.xml",
    "/sitemap.xml",
    "/pub/sitemap.xml",
)

_MAX_PAGES = 60  # cap so a broken sitemap can't run the crawler away


class Adapter(ShopifyAdapter):
    key = "alden_sf"

    async def fetch(self) -> AsyncIterator[dict]:
        # 1. Shopify JSON — cheap and handles platform migrations.
        shopify_batch = [p async for p in super().fetch()]
        if shopify_batch:
            for p in shopify_batch:
                yield p
            return

        # 2. BigCommerce public catalog search.
        bc_batch = [p async for p in self._try_bigcommerce()]
        if bc_batch:
            for p in bc_batch:
                yield p
            return

        # 3. Sitemap fallback.
        async for p in self._try_sitemap():
            yield p

    async def _try_bigcommerce(self) -> AsyncIterator[dict]:
        try:
            r = await self.client.get(
                f"{self.base_url}/api/catalog/products",
                params={"keyword": "alden", "limit": 100},
            )
        except httpx.HTTPError as e:
            log.debug("alden_sf bc probe failed: %s", e)
            return
        if r.status_code != 200:
            return
        try:
            data = r.json()
        except ValueError:
            return
        for p in data.get("data") or data.get("products") or []:
            title = p.get("name") or ""
            if "alden" not in title.lower():
                continue
            price = p.get("price") or (p.get("prices") or {}).get("price", {}).get("value")
            image = (p.get("images") or [{}])[0].get("url_standard") if p.get("images") else None
            url = p.get("custom_url", {}).get("url") if isinstance(p.get("custom_url"), dict) else p.get("url")
            if url and not url.startswith("http"):
                url = self.base_url + url
            yield self.make_product(
                url=url or self.base_url,
                title=title,
                image_url=image,
                price_minor=round((price or 0) * 100) if price else None,
                in_stock=bool(p.get("inventory_level", 1)),
                retailer_sku=str(p.get("sku") or p.get("id") or ""),
            )

    async def _try_sitemap(self) -> AsyncIterator[dict]:
        sitemap_text: str | None = None
        for path in _PRODUCT_SITEMAPS:
            try:
                r = await self.client.get(self.base_url + path)
            except httpx.HTTPError:
                continue
            if r.status_code == 200 and "<loc>" in r.text:
                sitemap_text = r.text
                break
        if not sitemap_text:
            return

        tree = HTMLParser(sitemap_text)
        urls = [
            loc.text().strip()
            for loc in tree.css("loc")
            if "/product" in loc.text() or "alden" in loc.text().lower()
        ]
        for url in urls[:_MAX_PAGES]:
            try:
                page = await self.client.get(url)
                if page.status_code != 200:
                    continue
            except httpx.HTTPError:
                continue
            prod = _parse_product_page(url, page.text)
            if prod is None:
                continue
            yield self.make_product(**prod)


def _parse_product_page(url: str, html: str) -> dict | None:
    """Pull a product dict out of a typical product page via OG + microdata."""
    dom = HTMLParser(html)

    def meta(name: str) -> str | None:
        el = dom.css_first(f"meta[property='{name}']") or dom.css_first(f"meta[name='{name}']")
        return el.attributes.get("content") if el else None

    title = meta("og:title") or (dom.css_first("h1").text(strip=True) if dom.css_first("h1") else None)
    if not title or "alden" not in title.lower():
        return None

    image = meta("og:image")
    price_raw = meta("product:price:amount") or meta("og:price:amount")
    if not price_raw:
        price_el = dom.css_first("[itemprop='price'], .price, .product-price")
        price_raw = (
            price_el.attributes.get("content") or price_el.text(strip=True)
        ) if price_el else None
    price_minor = _parse_price_minor(price_raw) if price_raw else None

    availability = meta("product:availability") or meta("og:availability") or ""
    in_stock = "in stock" in availability.lower() or availability.lower() in {"instock", "in_stock"}
    if not availability:
        in_stock = "out of stock" not in html.lower()

    return {
        "url": url,
        "title": title,
        "image_url": image,
        "price_minor": price_minor,
        "in_stock": in_stock,
    }
