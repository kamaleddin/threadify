"""Pydantic schemas for API requests/responses."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# Account schemas
class AccountBase(BaseModel):
    """Base account schema."""

    handle: str = Field(..., max_length=255)
    provider: str = "x"
    scopes: str | None = None


class AccountCreate(AccountBase):
    """Schema for creating an account."""

    pass


class AccountRead(AccountBase):
    """Schema for reading an account (no secrets)."""

    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Run schemas
class RunBase(BaseModel):
    """Base run schema."""

    url: str = Field(..., max_length=2048)
    mode: str = "review"
    type: str = "thread"
    settings_json: str | None = None


class RunCreate(RunBase):
    """Schema for creating a run."""

    account_id: int


class RunRead(RunBase):
    """Schema for reading a run."""

    id: int
    submitted_at: datetime
    account_id: int
    canonical_url: str | None = None
    status: str
    cost_estimate: float | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    error_message: str | None = None
    scraped_title: str | None = None
    word_count: int | None = None

    model_config = ConfigDict(from_attributes=True)


# Tweet schemas
class TweetBase(BaseModel):
    """Base tweet schema."""

    idx: int
    role: str = "content"
    text: str
    media_alt: str | None = None


class TweetCreate(TweetBase):
    """Schema for creating a tweet."""

    run_id: int


class TweetRead(TweetBase):
    """Schema for reading a tweet."""

    id: int
    run_id: int
    posted_tweet_id: str | None = None
    permalink: str | None = None
    posted_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# Image schemas
class ImageBase(BaseModel):
    """Base image schema."""

    source_url: str = Field(..., max_length=2048)
    width: int | None = None
    height: int | None = None
    used: bool = False


class ImageCreate(ImageBase):
    """Schema for creating an image."""

    run_id: int


class ImageRead(ImageBase):
    """Schema for reading an image."""

    id: int
    run_id: int

    model_config = ConfigDict(from_attributes=True)


# Settings schemas
class SettingsBase(BaseModel):
    """Base settings schema."""

    key: str = Field(..., max_length=255)
    value_json: str | None = None


class SettingsCreate(SettingsBase):
    """Schema for creating settings."""

    pass


class SettingsRead(SettingsBase):
    """Schema for reading settings."""

    id: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ApiToken schemas
class ApiTokenBase(BaseModel):
    """Base API token schema."""

    label: str = Field(..., max_length=255)


class ApiTokenCreate(ApiTokenBase):
    """Schema for creating an API token."""

    pass


class ApiTokenRead(ApiTokenBase):
    """Schema for reading an API token (no hash)."""

    id: int
    created_at: datetime
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
