"""Integration test — requires live GolfBox access. Run manually, not in CI.

Usage: python -m pytest tests/test_golf_integration.py -v -s -m integration
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lambdas", "golf-scraper"))

# Skip if credentials not available
GOLFBOX_USER = os.environ.get("GOLFBOX_USERNAME", "edehvi")
GOLFBOX_PASS = os.environ.get("GOLFBOX_PASSWORD", "cuqj")


@pytest.mark.integration
def test_full_login_fetch_parse_pipeline():
    """Test the complete pipeline: login → fetch grid → parse slots."""
    from scraper import GolfBoxClient
    from parser import parse_grid_html

    client = GolfBoxClient(GOLFBOX_USER, GOLFBOX_PASS)
    assert client.login() is True

    # Fetch tomorrow's grid
    import datetime
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    html = client.fetch_grid(
        resource_guid="884D570B-7F66-4ECD-88E2-215E3B386422",
        club_guid="A85DA1E0-B469-4702-BDBC-4E8972EC50A9",
        date_str=tomorrow,
    )
    assert html is not None
    assert len(html) > 1000  # Should be a real page

    slots = parse_grid_html(html)
    assert isinstance(slots, dict)
    # Print for manual verification
    print(f"\n  Grid for {tomorrow}: {len(slots)} time slots found")
    for time_key, descs in sorted(slots.items())[:5]:
        print(f"    {time_key}: {descs}")
