"""Tests for X/Twitter posting service."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest
from app.services.post_x import (
    PostError,
    RateLimitError,
    post_single,
    post_thread,
)


@dataclass
class MockResponse:
    """Mock HTTP response."""

    status_code: int
    json_data: dict[str, Any]
    headers: dict[str, str]

    def json(self) -> dict[str, Any]:
        """Return JSON data."""
        return self.json_data

    def raise_for_status(self) -> None:
        """Raise for HTTP errors."""
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


def mock_http_post_success(tweet_id: str = "1234567890") -> Any:
    """Create mock HTTP POST that returns success."""

    def _post(url: str, **kwargs: Any) -> MockResponse:
        # Extract text from json payload
        json_data = kwargs.get("json", {})
        text = json_data.get("text", "")

        return MockResponse(
            status_code=201,
            json_data={"data": {"id": tweet_id, "text": text}},
            headers={},
        )

    return _post


def mock_http_post_failure(status_code: int = 500) -> Any:
    """Create mock HTTP POST that returns failure."""

    def _post(url: str, **kwargs: Any) -> MockResponse:
        return MockResponse(
            status_code=status_code,
            json_data={"errors": [{"message": "Internal server error"}]},
            headers={},
        )

    return _post


def mock_http_post_rate_limit() -> Any:
    """Create mock HTTP POST that returns rate limit error."""

    def _post(url: str, **kwargs: Any) -> MockResponse:
        return MockResponse(
            status_code=429,
            json_data={"errors": [{"message": "Too Many Requests"}]},
            headers={"x-rate-limit-reset": str(int(datetime.now().timestamp()) + 60)},
        )

    return _post


def mock_sleeper_no_op() -> Any:
    """Create mock sleeper that doesn't actually sleep."""

    async def _sleep(seconds: float) -> None:
        pass

    return _sleep


def test_post_single_with_valid_text() -> None:
    """Test that post_single posts a single tweet successfully."""
    # Arrange
    account_token = "test_token_123"
    text = "This is a test tweet"
    http_post = mock_http_post_success("9876543210")

    # Act
    result = post_single(account_token, text, http_post=http_post)

    # Assert
    assert result.success is True
    assert result.tweet_id == "9876543210"
    assert result.text == text
    assert result.error is None


def test_post_single_with_media() -> None:
    """Test that post_single handles media attachment."""
    # Arrange
    account_token = "test_token_123"
    text = "Tweet with image"
    media_bytes = b"fake_image_data"
    media_alt = "Alt text for image"
    http_post = mock_http_post_success("1111111111")

    # Act
    result = post_single(
        account_token, text, media=media_bytes, media_alt=media_alt, http_post=http_post
    )

    # Assert
    assert result.success is True
    assert result.tweet_id == "1111111111"


def test_post_single_handles_api_failure() -> None:
    """Test that post_single raises PostError on API failure."""
    # Arrange
    account_token = "test_token_123"
    text = "This will fail"
    http_post = mock_http_post_failure(500)

    # Act & Assert
    with pytest.raises(PostError, match="Failed to post tweet"):
        post_single(account_token, text, http_post=http_post)


def test_post_single_handles_rate_limit() -> None:
    """Test that post_single raises RateLimitError on 429."""
    # Arrange
    account_token = "test_token_123"
    text = "Rate limited tweet"
    http_post = mock_http_post_rate_limit()

    # Act & Assert
    with pytest.raises(RateLimitError, match="Rate limit exceeded"):
        post_single(account_token, text, http_post=http_post)


def test_post_single_retries_on_transient_failure() -> None:
    """Test that post_single retries on transient failures."""
    # Arrange
    account_token = "test_token_123"
    text = "Retry test"

    call_count = 0

    def http_post_fail_then_succeed(url: str, **kwargs: Any) -> MockResponse:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            return MockResponse(
                status_code=500,
                json_data={"errors": [{"message": "Transient error"}]},
                headers={},
            )
        return MockResponse(
            status_code=201,
            json_data={"data": {"id": "success_after_retry", "text": text}},
            headers={},
        )

    # Act
    result = post_single(account_token, text, http_post=http_post_fail_then_succeed, max_retries=3)

    # Assert
    assert result.success is True
    assert result.tweet_id == "success_after_retry"
    assert call_count == 2  # Failed once, succeeded on retry


@pytest.mark.asyncio
async def test_post_thread_with_multiple_tweets() -> None:
    """Test that post_thread posts all tweets in order."""
    # Arrange
    account_token = "test_token_123"
    texts = ["Tweet 1/3", "Tweet 2/3", "Tweet 3/3"]

    tweet_ids = ["111", "222", "333"]
    call_index = 0

    def http_post_sequential(url: str, **kwargs: Any) -> MockResponse:
        nonlocal call_index
        tweet_id = tweet_ids[call_index]
        call_index += 1
        return MockResponse(
            status_code=201,
            json_data={"data": {"id": tweet_id, "text": kwargs["json"]["text"]}},
            headers={},
        )

    sleeper = mock_sleeper_no_op()

    # Act
    result = await post_thread(
        account_token, texts, http_post=http_post_sequential, sleeper=sleeper
    )

    # Assert
    assert result.success is True
    assert len(result.tweet_ids) == 3
    assert result.tweet_ids == ["111", "222", "333"]
    assert result.failed_at is None
    assert result.error is None


