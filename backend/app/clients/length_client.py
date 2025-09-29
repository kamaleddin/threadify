"""HTTP client for the Twitter text length validation service."""

from typing import Any

import httpx
from pydantic import BaseModel

from app.config import get_settings


class LengthValidRange(BaseModel):
    """Valid range for tweet text."""

    start: int
    end: int


class LengthCheckResult(BaseModel):
    """Result of a length check."""

    is_valid: bool
    weighted_length: int
    permillage: int
    valid_range: LengthValidRange


class LengthServiceError(Exception):
    """Raised when the length service returns an error."""

    pass


class LengthClient:
    """Client for the Twitter text length validation service."""

    def __init__(self, base_url: str | None = None, timeout: float = 5.0) -> None:
        """
        Initialize the length client.

        Args:
            base_url: Base URL of the length service (defaults to config)
            timeout: Request timeout in seconds
        """
        if base_url is None:
            settings = get_settings()
            base_url = settings.length_service_url

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> "LengthClient":
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()

    def check(self, text: str) -> LengthCheckResult:
        """
        Check if a tweet text is valid according to Twitter's rules.

        Args:
            text: Tweet text to validate

        Returns:
            LengthCheckResult with validation details

        Raises:
            LengthServiceError: If the service returns an error
            httpx.HTTPError: If the request fails
        """
        try:
            response = self._client.post(
                f"{self.base_url}/length/check", json={"text": text}
            )

            if response.status_code == 400:
                error_data = response.json()
                raise LengthServiceError(f"Invalid request: {error_data.get('error', 'Unknown error')}")

            response.raise_for_status()

            data = response.json()

            # Map snake_case to camelCase from the Node service
            return LengthCheckResult(
                is_valid=data["isValid"],
                weighted_length=data["weightedLength"],
                permillage=data["permillage"],
                valid_range=LengthValidRange(
                    start=data["validRange"]["start"], end=data["validRange"]["end"]
                ),
            )

        except httpx.HTTPError as e:
            raise LengthServiceError(f"Failed to check length: {e}") from e

    def check_batch(self, texts: list[str]) -> list[LengthCheckResult]:
        """
        Check multiple tweet texts in a single request.

        Args:
            texts: List of tweet texts to validate

        Returns:
            List of LengthCheckResult, one for each input text

        Raises:
            LengthServiceError: If the service returns an error
            httpx.HTTPError: If the request fails
        """
        try:
            response = self._client.post(
                f"{self.base_url}/length/batch", json={"texts": texts}
            )

            if response.status_code == 400:
                error_data = response.json()
                raise LengthServiceError(f"Invalid request: {error_data.get('error', 'Unknown error')}")

            response.raise_for_status()

            data = response.json()

            # Map results
            return [
                LengthCheckResult(
                    is_valid=result["isValid"],
                    weighted_length=result["weightedLength"],
                    permillage=result["permillage"],
                    valid_range=LengthValidRange(
                        start=result["validRange"]["start"],
                        end=result["validRange"]["end"],
                    ),
                )
                for result in data["results"]
            ]

        except httpx.HTTPError as e:
            raise LengthServiceError(f"Failed to check batch lengths: {e}") from e
