"""URL canonicalization for deduplication and normalization."""

from collections.abc import Callable
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx


class CanonicalizationError(Exception):
    """Raised when URL canonicalization fails."""

    pass


# Common tracking parameters to remove
TRACKING_PARAMS = {
    # Google Analytics
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    # Facebook
    "fbclid",
    "fb_action_ids",
    "fb_action_types",
    "fb_ref",
    "fb_source",
    # Twitter
    "twclid",
    # Other common tracking
    "gclid",  # Google Click ID
    "msclkid",  # Microsoft Click ID
    "mc_cid",  # Mailchimp Campaign ID
    "mc_eid",  # Mailchimp Email ID
    "_hsenc",  # HubSpot
    "_hsmi",  # HubSpot
    "mkt_tok",  # Marketo
    # General
    "ref",
    "source",
}


def canonicalize(
    url: str,
    http_get: Callable[[str], httpx.Response] | None = None,
    follow_redirects: bool = True,
    max_redirects: int = 5,
) -> str:
    """
    Canonicalize a URL for consistent comparison and deduplication.

    Rules applied:
    1. Add https:// scheme if missing
    2. Follow HTTP redirects to final destination (if follow_redirects=True)
    3. Normalize host: lowercase, strip 'www.' prefix
    4. Remove URL fragments (#...)
    5. Remove common tracking parameters
    6. Remove trailing slash from path (except for root /)
    7. Normalize query string parameter order

    Args:
        url: URL to canonicalize
        http_get: Optional HTTP client function (for testing/injection)
        follow_redirects: Whether to follow HTTP redirects
        max_redirects: Maximum number of redirects to follow

    Returns:
        Canonicalized URL string

    Raises:
        CanonicalizationError: If URL is malformed or redirect loop detected
    """
    if not url or not url.strip():
        raise CanonicalizationError("URL cannot be empty")

    url = url.strip()

    # Add scheme if missing (case-insensitive check)
    url_lower = url.lower()
    if not url_lower.startswith(("http://", "https://")):
        url = f"https://{url}"

    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise CanonicalizationError(f"Invalid URL: {e}") from e

    if not parsed.netloc:
        raise CanonicalizationError("URL must have a valid domain")

    # Follow redirects if requested
    if follow_redirects:
        if http_get is None:
            # Use default httpx client
            http_get = _default_http_get

        url = _follow_redirects(url, http_get, max_redirects)
        # Re-parse after following redirects
        try:
            parsed = urlparse(url)
        except Exception as e:
            raise CanonicalizationError(f"Invalid URL after redirects: {e}") from e

    # Normalize host
    host = parsed.netloc.lower()

    # Strip 'www.' prefix
    if host.startswith("www."):
        host = host[4:]

    # Ensure HTTPS (upgrade from HTTP)
    scheme = "https"

    # Remove port if it's the default for the target scheme (https)
    # Check both http:80 and https:443 since we're upgrading to https
    if ":" in host:
        hostname, port = host.rsplit(":", 1)
        if port in ("80", "443"):
            host = hostname

    # Normalize path
    path = parsed.path or "/"

    # Remove trailing slash (except for root)
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # Normalize query parameters
    query = ""
    if parsed.query:
        params = parse_qs(parsed.query, keep_blank_values=True)

        # Remove tracking parameters
        filtered_params = {k: v for k, v in params.items() if k.lower() not in TRACKING_PARAMS}

        # Sort parameters for consistency
        if filtered_params:
            # Convert lists back to single values where appropriate
            sorted_params = []
            for key in sorted(filtered_params.keys()):
                values = filtered_params[key]
                for value in values:
                    sorted_params.append((key, value))
            query = urlencode(sorted_params)

    # Fragment is always removed (set to empty)
    fragment = ""

    # Reconstruct URL
    canonical_url = urlunparse((scheme, host, path, "", query, fragment))

    return canonical_url


def _default_http_get(url: str) -> httpx.Response:
    """
    Default HTTP GET function using httpx.

    Args:
        url: URL to fetch

    Returns:
        httpx.Response object
    """
    with httpx.Client(follow_redirects=False, timeout=10.0) as client:
        return client.get(url)


def _follow_redirects(
    url: str, http_get: Callable[[str], httpx.Response], max_redirects: int
) -> str:
    """
    Follow HTTP redirects to the final destination.

    Args:
        url: Starting URL
        http_get: HTTP client function
        max_redirects: Maximum number of redirects to follow

    Returns:
        Final URL after all redirects

    Raises:
        CanonicalizationError: If too many redirects or redirect loop detected
    """
    visited = set()
    current_url = url

    for _ in range(max_redirects):
        if current_url in visited:
            raise CanonicalizationError(f"Redirect loop detected: {current_url}")

        visited.add(current_url)

        try:
            response = http_get(current_url)
        except Exception:
            # If we can't fetch the URL, return the current URL
            # This allows canonicalization to proceed even if the URL is unreachable
            return current_url

        # Check for redirect status codes
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("location")
            if not location:
                return current_url

            # Handle relative redirects
            if not location.startswith(("http://", "https://")):
                parsed_current = urlparse(current_url)
                if location.startswith("/"):
                    # Absolute path
                    location = f"{parsed_current.scheme}://{parsed_current.netloc}{location}"
                else:
                    # Relative path
                    base_path = parsed_current.path.rsplit("/", 1)[0]
                    location = (
                        f"{parsed_current.scheme}://{parsed_current.netloc}{base_path}/{location}"
                    )

            current_url = location
        else:
            # Not a redirect, return current URL
            return current_url

    # Exceeded max redirects
    raise CanonicalizationError(f"Too many redirects (>{max_redirects})")