@pytest.mark.asyncio
async def test_post_thread_with_pacing_delay() -> None:
    """Test that post_thread applies delay between tweets."""
    # Arrange
    account_token = "test_token_123"
    texts = ["Tweet 1", "Tweet 2"]
    http_post = mock_http_post_success()

    sleep_calls: list[float] = []

    async def sleeper_track(seconds: float) -> None:
        sleep_calls.append(seconds)

    # Act
    await post_thread(account_token, texts, http_post=http_post, sleeper=sleeper_track)

    # Assert
    # Should have 1 sleep call between 2 tweets
    assert len(sleep_calls) == 1
    # Sleep should be ~3s with jitter (2.5 to 3.5)
    assert 2.5 <= sleep_calls[0] <= 3.5


@pytest.mark.asyncio
async def test_post_thread_with_first_tweet_media() -> None:
    """Test that post_thread attaches media to first tweet only."""
    # Arrange
    account_token = "test_token_123"
    texts = ["First tweet with image", "Second tweet"]
    media_bytes = b"image_data"
    media_alt = "Image description"

    http_post = mock_http_post_success()
    sleeper = mock_sleeper_no_op()

    # Act
    result = await post_thread(
        account_token,
        texts,
        media_first=media_bytes,
        media_alt=media_alt,
        http_post=http_post,
        sleeper=sleeper,
    )

    # Assert
    assert result.success is True
    assert len(result.tweet_ids) == 2


@pytest.mark.asyncio
async def test_post_thread_handles_mid_thread_failure() -> None:
    """Test that post_thread stops and reports failure mid-thread."""
    # Arrange
    account_token = "test_token_123"
    texts = ["Tweet 1", "Tweet 2", "Tweet 3"]

    call_count = 0

    def http_post_fail_at_second(url: str, **kwargs: Any) -> MockResponse:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            # Fail at second tweet
            return MockResponse(
                status_code=500,
                json_data={"errors": [{"message": "Failed"}]},
                headers={},
            )
        return MockResponse(
            status_code=201,
            json_data={"data": {"id": f"tweet_{call_count}", "text": kwargs["json"]["text"]}},
            headers={},
        )

    sleeper = mock_sleeper_no_op()

    # Act
    result = await post_thread(
        account_token, texts, http_post=http_post_fail_at_second, sleeper=sleeper, max_retries=1
    )

    # Assert
    assert result.success is False
    assert len(result.tweet_ids) == 1  # Only first tweet succeeded
    assert result.tweet_ids[0] == "tweet_1"
    assert result.failed_at == 1  # Failed at index 1 (second tweet)
    assert result.error is not None


@pytest.mark.asyncio
async def test_post_thread_resumes_from_last_success() -> None:
    """Test that post_thread can resume from a specific index."""
    # Arrange
    account_token = "test_token_123"
    texts = ["Tweet 1", "Tweet 2", "Tweet 3"]
    previous_tweet_ids = ["existing_1", "existing_2"]

    call_count = 0

    def http_post_from_third(url: str, **kwargs: Any) -> MockResponse:
        nonlocal call_count
        call_count += 1
        return MockResponse(
            status_code=201,
            json_data={"data": {"id": "tweet_3", "text": kwargs["json"]["text"]}},
            headers={},
        )

    sleeper = mock_sleeper_no_op()

    # Act
    result = await post_thread(
        account_token,
        texts,
        http_post=http_post_from_third,
        sleeper=sleeper,
        resume_from=2,
        previous_tweet_ids=previous_tweet_ids,
    )

    # Assert
    assert result.success is True
    assert len(result.tweet_ids) == 3
    assert result.tweet_ids == ["existing_1", "existing_2", "tweet_3"]
    assert call_count == 1  # Only posted the third tweet


@pytest.mark.asyncio
async def test_post_thread_with_reply_chain() -> None:
    """Test that post_thread creates proper reply chain."""
    # Arrange
    account_token = "test_token_123"
    texts = ["First", "Second", "Third"]

    posted_ids = []
    reply_to_ids = []

    def http_post_track_replies(url: str, **kwargs: Any) -> MockResponse:
        json_data = kwargs.get("json", {})
        reply_to = json_data.get("reply", {}).get("in_reply_to_tweet_id")
        reply_to_ids.append(reply_to)

        tweet_id = f"id_{len(posted_ids) + 1}"
        posted_ids.append(tweet_id)

        return MockResponse(
            status_code=201,
            json_data={"data": {"id": tweet_id, "text": json_data.get("text")}},
            headers={},
        )

    sleeper = mock_sleeper_no_op()

    # Act
    result = await post_thread(
        account_token, texts, http_post=http_post_track_replies, sleeper=sleeper
    )

    # Assert
    assert result.success is True
    assert reply_to_ids[0] is None  # First tweet has no reply
    assert reply_to_ids[1] == "id_1"  # Second replies to first
    assert reply_to_ids[2] == "id_2"  # Third replies to second


@pytest.mark.asyncio
async def test_post_thread_rate_limit_retry() -> None:
    """Test that post_thread retries after rate limit with backoff."""
    # Arrange
    account_token = "test_token_123"
    texts = ["Tweet 1"]

    call_count = 0

    def http_post_rate_limit_then_success(url: str, **kwargs: Any) -> MockResponse:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MockResponse(
                status_code=429,
                json_data={"errors": [{"message": "Rate limited"}]},
                headers={"x-rate-limit-reset": str(int(datetime.now().timestamp()) + 1)},
            )
        return MockResponse(
            status_code=201,
            json_data={"data": {"id": "success_id", "text": kwargs["json"]["text"]}},
            headers={},
        )

    sleeper = mock_sleeper_no_op()

    # Act
    result = await post_thread(
        account_token,
        texts,
        http_post=http_post_rate_limit_then_success,
        sleeper=sleeper,
        max_retries=3,
    )

    # Assert
    assert result.success is True
    assert call_count == 2  # Rate limited once, then succeeded
