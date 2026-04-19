"""Adapter for the Alden Shop (https://www.aldenshop.com), Alden's own retail storefront.

Placeholder: tries Shopify endpoints, then falls back to yielding nothing so
the retailer shows a `partial` status in the /status page instead of failing
outright. Replace with a real parser when the storefront platform is known.
"""

from __future__ import annotations

from alden_finder.adapters.base import ShopifyAdapter


class Adapter(ShopifyAdapter):
    key = "aldenshop"
