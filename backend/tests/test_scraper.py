"""Tests for web content scraping."""

import pytest
from app.services.scraper import ScraperError, scrape
from httpx import Response

# Sample HTML fixtures
SAMPLE_BLOG_POST = """
<!DOCTYPE html>
<html>
<head>
    <title>A Great Blog Post</title>
    <meta property="og:title" content="A Great Blog Post - OpenGraph" />
    <meta property="og:site_name" content="Tech Blog" />
    <meta property="og:image" content="https://example.com/hero.jpg" />
    <meta name="twitter:image" content="https://example.com/twitter.jpg" />
</head>
<body>
    <article>
        <h1>A Great Blog Post</h1>
        <p>This is the first paragraph of an interesting blog post about technology.
        It contains valuable information that users want to read.</p>
        <p>Here is the second paragraph with more details and insights. We're adding
        enough content here to make sure this passes the word count threshold.</p>
        <p>Third paragraph continues the discussion with even more interesting points
        about the topic at hand. This ensures we have substantial content.</p>
        <p>Fourth paragraph wraps things up nicely with a conclusion and final thoughts
        that bring everything together in a meaningful way.</p>
    </article>
</body>
</html>
"""

MINIMAL_HTML = """
<!DOCTYPE html>
<html>
<head><title>Short Page</title></head>
<body><p>Just a few words here.</p></body>
</html>
"""

HTML_WITH_METADATA = """
<!DOCTYPE html>
<html>
<head>
    <title>HTML Title</title>
    <meta property="og:title" content="OpenGraph Title" />
    <meta name="twitter:title" content="Twitter Title" />
    <meta property="og:site_name" content="Example Site" />
    <meta property="og:image" content="https://example.com/image1.jpg" />
    <meta property="og:image" content="https://example.com/image2.jpg" />
</head>
<body>
    <h1>HTML Title</h1>
    <p>Content goes here with enough words to pass the threshold test.
    We need to make sure there are at least several sentences of content
    so that the word count is sufficient for testing purposes and to ensure
    we trigger the trafilatura path instead of falling back to readability.
    Additional sentences here help reach the minimum word count threshold.</p>
</body>
</html>
"""

HTML_WITH_NOISE = """
<!DOCTYPE html>
<html>
<head><title>Article with Noise</title></head>
<body>
    <script>var ads = "ignore this";</script>
    <style>.class { color: red; }</style>
    <article>
        <p>This is the actual content that should be extracted from the page.
        It contains meaningful text that the user wants to read and share.</p>
        <p>More content here to ensure we have enough words for testing.
        The scraper should ignore scripts and styles but keep this text.</p>
    </article>
    <noscript>Fallback content</noscript>
</body>
</html>
"""

EMPTY_HTML = """
<!DOCTYPE html>
<html>
<head><title>Empty</title></head>
<body></body>
</html>
"""


def mock_http_get(html_content: str) -> object:
    """Create a mock HTTP GET function that returns the given HTML."""

    def _get(url: str) -> Response:
        response = Response(200, text=html_content)
        response._request = None  # type: ignore
        return response

    return _get


def test_scrape_blog_post() -> None:
    """Test scraping a standard blog post."""
    http_get = mock_http_get(SAMPLE_BLOG_POST)
    result = scrape("https://example.com/post", http_get=http_get, min_word_count=50)

    assert result.title in ("A Great Blog Post", "A Great Blog Post - OpenGraph")
    assert len(result.text) > 100
    assert result.word_count > 50
    assert result.too_short is False  # 90 words > 50 threshold
    assert result.site_name == "Tech Blog"
    assert "https://example.com/hero.jpg" in result.hero_candidates


def test_scrape_extracts_metadata() -> None:
    """Test that metadata is correctly extracted."""
    http_get = mock_http_get(HTML_WITH_METADATA)
    # Use lower threshold to ensure we use trafilatura path
    result = scrape("https://example.com/meta", http_get=http_get, trafilatura_threshold=20)

    assert result.title == "OpenGraph Title"  # og:title takes precedence
    assert result.site_name == "Example Site"
    assert len(result.hero_candidates) >= 1
    assert "https://example.com/image1.jpg" in result.hero_candidates
    assert "og:title" in result.metadata
    assert "twitter:title" in result.metadata


def test_scrape_short_content_flagged() -> None:
    """Test that short content is flagged as too_short."""
    http_get = mock_http_get(MINIMAL_HTML)
    result = scrape("https://example.com/short", http_get=http_get, min_word_count=200)

    assert result.title == "Short Page"
    assert result.word_count < 200
    assert result.too_short is True


