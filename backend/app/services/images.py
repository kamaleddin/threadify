"""Hero image selection and processing for tweets."""

import io
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from PIL import Image


class ImageError(Exception):
    """Raised when image processing fails."""

    pass


@dataclass
class ProcessedImage:
    """Result of image processing."""

    data: bytes
    width: int
    height: int
    format: str = "JPEG"


def pick_hero(candidates: list[str]) -> str | None:
    """
    Pick the best hero image from a list of candidates.

    Selection order:
    1. First og:image (if present)
    2. First twitter:image (if present)
    3. None (no suitable candidate)

    Args:
        candidates: List of image URLs

    Returns:
        Selected image URL or None
    """
    if not candidates:
        return None

    # For now, just return the first candidate
    # In a more sophisticated implementation, we could:
    # - Filter by domain/source
    # - Fetch and validate dimensions
    # - Score by position in list
    return candidates[0] if candidates else None


def validate_and_process(
    image_url: str,
    http_get: Callable[[str], httpx.Response] | None = None,
    min_width: int = 800,
    max_width: int = 1600,
    jpeg_quality: int = 85,
) -> ProcessedImage:
    """
    Validate and process an image for use as a hero image.

    Processing steps:
    1. Download image
    2. Validate minimum width (>= min_width)
    3. Downscale if width > max_width
    4. Strip EXIF metadata
    5. Re-encode as JPEG

    Args:
        image_url: URL of the image to process
        http_get: Optional HTTP client function (for testing/injection)
        min_width: Minimum acceptable width in pixels
        max_width: Maximum width before downscaling
        jpeg_quality: JPEG quality (1-100)

    Returns:
        ProcessedImage with processed image data and dimensions

    Raises:
        ImageError: If image is too small, invalid, or processing fails
    """
    # Fetch image
    if http_get is None:
        http_get = _default_http_get

    try:
        response = http_get(image_url)
        if response.status_code >= 400:
            raise ImageError(f"HTTP {response.status_code} error")
        image_bytes = response.content
    except ImageError:
        raise
    except Exception as e:
        raise ImageError(f"Failed to fetch image: {e}") from e

    try:
        # Open image
        image = Image.open(io.BytesIO(image_bytes))

        # Validate minimum width
        if image.width < min_width:
            raise ImageError(f"Image too small: {image.width}px wide (minimum {min_width}px)")

        # Convert to RGB if necessary (for JPEG compatibility)
        if image.mode in ("RGBA", "P", "LA"):
            # Create white background for transparent images
            rgb_image = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")  # type: ignore[assignment]
            rgb_image.paste(image, mask=image.split()[-1] if image.mode in ("RGBA", "LA") else None)
            image = rgb_image  # type: ignore[assignment]
        elif image.mode != "RGB":
            image = image.convert("RGB")  # type: ignore[assignment]

        # Downscale if too large
        if image.width > max_width:
            # Calculate new height maintaining aspect ratio
            new_width = max_width
            new_height = int((max_width / image.width) * image.height)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)  # type: ignore[assignment]

        # Strip EXIF by not copying it
        # (When we save to a new BytesIO, EXIF is not included by default)

        # Re-encode as JPEG
        output = io.BytesIO()
        image.save(
            output,
            format="JPEG",
            quality=jpeg_quality,
            optimize=True,
            exif=b"",  # Explicitly strip EXIF
        )
        output.seek(0)

        return ProcessedImage(
            data=output.getvalue(),
            width=image.width,
            height=image.height,
            format="JPEG",
        )

    except ImageError:
        raise
    except Exception as e:
        raise ImageError(f"Failed to process image: {e}") from e


def alt_text_from(title: str, lede: str | None = None, max_length: int = 120) -> str:
    """
    Generate alt text for an image from article title and lede.

    Args:
        title: Article title
        lede: Optional article lede/summary
        max_length: Maximum length of alt text (default 120 chars)

    Returns:
        Alt text string, truncated to max_length
    """
    # Start with title
    alt = title.strip()

    # Add lede if provided and there's room
    if lede and lede.strip():
        lede = lede.strip()
        # Add separator if we have both title and lede
        combined = f"{alt}: {lede}"
        if len(combined) <= max_length:
            alt = combined
        elif len(alt) < max_length:
            # Truncate lede to fit
            remaining = max_length - len(alt) - 2  # -2 for ": "
            if remaining > 10:  # Only add if meaningful
                alt = f"{alt}: {lede[:remaining]}..."

    # Truncate if still too long
    if len(alt) > max_length:
        alt = alt[: max_length - 3] + "..."

    return alt


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
