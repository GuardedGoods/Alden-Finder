"""Adapter base classes.

Every retailer adapter produces an iterable of canonical product dicts
ready for `db.upsert_products`. Adapters don't touch the database directly;
the scraping runner wires I/O + DB together.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

import httpx
from selectolax.parser import HTMLParser

from alden_finder.core.models import SourceType, StockState
from alden_finder.core.normalize import classify

log = logging.getLogger(__name__)


class RetailerAdapter(ABC):
    """Base class for every retailer adapter."""

    key: str  # must match adapter_key in retailers.yaml

    def __init__(self, retailer: dict, client: httpx.AsyncClient):
        self.retailer = retailer
        self.client = client
        self.base_url: str = retailer["url"].rstrip("/")
        self.currency: str = retailer.get("currency", "USD")
        self.country: str = retailer.get("country", "US")

    @abstractmethod
    async def fetch(self) -> AsyncIterator[dict]:
        """Yield canonical product dicts ready for upsert."""
        raise NotImplementedError
        yield  # pragma: no cover  (satisfies type checker that this is a generator)

    # ---- helpers shared by adapters ---------------------------------------

    def make_product(
        self,
        *,
        url: str,
        title: str,
        image_url: str | None,
        price_minor: int | None,
        in_stock: bool,
        retailer_sku: str | None = None,
        body: str = "",
        variant: str = "",
        stock_state: StockState | None = None,
        source_type: SourceType | None = None,
    ) -> dict:
        fields = classify(title, body=body, variant=variant)
        state = (
            stock_state
            or (StockState.IN_STOCK if in_stock else StockState.OUT_OF_STOCK)
        )
        # retailer_sku is the upsert conflict key and must be non-empty.
        # Adapters that can't distinguish variants fall back to the URL,
        # which gives one row per product listing.
        sku = (retailer_sku or "").strip() or url
        return {
            "retailer_id": self.retailer["id"],
            "retailer_sku": sku,
            "url": url,
            "image_url": image_url,
            "title_raw": title.strip(),
            "price_minor": price_minor,
            "currency": self.currency,
            "on_sale": False,
            "stock_state": state.value,
            "source_type": (source_type or SourceType(self.retailer.get("source_type", "authorized"))).value,
            **fields,
        }


# ---------------------------------------------------------------------------
# Generic Shopify adapter
# ---------------------------------------------------------------------------


_ALDEN_COLLECTION_SLUGS = (
    "alden", "alden-shoes", "alden-footwear", "alden-shoe-company",
    "alden-shoe", "alden-boots", "alden-boot-co", "brands/alden",
)


def _is_alden_product(p: dict) -> bool:
    """True if a Shopify product is actually an Alden item.

    Some auto-discovered collections (e.g. Colony Clothing's "alden-capsule")
    also contain non-Alden inventory — Drumohr swim shorts, belts, wallets.
    Every real Alden product has the vendor or title reference us to Alden
    directly; anything else is carrier noise we don't want to index.
    """
    hay = (p.get("title") or "") + " " + (p.get("vendor") or "")
    return "alden" in hay.lower()


class ShopifyAdapter(RetailerAdapter):
    """Consumes Shopify's public JSON endpoints.

    Strategy, in order:
      1. /collections.json -> auto-discover any collection whose handle,
         title, or body_html mentions Alden, then pull /collections/<h>/products.json
         for each. Most robust — survives bespoke collection names.
      2. Hardcoded slug list — cheap fallback for stores that have disabled
         /collections.json.
      3. Site-wide /products.json with a title/vendor filter — works for
         Alden-only stores that don't organize by collection.
    """

    key = "shopify"

    async def _try_collection(self, slug: str) -> list[dict] | None:
        url = f"{self.base_url}/collections/{slug}/products.json?limit=250"
        try:
            r = await self.client.get(url)
        except httpx.HTTPError as e:
            log.debug("Shopify %s %s: %s", self.retailer.get("name"), slug, e)
            return None
        if r.status_code != 200 or "products" not in r.text:
            return None
        try:
            return r.json().get("products") or []
        except (ValueError, KeyError) as e:
            log.debug("Shopify %s %s: non-JSON body (%s)", self.retailer.get("name"), slug, e)
            return None

    async def _discover_alden_collections(self) -> list[str]:
        """Return handles of collections whose metadata mentions Alden."""
        try:
            r = await self.client.get(f"{self.base_url}/collections.json?limit=250")
        except httpx.HTTPError:
            return []
        if r.status_code != 200:
            return []
        try:
            collections = r.json().get("collections") or []
        except (ValueError, KeyError):
            return []
        hits = []
        for c in collections:
            hay = " ".join(
                str(c.get(k) or "") for k in ("handle", "title", "body_html")
            ).lower()
            if "alden" in hay:
                handle = c.get("handle")
                if handle:
                    hits.append(handle)
        return hits

    async def _all_alden_products(self) -> list[dict]:
        # 1. Discovery — filter non-Alden inventory that's in the same collection.
        seen_handles: set[str] = set()
        collected: list[dict] = []
        for handle in await self._discover_alden_collections():
            products = await self._try_collection(handle)
            if not products:
                continue
            for p in products:
                if not _is_alden_product(p):
                    continue
                ph = p.get("handle")
                if ph and ph not in seen_handles:
                    seen_handles.add(ph)
                    collected.append(p)
        if collected:
            return collected

        # 2. Hardcoded slug guesses — also filter per-product.
        for slug in _ALDEN_COLLECTION_SLUGS:
            products = await self._try_collection(slug)
            if products:
                hits = [p for p in products if _is_alden_product(p)]
                if hits:
                    return hits

        # 3. Site-wide /products.json with a filter.
        try:
            r = await self.client.get(f"{self.base_url}/products.json?limit=250")
        except httpx.HTTPError:
            r = None
        if r is not None and r.status_code == 200:
            try:
                all_products = r.json().get("products") or []
            except (ValueError, KeyError):
                all_products = []
            hits = [
                p for p in all_products
                if "alden" in (p.get("title", "") + " " + (p.get("vendor") or "")).lower()
            ]
            if hits:
                return hits

        # 4. HTML fallback — scrape the /collections/alden page for product
        #    handles and hit /products/<handle>.js per product. Covers stores
        #    where the JSON listing endpoints are disabled but the regular
        #    category pages (needed for Google) are still public.
        return await self._html_collection_fallback()

    async def _html_collection_fallback(self) -> list[dict]:
        handles: set[str] = set()
        for slug in _ALDEN_COLLECTION_SLUGS:
            try:
                r = await self.client.get(f"{self.base_url}/collections/{slug}")
            except httpx.HTTPError:
                continue
            if r.status_code != 200:
                continue
            # Shopify product URLs always look like /products/<handle>.
            for m in re.finditer(r"/products/([a-z0-9][a-z0-9\-]{2,})", r.text):
                handles.add(m.group(1))
            if handles:
                break
        if not handles:
            return []

        out: list[dict] = []
        for handle in list(handles)[:60]:       # cap so a weird page can't explode the run
            try:
                r = await self.client.get(f"{self.base_url}/products/{handle}.js")
            except httpx.HTTPError:
                continue
            if r.status_code != 200:
                continue
            try:
                product = r.json()
            except (ValueError, KeyError):
                continue
            if not product or not product.get("variants"):
                continue
            if "alden" not in (
                (product.get("title") or "") + " " + (product.get("vendor") or "")
            ).lower():
                continue
            # .js returns price as integer cents; /products.json format used by
            # the rest of the pipeline expects string dollars. Normalize.
            for v in product.get("variants") or []:
                raw = v.get("price")
                if isinstance(raw, int):
                    v["price"] = f"{raw / 100:.2f}"
                if "available" not in v:
                    v["available"] = True
            if not product.get("image") and product.get("featured_image"):
                product["image"] = {"src": product["featured_image"]}
            out.append(product)
        return out

    async def fetch(self) -> AsyncIterator[dict]:
        products = await self._all_alden_products()
        for p in products:
            handle = p.get("handle")
            title = p.get("title") or ""
            body_html = p.get("body_html") or ""
            image = (p.get("image") or {}).get("src") or (
                (p.get("images") or [{}])[0].get("src") if p.get("images") else None
            )
            url = f"{self.base_url}/products/{handle}"
            for variant in p.get("variants") or []:
                variant_title = variant.get("title") or ""
                price_f = float(variant.get("price") or 0)
                available = bool(variant.get("available", True))
                # Shopify variants always have an id; sku is optional. Fall
                # back to id so retailer_sku is never empty (schema enforces
                # NOT NULL, and the upsert conflict key needs it).
                sku = str(variant.get("sku") or variant.get("id") or f"{handle}::{variant_title or 'default'}")
                yield self.make_product(
                    url=url,
                    title=title,
                    image_url=image,
                    price_minor=round(price_f * 100) if price_f else None,
                    in_stock=available,
                    retailer_sku=sku,
                    body=body_html,
                    variant=variant_title,
                )


# ---------------------------------------------------------------------------
# Generic WooCommerce adapter
# ---------------------------------------------------------------------------


class WooAdapter(RetailerAdapter):
    """Best-effort WooCommerce adapter.

    We try `/product-category/alden/` and parse HTML product cards. Without the
    WC REST API key (which stores don't share publicly) this is necessarily
    surface-level.
    """

    key = "woo"
    _category_paths = ("/product-category/alden/", "/brand/alden/", "/shop/alden/")

    async def fetch(self) -> AsyncIterator[dict]:
        html = None
        for path in self._category_paths:
            try:
                r = await self.client.get(self.base_url + path, follow_redirects=True)
                if r.status_code == 200 and "alden" in r.text.lower():
                    html = r.text
                    break
            except httpx.HTTPError:
                continue
        if not html:
            return
        tree = HTMLParser(html)
        for card in tree.css("li.product, ul.products li, div.product"):
            a = card.css_first("a.woocommerce-LoopProduct-link, a.woocommerce-loop-product__link, a")
            if not a:
                continue
            url = a.attributes.get("href") or ""
            title_el = card.css_first(".woocommerce-loop-product__title, h2, .product-title")
            title = (title_el.text(strip=True) if title_el else a.text(strip=True)) or ""
            img_el = card.css_first("img")
            image = (img_el.attributes.get("src") or img_el.attributes.get("data-src")) if img_el else None
            price_el = card.css_first(".price bdi, .price .amount, .price")
            price_minor = _parse_price_minor(price_el.text() if price_el else "")
            in_stock_cls = "outofstock" not in (card.attributes.get("class") or "").lower()
            yield self.make_product(
                url=url,
                title=title,
                image_url=image,
                price_minor=price_minor,
                in_stock=in_stock_cls,
            )


_PRICE_RE = re.compile(r"([\d]+(?:[.,]\d{3})*(?:[.,]\d{2})?)")


def _parse_price_minor(text: str) -> int | None:
    if not text:
        return None
    m = _PRICE_RE.search(text.replace("\xa0", " "))
    if not m:
        return None
    raw = m.group(1).replace(",", "") if raw_is_us(m.group(1)) else m.group(1).replace(".", "").replace(",", ".")
    try:
        return round(float(raw) * 100)
    except ValueError:
        return None


def raw_is_us(s: str) -> bool:
    # Heuristic: if the last separator is a dot with two digits after, it's US format.
    if "." in s and "," in s:
        return s.rfind(".") > s.rfind(",")
    if "." in s:
        # "1,234.56" style would've been caught above; pure "99.00" is US.
        tail = s.rsplit(".", 1)[-1]
        return len(tail) == 2
    return True


def load_adapter(key: str, retailer: dict, client: httpx.AsyncClient) -> RetailerAdapter | None:
    """Return an adapter instance for `key`, or None for inert keys."""
    if key in {"static", ""} or not key:
        return None
    if key == "shopify":
        return ShopifyAdapter(retailer, client)
    if key == "woo":
        return WooAdapter(retailer, client)
    # Bespoke adapters live in alden_finder.adapters.<key>
    try:
        mod: Any = __import__(f"alden_finder.adapters.{key}", fromlist=["Adapter"])
    except ImportError:
        log.warning("No adapter module for key=%r; falling back to shopify.", key)
        return ShopifyAdapter(retailer, client)
    cls = getattr(mod, "Adapter", None)
    if cls is None:
        log.warning("adapters.%s has no `Adapter` class; using shopify fallback.", key)
        return ShopifyAdapter(retailer, client)
    return cls(retailer, client)
