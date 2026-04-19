from alden_finder.scraping.runner import load_registry


def test_registry_loads_and_is_valid():
    rs = load_registry()
    assert len(rs) >= 40, "expected the full seed list"
    required = {"name", "url", "country", "currency", "adapter_key"}
    for r in rs:
        missing = required - r.keys()
        assert not missing, f"{r.get('name')} missing {missing}"
        assert r["url"].startswith("https://"), f"{r['name']} non-https url"
        assert len(r["country"]) == 2, f"{r['name']} country must be ISO-2"
        assert len(r["currency"]) == 3, f"{r['name']} currency must be ISO-3"


def test_known_retailers_present():
    names = {r["name"] for r in load_registry()}
    for expected in ("Leffot", "Skoaktiebolaget", "Mr. Derk", "Double Monk", "Alden of San Francisco"):
        assert expected in names
