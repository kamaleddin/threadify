"""Web content scraping with trafilatura and readability-lxml fallback."""

from collections.abc import Callable
from dataclasses import dataclass

import httpx
import trafilatura
from readability import Document


class ScraperError(Exception):
    """Raised when content scraping fails."""

    pass


@dataclass
class ScrapedContent:
    """Result of scraping a web page."""

    title: str
    text: str
    site_name: str | None
    word_count: int
    too_short: bool
    hero_candidates: list[str]
    metadata: dict[str, str]


def scrape(
    url: str,
    http_get: Callable[[str], httpx.Response] | None = None,
    min_word_count: int = 200,
    trafilatura_threshold: int = 100,
) -> ScrapedContent:
    """
    Scrape content from a URL using trafilatura with readability fallback.

    Strategy:
    1. Try trafilatura first (faster, better extraction)
    2. If trafilatura fails or returns < threshold words, try readability
    3. Extract metadata (og:image, twitter:image, etc.)
    4. Flag content as too_short if word_count < min_word_count

    Args:
        url: URL to scrape
        http_get: Optional HTTP client function (for testing/injection)
        min_word_count: Minimum word count to not flag as too_short
        trafilatura_threshold: Minimum words from trafilatura before trying fallback

    Returns:
        ScrapedContent with extracted data

    Raises:
        ScraperError: If scraping fails completely
    """
    # Fetch HTML
    if http_get is None:
        http_get = _default_http_get

    try:
        response = http_get(url)
        # Check status code manually (avoid raise_for_status for mock compatibility)
        if response.status_code >= 400:
            raise ScraperError(f"HTTP {response.status_code} error")
        html = response.text
    except ScraperError:
        raise
    except Exception as e:
        raise ScraperError(f"Failed to fetch URL: {e}") from e

    if not html or not html.strip():
        raise ScraperError("Empty HTML content")

    # Extract metadata first (works on original HTML)
    metadata = _extract_metadata(html)

    # Try trafilatura first
    title = None
    text = None

    try:
        extracted = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
            favor_precision=True,
        )

        if extracted:
            # Trafilatura doesn't return title separately, extract it
            title = _extract_title(html, metadata)
            text = extracted.strip()

            # Check if we got enough content
            word_count = len(text.split())
            if word_count >= trafilatura_threshold:
                # Trafilatura succeeded with good content
                return _build_result(
                    title=title,
                    text=text,
                    metadata=metadata,
                    min_word_count=min_word_count,
                )
    except Exception:
        # Trafilatura failed, will try readability
        pass

    # Fallback to readability-lxml
    try:
        doc = Document(html)
        title = doc.title() or _extract_title(html, metadata)
        text = _extract_text_from_html(doc.summary())

        if not text or not text.strip():
            raise ScraperError("No text content extracted")

        return _build_result(
            title=title, text=text, metadata=metadata, min_word_count=min_word_count
        )
    except Exception as e:
        raise ScraperError(f"Both trafilatura and readability failed: {e}") from e


def _default_http_get(url: str) -> httpx.Response:
    """
    Default HTTP GET function using httpx.

    Args:
        url: URL to fetch

    Returns:
        httpx.Response object
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    with httpx.Client(timeout=30.0, follow_redirects=True, headers=headers) as client:
        return client.get(url)


def _extract_metadata(html: str) -> dict[str, str]:
    """
    Extract metadata from HTML (og:*, twitter:*, etc.).

    Args:
        html: HTML content

    Returns:
        Dictionary of metadata
    """
    from html.parser import HTMLParser

    metadata: dict[str, str] = {}
    hero_images: list[str] = []

    class MetaParser(HTMLParser):
        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag == "meta":
                attr_dict = dict(attrs)
                property_val = attr_dict.get("property", "")
                name_val = attr_dict.get("name", "")
                content_val = attr_dict.get("content")

                if not content_val:
                    return

                # Open Graph metadata
                if property_val and property_val.startswith("og:"):
                    key = property_val
                    metadata[key] = content_val
                    if property_val == "og:image":
                        hero_images.append(content_val)

                # Twitter metadata
                if name_val and name_val.startswith("twitter:"):
                    key = name_val
                    metadata[key] = content_val
                    if name_val == "twitter:image":
                        hero_images.append(content_val)

                # Site name
                if name_val in ("application-name", "site_name"):
                    metadata["site_name"] = content_val

    parser = MetaParser()
    try:
        parser.feed(html)
    except Exception:
        # HTML parsing errors are non-fatal
        pass

    # Store hero candidates in metadata
    if hero_images:
        metadata["_hero_candidates"] = ",".join(hero_images)

    return metadata


def _extract_title(html: str, metadata: dict[str, str]) -> str:
    """
    Extract page title from HTML or metadata.

    Preference order:
    1. og:title
    2. twitter:title
    3. <title> tag
    4. "[no-title]"

    Args:
        html: HTML content
        metadata: Extracted metadata

    Returns:
        Page title
    """
    # Try metadata first
    if "og:title" in metadata and metadata["og:title"]:
        return metadata["og:title"].strip()
    if "twitter:title" in metadata and metadata["twitter:title"]:
        return metadata["twitter:title"].strip()

    # Try <title> tag
    from html.parser import HTMLParser

    class TitleParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.title = ""
            self.in_title = False

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag == "title":
                self.in_title = True

        def handle_endtag(self, tag: str) -> None:
            if tag == "title":
                self.in_title = False

        def handle_data(self, data: str) -> None:
            if self.in_title:
                self.title += data

    parser = TitleParser()
    try:
        parser.feed(html)
        if parser.title.strip():
            return parser.title.strip()
    except Exception:
        pass

    return "[no-title]"


def _extract_text_from_html(html: str) -> str:
    """
    Extract plain text from HTML, removing tags and normalizing whitespace.

    Args:
        html: HTML content

    Returns:
        Plain text with normalized whitespace
    """
    import re
    from html.parser import HTMLParser

    class TextExtractor(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.text_parts: list[str] = []
            self.skip_tags = {"script", "style", "noscript"}
            self.current_tag: str | None = None

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            self.current_tag = tag

        def handle_endtag(self, tag: str) -> None:
            self.current_tag = None

        def handle_data(self, data: str) -> None:
            if self.current_tag not in self.skip_tags:
                text = data.strip()
                if text:
                    self.text_parts.append(text)

    parser = TextExtractor()
    try:
        parser.feed(html)
        text = " ".join(parser.text_parts)
        # Normalize multiple spaces to single space
        text = re.sub(r"\s+", " ", text)
        return text.strip()
    except Exception:
        return ""


def _build_result(
    title: str, text: str, metadata: dict[str, str], min_word_count: int
) -> ScrapedContent:
    """
    Build ScrapedContent result from extracted data.

    Args:
        title: Page title
        text: Extracted text content
        metadata: Page metadata
        min_word_count: Minimum word count threshold

    Returns:
        ScrapedContent instance
    """
    # Count words
    word_count = len(text.split())

    # Extract hero candidates
    hero_candidates = []
    if "_hero_candidates" in metadata:
        hero_candidates = metadata["_hero_candidates"].split(",")
        # Remove from metadata (internal use only)
        metadata = {k: v for k, v in metadata.items() if k != "_hero_candidates"}

    # Extract site name
    site_name = metadata.get("og:site_name") or metadata.get("site_name")

    return ScrapedContent(
        title=title,
        text=text,
        site_name=site_name,
        word_count=word_count,
        too_short=word_count < min_word_count,
        hero_candidates=hero_candidates,
        metadata=metadata,
    )