def test_scrape_filters_noise() -> None:
    """Test that scripts and styles are filtered out."""
    http_get = mock_http_get(HTML_WITH_NOISE)
    result = scrape("https://example.com/noise", http_get=http_get)

    assert "ignore this" not in result.text.lower()
    assert "color: red" not in result.text
    assert "actual content" in result.text.lower()
    assert result.word_count > 0


def test_scrape_empty_content_raises_error() -> None:
    """Test that empty HTML raises an error."""
    http_get = mock_http_get(EMPTY_HTML)

    with pytest.raises(ScraperError, match="No text content"):
        scrape("https://example.com/empty", http_get=http_get)


def test_scrape_http_error_raises_error() -> None:
    """Test that HTTP errors are handled."""

    def error_http_get(url: str) -> Response:
        raise Exception("Network error")

    with pytest.raises(ScraperError, match="Failed to fetch URL"):
        scrape("https://example.com/error", http_get=error_http_get)


def test_scrape_empty_response_raises_error() -> None:
    """Test that empty response raises an error."""
    http_get = mock_http_get("")

    with pytest.raises(ScraperError, match="Empty HTML content"):
        scrape("https://example.com/blank", http_get=http_get)


def test_scrape_title_fallback_order() -> None:
    """Test title extraction fallback order."""
    # HTML with only <title> tag
    html_title_only = """
    <!DOCTYPE html>
    <html>
    <head><title>HTML Title Only</title></head>
    <body><p>Content here with enough words to pass the minimum threshold
    for testing purposes. We need several sentences to make this work.</p></body>
    </html>
    """
    http_get = mock_http_get(html_title_only)
    result = scrape("https://example.com/title", http_get=http_get)
    assert result.title == "HTML Title Only"


def test_scrape_no_title_uses_fallback() -> None:
    """Test that missing title uses '[no-title]' fallback."""
    html_no_title = """
    <!DOCTYPE html>
    <html>
    <body><p>Content without a title tag but with enough words to pass
    the minimum word count threshold for our scraping tests.</p></body>
    </html>
    """
    http_get = mock_http_get(html_no_title)
    result = scrape("https://example.com/notitle", http_get=http_get)
    assert result.title == "[no-title]"


def test_scrape_custom_thresholds() -> None:
    """Test custom word count thresholds."""
    http_get = mock_http_get(MINIMAL_HTML)

    # Low threshold - should not be flagged as too short
    result1 = scrape("https://example.com/custom", http_get=http_get, min_word_count=5)
    assert result1.too_short is False

    # High threshold - should be flagged
    result2 = scrape("https://example.com/custom", http_get=http_get, min_word_count=500)
    assert result2.too_short is True


def test_scrape_readability_fallback() -> None:
    """Test that readability is used when trafilatura returns insufficient content."""
    # HTML that trafilatura might struggle with but readability can handle
    tricky_html = """
    <!DOCTYPE html>
    <html>
    <head><title>Tricky Page</title></head>
    <body>
        <div class="content">
            <h1>Main Article</h1>
            <p>This is the main content of the article with sufficient words
            to ensure that we pass all the word count thresholds.</p>
            <p>Additional paragraph with more information and details about
            the topic being discussed in this particular article.</p>
        </div>
    </body>
    </html>
    """
    http_get = mock_http_get(tricky_html)
    result = scrape("https://example.com/tricky", http_get=http_get)

    # Should extract content successfully (either via trafilatura or readability)
    assert result.title == "Tricky Page"
    assert result.word_count > 10
    assert "main content" in result.text.lower()


def test_scrape_hero_candidates_from_metadata() -> None:
    """Test extraction of multiple hero image candidates."""
    http_get = mock_http_get(HTML_WITH_METADATA)
    result = scrape("https://example.com/images", http_get=http_get)

    # Should have collected both og:image entries
    assert len(result.hero_candidates) >= 1
    assert any("image1.jpg" in url for url in result.hero_candidates)


def test_scrape_whitespace_normalization() -> None:
    """Test that whitespace in extracted text is normalized."""
    html_whitespace = """
    <!DOCTYPE html>
    <html>
    <head><title>Whitespace Test</title></head>
    <body>
        <p>First    sentence    with    extra    spaces.</p>
        <p>Second sentence follows after some content padding to ensure
        we have enough words for the minimum threshold requirement.</p>
    </body>
    </html>
    """
    http_get = mock_http_get(html_whitespace)
    result = scrape("https://example.com/whitespace", http_get=http_get)

    # Should normalize whitespace
    assert "    " not in result.text  # No excessive spaces
    assert len(result.text) > 0
