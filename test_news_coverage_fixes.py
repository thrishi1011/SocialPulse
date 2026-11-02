import asyncio
from datetime import datetime, timedelta
import pytest
import httpx
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import settings
from backend.database import SessionLocal
from backend.models import Source, Category, TrendingItem
from backend.services.news_coverage import (
    MAX_ARTICLES_PER_PLATFORM,
    is_topically_relevant,
    normalize_url,
    normalize_title_tokens,
    is_near_duplicate_title,
    _url_decode_cache,
    decode_url_safe,
    _fetch_from_outlet
)
from backend.fetchers.instagram_news_fetcher import InstagramNewsFetcher

client = TestClient(app)

def test_cap_raise():
    """Verify MAX_ARTICLES_PER_PLATFORM is raised to 80."""
    assert MAX_ARTICLES_PER_PLATFORM == 80

def test_twitter_x_relevance_regex():
    """Verify bare 'X' (e.g. Model X, iPhone X) does not match, but real X/Twitter context matches."""
    # Irrelevant: bare 'X' in product names without Twitter context
    assert not is_topically_relevant("Tesla unveils new Model X SUV in India", "Great car specs", "Twitter")
    assert not is_topically_relevant("Apple discontinues iPhone X accessories", "Old phone parts", "Twitter")
    assert not is_topically_relevant("Generation X retirement savings report", "Demographic study", "Twitter")

    # Relevant: genuine Twitter / X posts, debates, hashtags, policies
    assert is_topically_relevant("Outcry on X as users protest new verification rules", "Viral debate", "Twitter")
    assert is_topically_relevant("Viral tweet sparks controversy over political campaign", "Online reaction", "Twitter")
    assert is_topically_relevant("Minister statement on X (formerly Twitter) goes viral", "Debate in parliament", "Twitter")
    assert is_topically_relevant("Elon Musk announces major X algorithm update", "Creator outcry", "Twitter")
    assert is_topically_relevant("Trending hashtag on X leads to government inquiry", "Breaking news", "Twitter")

def test_deduplication_url_and_title():
    """Verify URL normalization strips tracking params and near-duplicate title detection works."""
    url1 = "https://www.thehindu.com/news/national/story.html?utm_source=twitter&utm_medium=social#comments"
    url2 = "https://www.thehindu.com/news/national/story.html"
    assert normalize_url(url1) == normalize_url(url2)

    title_tokens = [normalize_title_tokens("Delhi Government Issues Urgent Notice on Air Pollution Trend")]
    dup_title = "Delhi Government Issues Urgent Notice on Air Pollution Crisis"
    diff_title = "Mumbai Monsoon Season Brings Heavy Waterlogging Across Suburbs"

    assert is_near_duplicate_title(dup_title, title_tokens, threshold=0.7)
    assert not is_near_duplicate_title(diff_title, title_tokens, threshold=0.7)

@pytest.mark.asyncio
async def test_url_decode_cache():
    """Verify Google News decoded URLs are cached and returned directly from cache."""
    mock_raw_url = "https://news.google.com/articles/CBMiTWh0dHBzOi8vd3d3LmluZGlhbmV4cHJlc3MuY29tL2FydGljbGUvaW5kaWEvbW9kZXJhdGlvbi1yZXZpZXctb24teC0xMjM0NTY3Lw"
    mock_clean_url = "https://www.indianexpress.com/article/india/moderation-review-on-x-1234567/"

    _url_decode_cache[mock_raw_url] = mock_clean_url
    result = await decode_url_safe(mock_raw_url)
    assert result == mock_clean_url

