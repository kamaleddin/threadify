"""Tests for the length service HTTP client."""

import pytest
from httpx import Response

from app.clients.length_client import LengthClient, LengthServiceError


@pytest.fixture
def mock_httpx_client(monkeypatch: pytest.MonkeyPatch) -> list:
    """Mock httpx.Client to capture requests."""
    requests = []

    class MockResponse:
        def __init__(self, json_data: dict, status_code: int = 200):
            self.json_data = json_data
            self.status_code = status_code

        def json(self):
            return self.json_data

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception(f"HTTP {self.status_code}")

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def post(self, url: str, json: dict):
            requests.append({"url": url, "json": json})

            # Return mocked responses based on the request
            if "/length/check" in url:
                text = json.get("text", "")
                return MockResponse(
                    {
                        "isValid": len(text) > 0 and len(text) <= 280,
                        "weightedLength": len(text),
                        "permillage": int((len(text) / 280) * 1000),
                        "validRange": {"start": 0, "end": 280},
                    }
                )
            elif "/length/batch" in url:
                texts = json.get("texts", [])
                return MockResponse(
                    {
                        "results": [
                            {
                                "isValid": len(text) > 0 and len(text) <= 280,
                                "weightedLength": len(text),
                                "permillage": int((len(text) / 280) * 1000),
                                "validRange": {"start": 0, "end": 280},
                            }
                            for text in texts
                        ]
                    }
                )

        def close(self):
            pass

    import httpx

    monkeypatch.setattr(httpx, "Client", MockClient)
    return requests


def test_length_client_check_valid_text(mock_httpx_client: list) -> None:
    """Test checking a valid tweet."""
    client = LengthClient(base_url="http://test:8080")
    result = client.check("Hello world")

    assert result.is_valid is True
    assert result.weighted_length == 11
    assert result.valid_range.start == 0
    assert result.valid_range.end == 280

    # Verify request was made
    assert len(mock_httpx_client) == 1
    assert mock_httpx_client[0]["url"] == "http://test:8080/length/check"
    assert mock_httpx_client[0]["json"] == {"text": "Hello world"}


def test_length_client_check_empty_text(mock_httpx_client: list) -> None:
    """Test checking empty text."""
    client = LengthClient(base_url="http://test:8080")
    result = client.check("")

    assert result.is_valid is False
    assert result.weighted_length == 0


def test_length_client_check_long_text(mock_httpx_client: list) -> None:
    """Test checking text over 280 characters."""
    client = LengthClient(base_url="http://test:8080")
    long_text = "a" * 300
    result = client.check(long_text)

    assert result.is_valid is False
    assert result.weighted_length == 300


def test_length_client_check_batch(mock_httpx_client: list) -> None:
    """Test checking multiple tweets in batch."""
    client = LengthClient(base_url="http://test:8080")
    results = client.check_batch(["First", "Second", "Third"])

    assert len(results) == 3
    assert all(r.is_valid is True for r in results)
    assert results[0].weighted_length == 5
    assert results[1].weighted_length == 6
    assert results[2].weighted_length == 5

    # Verify request
    assert len(mock_httpx_client) == 1
    assert mock_httpx_client[0]["url"] == "http://test:8080/length/batch"
    assert mock_httpx_client[0]["json"] == {"texts": ["First", "Second", "Third"]}


def test_length_client_check_batch_empty(mock_httpx_client: list) -> None:
    """Test checking empty batch."""
    client = LengthClient(base_url="http://test:8080")
    results = client.check_batch([])

    assert len(results) == 0


def test_length_client_context_manager() -> None:
    """Test using client as context manager."""
    with LengthClient(base_url="http://test:8080") as client:
        assert client is not None
    # Should close without error


def test_length_client_uses_config_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that client uses URL from config by default."""
    monkeypatch.setenv("LENGTH_SERVICE_URL", "http://config-url:9090")

    # Import after setting env var
    from app.clients.length_client import LengthClient

    client = LengthClient()
    assert client.base_url == "http://config-url:9090"


def test_length_client_strips_trailing_slash() -> None:
    """Test that trailing slash is removed from base URL."""
    client = LengthClient(base_url="http://test:8080/")
    assert client.base_url == "http://test:8080"
