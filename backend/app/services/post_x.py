"""X/Twitter posting service."""

import asyncio
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx


class PostError(Exception):
    """Raised when posting to X fails."""

    pass


class RateLimitError(PostError):
    """Raised when rate limit is exceeded."""

    pass


@dataclass
class PostResult:
    """Result of posting a single tweet."""

    success: bool
    tweet_id: str | None = None
    text: str | None = None
    error: str | None = None


@dataclass
class ThreadPostResult:
    """Result of posting a thread."""

    success: bool
    tweet_ids: list[str]
    failed_at: int | None = None  # Index where posting failed
    error: str | None = None


def post_single(
    account_token: str,
    text: str,
    media: bytes | None = None,
    media_alt: str | None = None,
    reply_to_tweet_id: str | None = None,
    http_post: Callable[..., Any] | None = None,
    max_retries: int = 3,
) -> PostResult:
    """
    Post a single tweet to X/Twitter.

    Args:
        account_token: OAuth access token for the account
        text: Tweet text content
        media: Optional media bytes to attach
        media_alt: Optional alt text for media
        reply_to_tweet_id: Optional tweet ID to reply to
        http_post: Optional HTTP POST function (for testing/injection)
        max_retries: Maximum number of retry attempts

    Returns:
        PostResult with success status and tweet ID

    Raises:
        PostError: If posting fails after retries
        RateLimitError: If rate limit is exceeded
    """
    if http_post is None:
        http_post = _default_http_post

    # Prepare request payload
    payload: dict[str, Any] = {"text": text}

    # Add reply if specified
    if reply_to_tweet_id:
        payload["reply"] = {"in_reply_to_tweet_id": reply_to_tweet_id}

    # Handle media upload if provided
    media_id = None
    if media:
        media_id = _upload_media(account_token, media, media_alt, http_post)
        payload["media"] = {"media_ids": [media_id]}

    # Post tweet with retries
    for attempt in range(max_retries):
        try:
            response = http_post(
                "https://api.twitter.com/2/tweets",
                json=payload,
                headers={
                    "Authorization": f"Bearer {account_token}",
                    "Content-Type": "application/json",
                },
            )

            # Check for rate limit
            if response.status_code == 429:
                reset_time = response.headers.get("x-rate-limit-reset")
                if attempt < max_retries - 1:
                    # Retry with exponential backoff on rate limit
                    time.sleep(2**attempt)
                    continue
                raise RateLimitError(
                    f"Rate limit exceeded. Reset at: {reset_time if reset_time else 'unknown'}"
                )

            # Check for other errors
            if response.status_code >= 400:
                error_msg = response.json_data.get("errors", [{}])[0].get(
                    "message", "Unknown error"
                )
                if attempt < max_retries - 1:
                    # Retry with exponential backoff
                    time.sleep(2**attempt)
                    continue
                raise PostError(f"Failed to post tweet: {error_msg}")

            # Success
            response_data = response.json()
            tweet_data = response_data.get("data", {})
            tweet_id = tweet_data.get("id")

            return PostResult(success=True, tweet_id=tweet_id, text=text)

        except RateLimitError:
            raise
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2**attempt)
                continue
            raise PostError(f"Failed to post tweet: {e}") from e

    raise PostError("Failed to post tweet after retries")


async def post_thread(
    account_token: str,
    texts: list[str],
    media_first: bytes | None = None,
    media_alt: str | None = None,
    resume_from: int = 0,
    previous_tweet_ids: list[str] | None = None,
    http_post: Callable[..., Any] | None = None,
    sleeper: Callable[[float], Any] | None = None,
    max_retries: int = 3,
) -> ThreadPostResult:
    """
    Post a thread of tweets to X/Twitter.

    Tweets are posted sequentially with a paced delay (~3s with jitter).
    Each tweet replies to the previous one to form a thread.

    Args:
        account_token: OAuth access token for the account
        texts: List of tweet texts in order
        media_first: Optional media bytes to attach to first tweet
        media_alt: Optional alt text for media
        resume_from: Index to resume from (for retry logic)
        previous_tweet_ids: Tweet IDs from previous attempts
        http_post: Optional HTTP POST function (for testing/injection)
        sleeper: Optional async sleep function (for testing/injection)
        max_retries: Maximum number of retry attempts per tweet

    Returns:
        ThreadPostResult with success status and tweet IDs

    Note:
        Reference tweets should be posted separately as replies,
        not counted in the thread numbering.
    """
    if http_post is None:
        http_post = _default_http_post

    if sleeper is None:
        sleeper = asyncio.sleep

    tweet_ids = list(previous_tweet_ids) if previous_tweet_ids else []
    last_tweet_id: str | None = tweet_ids[-1] if tweet_ids else None

    for idx in range(resume_from, len(texts)):
        text = texts[idx]

        # Attach media only to first tweet
        media = media_first if idx == 0 and media_first else None
        alt = media_alt if idx == 0 and media_alt else None

        # Add delay between tweets (except before first tweet)
        if idx > resume_from:
            # 3s with ±0.5s jitter
            delay = 3.0 + random.uniform(-0.5, 0.5)
            await sleeper(delay)

        try:
            result = post_single(
                account_token,
                text,
                media=media,
                media_alt=alt,
                reply_to_tweet_id=last_tweet_id,
                http_post=http_post,
                max_retries=max_retries,
            )

            if not result.success or not result.tweet_id:
                return ThreadPostResult(
                    success=False,
                    tweet_ids=tweet_ids,
                    failed_at=idx,
                    error=result.error or "Unknown error",
                )

            tweet_ids.append(result.tweet_id)
            last_tweet_id = result.tweet_id

        except (PostError, RateLimitError) as e:
            return ThreadPostResult(
                success=False,
                tweet_ids=tweet_ids,
                failed_at=idx,
                error=str(e),
            )

    return ThreadPostResult(success=True, tweet_ids=tweet_ids)


def _upload_media(
    account_token: str,
    media_bytes: bytes,
    alt_text: str | None,
    http_post: Callable[..., Any],
) -> str:
    """
    Upload media to X/Twitter and return media ID.

    Args:
        account_token: OAuth access token
        media_bytes: Media file bytes
        alt_text: Optional alt text for accessibility
        http_post: HTTP POST function

    Returns:
        Media ID string

    Raises:
        PostError: If upload fails
    """
    # Upload media (simplified for MVP)
    # In production, use proper multipart upload for large files
    response = http_post(
        "https://upload.twitter.com/1.1/media/upload.json",
        data={"media": media_bytes},
        headers={"Authorization": f"Bearer {account_token}"},
    )

    if response.status_code >= 400:
        raise PostError("Failed to upload media")

    media_data = response.json()
    media_id: str = media_data.get("media_id_string", "")

    # Add alt text if provided
    if alt_text and media_id:
        http_post(
            "https://upload.twitter.com/1.1/media/metadata/create.json",
            json={"media_id": media_id, "alt_text": {"text": alt_text}},
            headers={
                "Authorization": f"Bearer {account_token}",
                "Content-Type": "application/json",
            },
        )

    return media_id


def _default_http_post(url: str, **kwargs: Any) -> Any:
    """
    Default HTTP POST function using httpx.

    Args:
        url: URL to POST to
        **kwargs: Additional arguments for httpx

    Returns:
        httpx Response object
    """
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, **kwargs)
        response.raise_for_status()
        return response