@pytest.mark.asyncio
async def test_html_fallback_fix():
    """Verify that when RSS returns HTTP 200 with 0 articles, HTML section scraper executes."""
    empty_rss_xml = '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Empty</title></channel></rss>'
    html_page = """
    <html>
      <body>
        <a href="https://example-news.com/news/instagram-viral-reel-trend-sparks-debate-2026/">
          Instagram viral reel trend sparks massive debate among creators
        </a>
      </body>
    </html>
    """

    class MockTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if "feed" in url_str:
                return httpx.Response(200, text=empty_rss_xml, request=request)
            return httpx.Response(200, text=html_page, request=request)

    async with httpx.AsyncClient(transport=MockTransport()) as client:
        outlet_config = {
            "name": "Mock Test Outlet",
            "base_domain": "https://example-news.com",
            "rss_url": "https://example-news.com/feed",
            "section_urls": ["https://example-news.com/trending"]
        }
        stats = {"Mock Test Outlet": {"found": 0, "kept": 0, "failed": 0}}
        articles = await _fetch_from_outlet(client, outlet_config, "Instagram", stats)

        assert len(articles) > 0
        assert "Instagram" in articles[0]["title"]
        assert articles[0]["source"]["name"] == "Mock Test Outlet"

@pytest.mark.asyncio
async def test_no_mock_topup_in_live_mode_for_category_b():
    """Verify Category B sources in live mode do not pad results with fake sample/example.com mock data."""
    fetcher = InstagramNewsFetcher()
    assert fetcher.source_category == "B"

    # In live mode, even if fetch_raw returns empty, fallback mock or mock top-up must NOT run for Category B
    fetcher.fetch_raw = lambda: asyncio.sleep(0.01, result=[])
    db = SessionLocal()
    try:
        result = await fetcher.execute(db, force_live=True)
        # Should not fall back to mock
        assert result.status != "fallback_mock"

        # Verify no items with example.com exist for this source
        src = db.query(Source).filter(Source.slug == fetcher.slug).first()
        if src:
            example_items = db.query(TrendingItem).filter(
                TrendingItem.source_id == src.id,
                TrendingItem.url.like("%example.com%")
            ).count()
            assert example_items == 0
    finally:
        db.close()

def test_window_widening():
    """Verify that when a Category B news platform has few items in 24h, the API widens the window and returns window_widened_to."""
    client = TestClient(app)
    db = SessionLocal()
    temp_source_slug = "test_widening_news"
    temp_src = None
    try:
        # Create a dedicated Category B source for this test so production items are never deleted
        temp_src = db.query(Source).filter(Source.slug == temp_source_slug).first()
        if not temp_src:
            temp_src = Source(
                slug=temp_source_slug,
                display_name="Test Widening News",
                source_category="B",
                source_type_label="News Coverage",
                is_enabled=True
            )
            db.add(temp_src)
            db.commit()
            db.refresh(temp_src)

        # Clear any prior test items for this test source
        db.query(TrendingItem).filter(TrendingItem.source_id == temp_src.id).delete()
        db.commit()

        # Insert 3 items in 24h (less than 20)
        for i in range(3):
            db.add(TrendingItem(
                source_id=temp_src.id,
                external_id=f"test_widening_24h_{i}",
                title=f"Test viral political campaign debate trend {i}",
                url=f"https://verified-news.in/tech/test-trend-{i}",
                published_at=datetime.utcnow() - timedelta(hours=4),
                fetched_at=datetime.utcnow() - timedelta(hours=4),
                source_category="B",
                ai_processed=True
            ))

        # Insert 22 items in past 5 days (within 7d window)
        for i in range(22):
            db.add(TrendingItem(
                source_id=temp_src.id,
                external_id=f"test_widening_7d_{i}",
                title=f"Test minister reel controversy on political policy {i}",
                url=f"https://verified-news.in/tech/test-minister-policy-{i}",
                published_at=datetime.utcnow() - timedelta(days=4),
                fetched_at=datetime.utcnow() - timedelta(days=4),
                source_category="B",
                ai_processed=True
            ))
        db.commit()

        # Query /api/v1/trends with source=test_widening_news and recency=24h
        resp = client.get(f"/api/v1/trends?source={temp_source_slug}&recency=24h")
        assert resp.status_code == 200
        data = resp.json()

        # Window widening should trigger because 3 < 20 in 24h
        assert data.get("window_widened_to") in ["3d", "7d", "30d", "all"]
        assert data.get("original_window_count") == 3
        # Should now return >= 20 items because the window widened to include 7d items
        assert data.get("total") >= 20
    finally:
        if temp_src:
            db.query(TrendingItem).filter(TrendingItem.source_id == temp_src.id).delete()
            db.query(Source).filter(Source.id == temp_src.id).delete()
            db.commit()
        db.close()
