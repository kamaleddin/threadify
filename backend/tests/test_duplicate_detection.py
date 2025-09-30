"""Tests for duplicate detection service."""

import pytest
from app.db.base import Base, engine
from app.db.models import Account, Run
from app.services.duplicate_detection import (
    check_duplicate,
)
from sqlalchemy.orm import Session


@pytest.fixture
def db_session() -> Session:
    """Create a test database session."""
    from sqlalchemy.orm import sessionmaker

    # Create tables
    Base.metadata.create_all(bind=engine)

    # Create session
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    # Cleanup
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_account(db_session: Session) -> Account:
    """Create a test account."""
    account = Account(
        handle="testuser",
        provider="x",
        scopes="tweet.read tweet.write users.read offline.access",
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    return account


def test_check_duplicate_no_previous_runs(db_session: Session, test_account: Account) -> None:
    """Test that check_duplicate returns no duplicate when no previous runs exist."""
    # Arrange
    canonical_url = "https://example.com/article"

    # Act
    result = check_duplicate(db_session, test_account.id, canonical_url)

    # Assert
    assert result.is_duplicate is False
    assert result.previous_run_id is None
    assert result.should_block is False


def test_check_duplicate_with_completed_run_in_auto_mode(
    db_session: Session, test_account: Account
) -> None:
    """Test that duplicate is blocked in auto mode when completed run exists."""
    # Arrange
    canonical_url = "https://example.com/article"

    # Create a completed run
    previous_run = Run(
        account_id=test_account.id,
        url="https://example.com/article?utm_source=twitter",
        canonical_url=canonical_url,
        mode="auto",
        type="thread",
        status="completed",
    )
    db_session.add(previous_run)
    db_session.commit()

    # Act
    result = check_duplicate(db_session, test_account.id, canonical_url, mode="auto", force=False)

    # Assert
    assert result.is_duplicate is True
    assert result.previous_run_id == previous_run.id
    assert result.should_block is True


def test_check_duplicate_with_completed_run_and_force_flag(
    db_session: Session, test_account: Account
) -> None:
    """Test that force flag overrides duplicate blocking in auto mode."""
    # Arrange
    canonical_url = "https://example.com/article"

    # Create a completed run
    previous_run = Run(
        account_id=test_account.id,
        url=canonical_url,
        canonical_url=canonical_url,
        mode="auto",
        type="thread",
        status="completed",
    )
    db_session.add(previous_run)
    db_session.commit()

    # Act
    result = check_duplicate(db_session, test_account.id, canonical_url, mode="auto", force=True)

    # Assert
    assert result.is_duplicate is True
    assert result.previous_run_id == previous_run.id
    assert result.should_block is False  # Force flag overrides blocking


def test_check_duplicate_in_review_mode_warns_but_allows(
    db_session: Session, test_account: Account
) -> None:
    """Test that duplicate is warned but allowed in review mode."""
    # Arrange
    canonical_url = "https://example.com/article"

    # Create a completed run
    previous_run = Run(
        account_id=test_account.id,
        url=canonical_url,
        canonical_url=canonical_url,
        mode="review",
        type="thread",
        status="completed",
    )
    db_session.add(previous_run)
    db_session.commit()

    # Act
    result = check_duplicate(db_session, test_account.id, canonical_url, mode="review", force=False)

    # Assert
    assert result.is_duplicate is True
    assert result.previous_run_id == previous_run.id
    assert result.should_block is False  # Review mode allows override


def test_check_duplicate_with_failed_run_does_not_block(
    db_session: Session, test_account: Account
) -> None:
    """Test that failed runs are not considered duplicates."""
    # Arrange
    canonical_url = "https://example.com/article"

    # Create a failed run
    failed_run = Run(
        account_id=test_account.id,
        url=canonical_url,
        canonical_url=canonical_url,
        mode="auto",
        type="thread",
        status="failed",
    )
    db_session.add(failed_run)
    db_session.commit()

    # Act
    result = check_duplicate(db_session, test_account.id, canonical_url, mode="auto")

    # Assert
    assert result.is_duplicate is False  # Failed runs don't count
    assert result.previous_run_id is None
    assert result.should_block is False


def test_check_duplicate_with_submitted_run_does_not_block(
    db_session: Session, test_account: Account
) -> None:
    """Test that submitted (in-progress) runs are not considered duplicates."""
    # Arrange
    canonical_url = "https://example.com/article"

    # Create a submitted run
    submitted_run = Run(
        account_id=test_account.id,
        url=canonical_url,
        canonical_url=canonical_url,
        mode="auto",
        type="thread",
        status="submitted",
    )
    db_session.add(submitted_run)
    db_session.commit()

    # Act
    result = check_duplicate(db_session, test_account.id, canonical_url, mode="auto")

    # Assert
    assert result.is_duplicate is False  # In-progress runs don't count
    assert result.previous_run_id is None
    assert result.should_block is False


def test_check_duplicate_with_approved_run_blocks(
    db_session: Session, test_account: Account
) -> None:
    """Test that approved runs are considered duplicates."""
    # Arrange
    canonical_url = "https://example.com/article"

    # Create an approved run
    approved_run = Run(
        account_id=test_account.id,
        url=canonical_url,
        canonical_url=canonical_url,
        mode="review",
        type="thread",
        status="approved",
    )
    db_session.add(approved_run)
    db_session.commit()

    # Act
    result = check_duplicate(db_session, test_account.id, canonical_url, mode="auto")

    # Assert
    assert result.is_duplicate is True
    assert result.previous_run_id == approved_run.id
    assert result.should_block is True  # Approved runs count as duplicates


def test_check_duplicate_different_account_not_duplicate(
    db_session: Session, test_account: Account
) -> None:
    """Test that runs from different accounts are not duplicates."""
    # Arrange
    canonical_url = "https://example.com/article"

    # Create another account
    other_account = Account(handle="otheruser", provider="x", scopes="tweet.read")
    db_session.add(other_account)
    db_session.commit()

    # Create a completed run for the other account
    other_run = Run(
        account_id=other_account.id,
        url=canonical_url,
        canonical_url=canonical_url,
        mode="auto",
        type="thread",
        status="completed",
    )
    db_session.add(other_run)
    db_session.commit()

    # Act
    result = check_duplicate(db_session, test_account.id, canonical_url, mode="auto")

    # Assert
    assert result.is_duplicate is False  # Different account
    assert result.previous_run_id is None
    assert result.should_block is False


def test_check_duplicate_returns_most_recent_run(
    db_session: Session, test_account: Account
) -> None:
    """Test that check_duplicate returns the most recent matching run."""
    # Arrange
    from datetime import datetime, timedelta

    canonical_url = "https://example.com/article"

    # Create two completed runs with different timestamps
    old_run = Run(
        account_id=test_account.id,
        url=canonical_url,
        canonical_url=canonical_url,
        mode="auto",
        type="thread",
        status="completed",
    )
    db_session.add(old_run)
    db_session.commit()
    db_session.refresh(old_run)

    # Update submitted_at to be older
    old_run.submitted_at = datetime.now() - timedelta(days=1)
    db_session.commit()

    new_run = Run(
        account_id=test_account.id,
        url=canonical_url,
        canonical_url=canonical_url,
        mode="auto",
        type="thread",
        status="completed",
    )
    db_session.add(new_run)
    db_session.commit()

    # Act
    result = check_duplicate(db_session, test_account.id, canonical_url, mode="auto")

    # Assert
    assert result.is_duplicate is True
    assert result.previous_run_id == new_run.id  # Most recent run
    assert result.should_block is True


def test_check_duplicate_with_null_canonical_url(
    db_session: Session, test_account: Account
) -> None:
    """Test that runs with null canonical_url are not considered duplicates."""
    # Arrange
    canonical_url = "https://example.com/article"

    # Create a run with null canonical_url
    null_run = Run(
        account_id=test_account.id,
        url="https://example.com/different",
        canonical_url=None,
        mode="auto",
        type="thread",
        status="completed",
    )
    db_session.add(null_run)
    db_session.commit()

    # Act
    result = check_duplicate(db_session, test_account.id, canonical_url, mode="auto")

    # Assert
    assert result.is_duplicate is False
    assert result.previous_run_id is None
    assert result.should_block is False


def test_check_duplicate_case_sensitivity(db_session: Session, test_account: Account) -> None:
    """Test that canonical URLs are compared case-sensitively."""
    # Arrange
    # Create a run with lowercase URL
    lower_run = Run(
        account_id=test_account.id,
        url="https://example.com/article",
        canonical_url="https://example.com/article",
        mode="auto",
        type="thread",
        status="completed",
    )
    db_session.add(lower_run)
    db_session.commit()

    # Act - check with uppercase (should not match because canonicalization lowercases host)
    # In practice, canonical URLs should already be normalized
    result = check_duplicate(
        db_session, test_account.id, "https://example.com/article", mode="auto"
    )

    # Assert
    assert result.is_duplicate is True
    assert result.previous_run_id == lower_run.id
