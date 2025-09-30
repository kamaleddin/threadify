"""Tests for URL canonicalization."""

import pytest
from app.services.canonicalize import CanonicalizationError, canonicalize
from httpx import Response


def test_canonicalize_adds_https_scheme() -> None:
    """Test that URLs without scheme get https:// added."""
    url = "example.com/path"
    result = canonicalize(url, follow_redirects=False)
    assert result.startswith("https://")
    assert "example.com/path" in result


def test_canonicalize_lowercases_host() -> None:
    """Test that host is lowercased."""
    url = "https://Example.COM/path"
    result = canonicalize(url, follow_redirects=False)
    assert result == "https://example.com/path"


def test_canonicalize_removes_www() -> None:
    """Test that www. prefix is removed."""
    url = "https://www.example.com/path"
    result = canonicalize(url, follow_redirects=False)
    assert result == "https://example.com/path"


def test_canonicalize_removes_fragment() -> None:
    """Test that URL fragments are removed."""
    url = "https://example.com/path#section"
    result = canonicalize(url, follow_redirects=False)
    assert result == "https://example.com/path"
    assert "#" not in result


def test_canonicalize_removes_tracking_params() -> None:
    """Test that common tracking parameters are removed."""
    url = "https://example.com/path?utm_source=twitter&utm_campaign=test&id=123"
    result = canonicalize(url, follow_redirects=False)
    assert "utm_source" not in result
    assert "utm_campaign" not in result
    assert "id=123" in result  # Non-tracking param preserved


def test_canonicalize_removes_trailing_slash() -> None:
    """Test that trailing slash is removed from paths."""
    url = "https://example.com/path/"
    result = canonicalize(url, follow_redirects=False)
    assert result == "https://example.com/path"


def test_canonicalize_keeps_root_slash() -> None:
    """Test that root path keeps its slash."""
    url = "https://example.com/"
    result = canonicalize(url, follow_redirects=False)
    assert result == "https://example.com/"


def test_canonicalize_upgrades_http_to_https() -> None:
    """Test that HTTP is upgraded to HTTPS."""
    url = "http://example.com/path"
    result = canonicalize(url, follow_redirects=False)
    assert result.startswith("https://")


def test_canonicalize_sorts_query_params() -> None:
    """Test that query parameters are sorted alphabetically."""
    url = "https://example.com/path?z=1&a=2&m=3"
    result = canonicalize(url, follow_redirects=False)
    # Parameters should be sorted: a, m, z
    assert result == "https://example.com/path?a=2&m=3&z=1"


def test_canonicalize_removes_default_ports() -> None:
    """Test that default ports are removed."""
    # HTTP default port 80
    url1 = "http://example.com:80/path"
    result1 = canonicalize(url1, follow_redirects=False)
    assert ":80" not in result1

    # HTTPS default port 443
    url2 = "https://example.com:443/path"
    result2 = canonicalize(url2, follow_redirects=False)
    assert ":443" not in result2


def test_canonicalize_preserves_non_default_ports() -> None:
    """Test that non-default ports are preserved."""
    url = "https://example.com:8080/path"
    result = canonicalize(url, follow_redirects=False)
    assert ":8080" in result


def test_canonicalize_handles_multiple_tracking_params() -> None:
    """Test removing multiple tracking parameters."""
    url = "https://example.com/?fbclid=123&utm_source=fb&gclid=456&real_param=value"
    result = canonicalize(url, follow_redirects=False)
    assert "fbclid" not in result
    assert "utm_source" not in result
    assert "gclid" not in result
    assert "real_param=value" in result


def test_canonicalize_empty_url_raises_error() -> None:
    """Test that empty URL raises error."""
    with pytest.raises(CanonicalizationError, match="cannot be empty"):
        canonicalize("")


def test_canonicalize_whitespace_url_raises_error() -> None:
    """Test that whitespace-only URL raises error."""
    with pytest.raises(CanonicalizationError, match="cannot be empty"):
        canonicalize("   ")


def test_canonicalize_invalid_url_raises_error() -> None:
    """Test that invalid URL raises error."""
    # A URL that will fail parsing due to invalid characters in the scheme
    with pytest.raises(CanonicalizationError, match="valid domain"):
        canonicalize("https://")


def test_canonicalize_no_domain_raises_error() -> None:
    """Test that URL without domain raises error."""
    with pytest.raises(CanonicalizationError, match="valid domain"):
        canonicalize("https:///path/only")


def test_canonicalize_complex_url() -> None:
    """Test canonicalization of a complex URL with many features."""
    url = "HTTP://WWW.Example.COM:443/Path/To/Page/?utm_campaign=test&z=last&a=first&fbclid=track#section"
    result = canonicalize(url, follow_redirects=False)

    assert result == "https://example.com/Path/To/Page?a=first&z=last"
    # Should have: https, no www, lowercase domain, no :443, sorted params, no tracking, no fragment


