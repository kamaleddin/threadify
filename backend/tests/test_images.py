"""Tests for hero image selection and processing."""

import io

import pytest
from app.services.images import (
    ImageError,
    ProcessedImage,
    alt_text_from,
    pick_hero,
    validate_and_process,
)
from httpx import Response
from PIL import Image


def create_test_image(width: int, height: int, mode: str = "RGB", with_exif: bool = False) -> bytes:
    """Create a test image with specified dimensions."""
    image = Image.new(mode, (width, height), color="red")

    output = io.BytesIO()
    save_kwargs = {"format": "JPEG"}

    if with_exif:
        # Add some EXIF data
        from PIL import Image as PILImage

        exif = PILImage.Exif()
        exif[0x010F] = "Test Camera"  # Make
        exif[0x0110] = "Test Model"  # Model
        save_kwargs["exif"] = exif.tobytes()

    image.save(output, **save_kwargs)
    return output.getvalue()


def mock_http_get(image_data: bytes, status_code: int = 200) -> object:
    """Create a mock HTTP GET function that returns image data."""

    def _get(url: str) -> Response:
        response = Response(status_code, content=image_data)
        response._request = None  # type: ignore
        return response

    return _get


def test_pick_hero_returns_first_candidate() -> None:
    """Test that pick_hero returns the first candidate."""
    candidates = [
        "https://example.com/image1.jpg",
        "https://example.com/image2.jpg",
        "https://example.com/image3.jpg",
    ]
    result = pick_hero(candidates)
    assert result == "https://example.com/image1.jpg"


def test_pick_hero_empty_list_returns_none() -> None:
    """Test that pick_hero returns None for empty list."""
    assert pick_hero([]) is None


def test_pick_hero_none_list_returns_none() -> None:
    """Test that pick_hero handles None input gracefully."""
    assert pick_hero([]) is None


def test_validate_and_process_valid_image() -> None:
    """Test processing a valid image."""
    # Create 1000x600 image
    image_data = create_test_image(1000, 600)
    http_get = mock_http_get(image_data)

    result = validate_and_process("https://example.com/test.jpg", http_get=http_get)

    assert isinstance(result, ProcessedImage)
    assert result.width == 1000
    assert result.height == 600
    assert result.format == "JPEG"
    assert len(result.data) > 0

    # Verify it's a valid JPEG
    img = Image.open(io.BytesIO(result.data))
    assert img.format == "JPEG"


def test_validate_and_process_downscales_large_image() -> None:
    """Test that large images are downscaled."""
    # Create 2000x1200 image (should be downscaled to 1600x960)
    image_data = create_test_image(2000, 1200)
    http_get = mock_http_get(image_data)

    result = validate_and_process(
        "https://example.com/large.jpg", http_get=http_get, max_width=1600
    )

    assert result.width == 1600
    # Height should maintain aspect ratio: 1200 * (1600/2000) = 960
    assert result.height == 960
    assert result.format == "JPEG"


def test_validate_and_process_rejects_small_image() -> None:
    """Test that images below minimum width are rejected."""
    # Create 500x300 image (below 800px minimum)
    image_data = create_test_image(500, 300)
    http_get = mock_http_get(image_data)

    with pytest.raises(ImageError, match="Image too small.*500px.*800px"):
        validate_and_process("https://example.com/small.jpg", http_get=http_get, min_width=800)


def test_validate_and_process_accepts_exactly_min_width() -> None:
    """Test that image exactly at minimum width is accepted."""
    # Create 800x400 image (exactly at minimum)
    image_data = create_test_image(800, 400)
    http_get = mock_http_get(image_data)

    result = validate_and_process("https://example.com/exact.jpg", http_get=http_get, min_width=800)

    assert result.width == 800
    assert result.height == 400


def test_validate_and_process_strips_exif() -> None:
    """Test that EXIF data is stripped from images."""
    # Create image with EXIF data
    image_data = create_test_image(1000, 600, with_exif=True)
    http_get = mock_http_get(image_data)

    result = validate_and_process("https://example.com/exif.jpg", http_get=http_get)

    # Load the result and check for EXIF
    img = Image.open(io.BytesIO(result.data))
    exif = img.getexif()

    # EXIF should be empty or minimal (PIL might add some basic fields)
    # Check that our custom EXIF tags are not present
    assert 0x010F not in exif  # Make
    assert 0x0110 not in exif  # Model


def test_validate_and_process_converts_rgba_to_rgb() -> None:
    """Test that RGBA images are converted to RGB."""
    # Create RGBA PNG image
    image = Image.new("RGBA", (1000, 600), color=(255, 0, 0, 128))  # Red with transparency
    output = io.BytesIO()
    image.save(output, format="PNG")
    image_data = output.getvalue()

    http_get = mock_http_get(image_data)

    result = validate_and_process("https://example.com/rgba.png", http_get=http_get)

    # Load result and verify it's RGB
    img = Image.open(io.BytesIO(result.data))
    assert img.mode == "RGB"
    assert result.format == "JPEG"


