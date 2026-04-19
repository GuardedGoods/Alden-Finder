"""Pydantic models for the canonical Alden Finder data types."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class StockState(StrEnum):
    IN_STOCK = "in_stock"
    PREORDER = "preorder"
    MTO = "mto"
    SECONDS = "seconds"
    PRE_OWNED = "pre_owned"
    OUT_OF_STOCK = "out_of_stock"


class SourceType(StrEnum):
    AUTHORIZED = "authorized"
    SECONDS = "seconds"
    MTO = "mto"
    RESALE = "resale"


class Category(StrEnum):
    BOOT = "boot"
    CHUKKA = "chukka"
    INDY = "indy"
    OXFORD = "oxford"
    BLUCHER = "blucher"
    LOAFER = "loafer"
    TASSEL = "tassel"
    LWB = "lwb"
    SADDLE = "saddle"
    SLIPPER = "slipper"
    OTHER = "other"


class Retailer(BaseModel):
    id: int | None = None
    name: str
    url: HttpUrl
    country: str                        # ISO-3166 alpha-2
    currency: str                       # ISO-4217
    adapter_key: str                    # matches a registered adapter in adapters/
    active: bool = True
    rate_limit_s: float = 2.0
    ships_to: list[str] = Field(default_factory=list)
    notes: str | None = None
    source_type: SourceType = SourceType.AUTHORIZED
    last_scrape_started_at: datetime | None = None
    last_scrape_finished_at: datetime | None = None
    last_scrape_status: str | None = None   # "ok" | "error" | "partial"
    last_scrape_product_count: int | None = None
    last_scrape_error: str | None = None


class Product(BaseModel):
    """A single Alden product variant (last + size + width)."""

    id: int | None = None
    retailer_id: int
    retailer_sku: str | None = None
    url: str
    image_url: str | None = None

    model_number: str | None = None     # e.g. "405", "990", "975", "D8810H"
    title_raw: str

    last_name: str | None = None        # Barrie, Trubalance, ...
    leather_name: str | None = None     # Shell Cordovan, Calfskin, Suede, CXL
    color: str | None = None            # Color 8, Cigar, Whiskey, Ravello, Black, ...
    category: Category = Category.OTHER

    size_us: float | None = None        # 9, 9.5, 10
    size_uk: float | None = None
    size_eu: float | None = None
    width: str | None = None            # A, B, C, D, E, EE, EEE

    price_minor: int | None = None      # price in minor units (cents)
    currency: str | None = None
    on_sale: bool = False

    stock_state: StockState = StockState.IN_STOCK
    source_type: SourceType = SourceType.AUTHORIZED

    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    last_checked_at: datetime | None = None

    extra: dict[str, Any] = Field(default_factory=dict)


class ScrapeRun(BaseModel):
    id: int | None = None
    retailer_id: int
    started_at: datetime
    finished_at: datetime | None = None
    status: str = "running"              # "running" | "ok" | "error" | "partial"
    product_count: int = 0
    error: str | None = None


class FilterSpec(BaseModel):
    """Search filters supplied by the UI. All None-able = not filtered."""

    lasts: list[str] = Field(default_factory=list)
    sizes_us: list[float] = Field(default_factory=list)
    widths: list[str] = Field(default_factory=list)
    leathers: list[str] = Field(default_factory=list)
    colors: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    stock_states: list[str] = Field(default_factory=list)
    retailer_ids: list[int] = Field(default_factory=list)
    model_number: str | None = None
    on_sale: bool = False
    price_min: float | None = None
    price_max: float | None = None
    display_currency: str = "USD"
    q: str | None = None                 # free-text
    sort: str = "new"                    # "new" | "price_asc" | "price_desc" | "retailer"