def test_canonicalize_with_redirect() -> None:
    """Test following a simple redirect."""

    def mock_http_get(url: str) -> Response:
        if url == "https://example.com/old":
            return Response(status_code=301, headers={"location": "https://example.com/new"})
        return Response(status_code=200)

    url = "https://example.com/old"
    result = canonicalize(url, http_get=mock_http_get, follow_redirects=True)
    assert result == "https://example.com/new"


def test_canonicalize_with_multiple_redirects() -> None:
    """Test following multiple redirects."""

    def mock_http_get(url: str) -> Response:
        if url == "https://example.com/1":
            return Response(status_code=302, headers={"location": "https://example.com/2"})
        elif url == "https://example.com/2":
            return Response(status_code=302, headers={"location": "https://example.com/final"})
        return Response(status_code=200)

    url = "https://example.com/1"
    result = canonicalize(url, http_get=mock_http_get, follow_redirects=True)
    assert result == "https://example.com/final"


def test_canonicalize_with_relative_redirect() -> None:
    """Test following a relative redirect."""

    def mock_http_get(url: str) -> Response:
        if url == "https://example.com/old":
            return Response(status_code=301, headers={"location": "/new"})
        return Response(status_code=200)

    url = "https://example.com/old"
    result = canonicalize(url, http_get=mock_http_get, follow_redirects=True)
    assert result == "https://example.com/new"


def test_canonicalize_redirect_loop_detected() -> None:
    """Test that redirect loops are detected."""

    def mock_http_get(url: str) -> Response:
        if url == "https://example.com/a":
            return Response(status_code=301, headers={"location": "https://example.com/b"})
        elif url == "https://example.com/b":
            return Response(status_code=301, headers={"location": "https://example.com/a"})
        return Response(status_code=200)

    url = "https://example.com/a"
    with pytest.raises(CanonicalizationError, match="Redirect loop"):
        canonicalize(url, http_get=mock_http_get, follow_redirects=True)


def test_canonicalize_too_many_redirects() -> None:
    """Test that too many redirects raises error."""

    redirect_count = 0

    def mock_http_get(url: str) -> Response:
        nonlocal redirect_count
        redirect_count += 1
        return Response(
            status_code=301, headers={"location": f"https://example.com/{redirect_count}"}
        )

    url = "https://example.com/start"
    with pytest.raises(CanonicalizationError, match="Too many redirects"):
        canonicalize(url, http_get=mock_http_get, follow_redirects=True, max_redirects=3)


def test_canonicalize_redirect_without_location_header() -> None:
    """Test that redirect without location header returns current URL."""

    def mock_http_get(url: str) -> Response:
        return Response(status_code=301, headers={})  # No location header

    url = "https://example.com/page"
    result = canonicalize(url, http_get=mock_http_get, follow_redirects=True)
    assert result == "https://example.com/page"


def test_canonicalize_http_error_returns_url() -> None:
    """Test that HTTP errors don't break canonicalization."""

    def mock_http_get(url: str) -> Response:
        raise Exception("Network error")

    url = "https://example.com/page"
    # Should still canonicalize the URL even if we can't fetch it
    result = canonicalize(url, http_get=mock_http_get, follow_redirects=True)
    assert result == "https://example.com/page"


def test_canonicalize_preserves_path_case() -> None:
    """Test that path case is preserved (only host is lowercased)."""
    url = "https://example.com/Path/To/Page"
    result = canonicalize(url, follow_redirects=False)
    assert "/Path/To/Page" in result


def test_canonicalize_handles_query_with_multiple_values() -> None:
    """Test handling query parameters with multiple values."""
    url = "https://example.com/page?tag=python&tag=coding&id=1"
    result = canonicalize(url, follow_redirects=False)
    # Both tag values should be preserved and sorted
    assert "tag=python" in result
    assert "tag=coding" in result
    assert "id=1" in result


def test_canonicalize_no_redirects_when_disabled() -> None:
    """Test that redirects are not followed when disabled."""

    def mock_http_get(url: str) -> Response:
        return Response(status_code=301, headers={"location": "https://example.com/new"})

    url = "https://example.com/old"
    result = canonicalize(url, http_get=mock_http_get, follow_redirects=False)
    # Should return canonicalized original URL, not redirected
    assert result == "https://example.com/old"


def test_canonicalize_strips_whitespace() -> None:
    """Test that whitespace is stripped from input URL."""
    url = "  https://example.com/path  "
    result = canonicalize(url, follow_redirects=False)
    assert result == "https://example.com/path"
