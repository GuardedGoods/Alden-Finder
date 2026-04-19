from alden_finder.core import db
from alden_finder.core.models import FilterSpec


def test_sample_search_defaults_returns_all():
    rows = db.search(FilterSpec(), limit=50)
    assert len(rows) >= 3
    assert all("title_raw" in p for p in rows)
    assert all("_retailer" in p for p in rows)


def test_filter_by_last():
    rows = db.search(FilterSpec(lasts=["Trubalance"]), limit=50)
    assert all(p.get("last_name") == "Trubalance" for p in rows)
    assert any(p.get("model_number") == "405" for p in rows)


def test_filter_by_country():
    rows = db.search(FilterSpec(countries=["SE"]), limit=50)
    assert rows
    assert all(p["_retailer"].get("country") == "SE" for p in rows)


def test_sort_price_asc():
    rows = db.search(FilterSpec(sort="price_asc"), limit=50)
    prices = [p.get("price_minor") or 0 for p in rows]
    assert prices == sorted(prices)
