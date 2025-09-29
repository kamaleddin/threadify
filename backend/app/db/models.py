"""Database models for Threadify."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Account(Base):
    """Twitter/X account with OAuth credentials."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    handle: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), default="x", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    scopes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    runs: Mapped[list["Run"]] = relationship("Run", back_populates="account")


class Run(Base):
    """A content generation run for a URL."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("accounts.id"), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(2048), nullable=True, index=True)
    mode: Mapped[str] = mapped_column(
        String(50), default="review", nullable=False
    )  # review, auto
    type: Mapped[str] = mapped_column(
        String(50), default="thread", nullable=False
    )  # thread, single
    settings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default="submitted", nullable=False, index=True
    )  # submitted, review, approved, posting, failed, completed
    cost_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    scraped_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    scraped_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    account: Mapped["Account"] = relationship("Account", back_populates="runs")
    tweets: Mapped[list["Tweet"]] = relationship(
        "Tweet", back_populates="run", cascade="all, delete-orphan"
    )
    images: Mapped[list["Image"]] = relationship(
        "Image", back_populates="run", cascade="all, delete-orphan"
    )


class Tweet(Base):
    """Individual tweet in a thread or single post."""

    __tablename__ = "tweets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("runs.id"), nullable=False)
    idx: Mapped[int] = mapped_column(Integer, nullable=False)  # Position in thread (0-indexed)
    role: Mapped[str] = mapped_column(
        String(50), default="content", nullable=False
    )  # content, reference
    text: Mapped[str] = mapped_column(Text, nullable=False)
    media_alt: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    posted_tweet_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    permalink: Mapped[str | None] = mapped_column(String(500), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    run: Mapped["Run"] = relationship("Run", back_populates="tweets")


class Image(Base):
    """Hero image candidates and metadata."""

    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("runs.id"), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used: Mapped[bool] = mapped_column(Integer, default=0, nullable=False)  # SQLite boolean as int

    # Relationships
    run: Mapped["Run"] = relationship("Run", back_populates="images")


class Settings(Base):
    """Application-wide settings and defaults."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ApiToken(Base):
    """API tokens for CLI authentication."""

    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