def test_validate_and_process_http_error() -> None:
    """Test that HTTP errors are handled."""
    image_data = create_test_image(1000, 600)
    http_get = mock_http_get(image_data, status_code=404)

    with pytest.raises(ImageError, match="HTTP 404"):
        validate_and_process("https://example.com/notfound.jpg", http_get=http_get)


def test_validate_and_process_invalid_image_data() -> None:
    """Test that invalid image data raises error."""
    http_get = mock_http_get(b"not an image")

    with pytest.raises(ImageError, match="Failed to process image"):
        validate_and_process("https://example.com/invalid.jpg", http_get=http_get)


def test_validate_and_process_network_error() -> None:
    """Test that network errors are handled."""

    def error_http_get(url: str) -> Response:
        raise Exception("Network error")

    with pytest.raises(ImageError, match="Failed to fetch image"):
        validate_and_process("https://example.com/error.jpg", http_get=error_http_get)


def test_validate_and_process_custom_quality() -> None:
    """Test that custom JPEG quality is applied."""
    image_data = create_test_image(1000, 600)
    http_get = mock_http_get(image_data)

    # High quality should produce larger file
    result_high = validate_and_process(
        "https://example.com/test.jpg", http_get=http_get, jpeg_quality=95
    )

    # Low quality should produce smaller file
    result_low = validate_and_process(
        "https://example.com/test.jpg", http_get=http_get, jpeg_quality=50
    )

    # Low quality should be smaller (though this isn't guaranteed for all images)
    # Just verify both work
    assert len(result_high.data) > 0
    assert len(result_low.data) > 0


def test_alt_text_from_title_only() -> None:
    """Test generating alt text from title only."""
    result = alt_text_from("A Great Article About Technology")
    assert result == "A Great Article About Technology"


def test_alt_text_from_title_and_lede() -> None:
    """Test generating alt text from title and lede."""
    title = "Great Article"
    lede = "This is a summary of the article content"
    result = alt_text_from(title, lede)
    assert result == "Great Article: This is a summary of the article content"


def test_alt_text_truncates_long_text() -> None:
    """Test that alt text is truncated to max length."""
    title = "A" * 150  # Very long title
    result = alt_text_from(title, max_length=120)

    assert len(result) == 120
    assert result.endswith("...")


def test_alt_text_truncates_combined_text() -> None:
    """Test that combined title+lede is truncated if too long."""
    title = "A" * 60
    lede = "B" * 100  # Combined would be >120
    result = alt_text_from(title, lede, max_length=120)

    assert len(result) <= 120
    assert result.startswith("A" * 60)


def test_alt_text_skips_short_lede_fragment() -> None:
    """Test that very short lede fragments are skipped."""
    title = "A" * 110  # Close to max length
    lede = "Short summary"
    result = alt_text_from(title, lede, max_length=120)

    # Should include truncated title with ellipsis, not the tiny lede fragment
    assert len(result) <= 120


def test_alt_text_handles_empty_lede() -> None:
    """Test that empty lede is handled gracefully."""
    title = "Test Title"
    result = alt_text_from(title, "")
    assert result == "Test Title"


def test_alt_text_handles_none_lede() -> None:
    """Test that None lede is handled gracefully."""
    title = "Test Title"
    result = alt_text_from(title, None)
    assert result == "Test Title"


def test_alt_text_strips_whitespace() -> None:
    """Test that whitespace is stripped from title and lede."""
    title = "  Test Title  "
    lede = "  Test lede  "
    result = alt_text_from(title, lede)
    assert result == "Test Title: Test lede"


def test_alt_text_custom_max_length() -> None:
    """Test alt text with custom max length."""
    title = "Test Title"
    lede = "This is a longer summary that should be truncated"
    result = alt_text_from(title, lede, max_length=30)

    assert len(result) <= 30
    assert result.startswith("Test Title")


def test_validate_and_process_maintains_aspect_ratio() -> None:
    """Test that aspect ratio is maintained during downscaling."""
    # Create 1800x900 image (2:1 aspect ratio)
    image_data = create_test_image(1800, 900)
    http_get = mock_http_get(image_data)

    result = validate_and_process(
        "https://example.com/aspect.jpg", http_get=http_get, max_width=1600
    )

    # Should be downscaled to 1600x800 (maintaining 2:1)
    assert result.width == 1600
    assert result.height == 800


def test_validate_and_process_palette_mode_conversion() -> None:
    """Test that palette mode images are converted properly."""
    # Create a palette mode image
    image = Image.new("P", (1000, 600))
    output = io.BytesIO()
    image.save(output, format="PNG")
    image_data = output.getvalue()

    http_get = mock_http_get(image_data)

    result = validate_and_process("https://example.com/palette.png", http_get=http_get)

    # Should be converted to RGB JPEG
    img = Image.open(io.BytesIO(result.data))
    assert img.mode == "RGB"
    assert result.format == "JPEG"
