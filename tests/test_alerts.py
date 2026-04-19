from alden_finder.alerts import mailer, worker
from alden_finder.core.models import FilterSpec


def test_render_email_contains_titles_and_links():
    matches = [
        {
            "title_raw": "Alden 405 Indy Boot Color 8",
            "url": "https://leffot.com/products/alden-405",
            "last_name": "Trubalance",
            "leather_name": "Shell Cordovan",
            "color": "Color 8",
            "size_us": 10,
            "width": "D",
            "_retailer": {"name": "Leffot", "country": "US"},
        },
    ]
    subject, html_body, text_body = mailer.render_email(matches)
    assert "1 new Alden match" in subject
    assert "Alden 405 Indy Boot Color 8" in html_body
    assert "https://leffot.com/products/alden-405" in html_body
    assert "Leffot" in html_body
    assert "Unsubscribe" in html_body
    assert "Alden 405 Indy Boot Color 8" in text_body


def test_filter_spec_roundtrips_through_alerts():
    spec = FilterSpec(lasts=["Trubalance"], sizes_us=[10.0], widths=["D"])
    as_json = spec.model_dump(mode="json")
    from alden_finder.alerts.matcher import _spec_from_json

    roundtripped = _spec_from_json(as_json)
    assert roundtripped.lasts == ["Trubalance"]
    assert roundtripped.sizes_us == [10.0]
    assert roundtripped.widths == ["D"]


def test_worker_dry_run_without_db_is_noop():
    # With no Supabase configured, pending_matches returns [] and worker exits 0.
    assert worker.run(dry_run=True) == 0
