import json
from pathlib import Path

import httpx
import pytest

from alden_finder.adapters.base import ShopifyAdapter

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "shopify_sample.json").read_text())


@pytest.mark.asyncio
async def test_shopify_adapter_parses_variants():
    def handler(request: httpx.Request) -> httpx.Response:
        if "/collections/alden/products.json" in str(request.url):
            return httpx.Response(200, json=FIXTURE)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        retailer = {
            "id": 42,
            "name": "Test Shop",
            "url": "https://example.com",
            "country": "US",
            "currency": "USD",
            "source_type": "authorized",
        }
        adapter = ShopifyAdapter(retailer, client)
        products = [p async for p in adapter.fetch()]

    assert len(products) == 4  # 3 + 1 variants
    # In-stock for 10D, 10.5D, and the 975 10D
    in_stock = [p for p in products if p["stock_state"] == "in_stock"]
    assert len(in_stock) == 3

    p405 = next(p for p in products if p["retailer_sku"] == "405-10D")
    assert p405["model_number"] == "405"
    assert p405["last_name"] == "Trubalance"
    assert p405["leather_name"] == "Shell Cordovan"
    assert p405["color"] == "Color 8"
    assert p405["category"] == "indy"
    assert p405["size_us"] == 10.0
    assert p405["width"] == "D"
    assert p405["price_minor"] == 98000
    assert p405["currency"] == "USD"
    assert p405["url"] == "https://example.com/products/alden-405-indy-boot-color-8-shell"
    assert p405["image_url"] == "https://cdn.example.com/405-color-8.jpg"

    p975 = next(p for p in products if p["retailer_sku"] == "975-10D")
    assert p975["last_name"] == "Barrie"
    assert p975["category"] == "lwb"
