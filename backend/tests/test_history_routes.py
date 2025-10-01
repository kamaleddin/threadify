"""Tests for history page routes."""

from collections.abc import Generator
from datetime import datetime, timedelta
from typing import Any

import pytest
from app.db.base import Base, engine
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Create a test database session."""
    from sqlalchemy.orm import sessionmaker

    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_account(db_session: Session) -> Any:
    """Create a test account."""
    from app.db.models import Account

    account = Account(
        handle="testuser",
        provider="x",
        scopes="tweet.read tweet.write users.read offline.access",
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    return account


@pytest.fixture
def test_runs(db_session: Session, test_account: Any) -> list[Any]:
    """Create multiple test runs with different statuses."""
    from app.db.models import Run, Tweet

    runs = []

    # Run 1: Completed thread
    run1 = Run(
        account_id=test_account.id,
        url="https://example.com/article1",
        canonical_url="https://example.com/article1",
        mode="auto",
        type="thread",
        status="completed",
        scraped_title="First Article",
        scraped_text="First content",
        word_count=100,
        tokens_in=50,
        tokens_out=30,
        cost_estimate=0.001,
        submitted_at=datetime.now() - timedelta(hours=2),
    )
    db_session.add(run1)
    db_session.commit()
    db_session.refresh(run1)

    # Add tweets for run1
    for idx in range(3):
        tweet = Tweet(
            run_id=run1.id,
            idx=idx,
            role="content",
            text=f"Tweet {idx+1}/3",
            posted_tweet_id=f"123456789{idx}",
        )
        db_session.add(tweet)

    runs.append(run1)

    # Run 2: In review
    run2 = Run(
        account_id=test_account.id,
        url="https://example.com/article2",
        canonical_url="https://example.com/article2",
        mode="review",
        type="single",
        status="review",
        scraped_title="Second Article",
        scraped_text="Second content",
        word_count=50,
        tokens_in=25,
        tokens_out=15,
        cost_estimate=0.0005,
        submitted_at=datetime.now() - timedelta(hours=1),
    )
    db_session.add(run2)
    db_session.commit()
    db_session.refresh(run2)

    # Add tweet for run2
    tweet = Tweet(
        run_id=run2.id,
        idx=0,
        role="content",
        text="Single tweet",
    )
    db_session.add(tweet)

    runs.append(run2)

    # Run 3: Failed
    run3 = Run(
        account_id=test_account.id,
        url="https://example.com/article3",
        canonical_url="https://example.com/article3",
        mode="auto",
        type="thread",
        status="failed",
        scraped_title="Third Article",
        scraped_text="Third content",
        word_count=75,
        tokens_in=40,
        tokens_out=0,
        cost_estimate=0.0,
        submitted_at=datetime.now() - timedelta(minutes=30),
    )
    db_session.add(run3)
    db_session.commit()
    db_session.refresh(run3)

    runs.append(run3)

    db_session.commit()
    return runs


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Create test client with database override."""
    from app.db.base import get_db

    def override_get_db() -> Session:
        return db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_history_page_loads(client: TestClient, test_runs: list[Any]) -> None:
    """Test that history page loads successfully."""
    response = client.get("/history")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_history_shows_all_runs(client: TestClient, test_runs: list[Any]) -> None:
    """Test that history page displays all runs."""
    response = client.get("/history")

    assert response.status_code == 200
    content = response.content.decode()
    assert "First Article" in content
    assert "Second Article" in content
    assert "Third Article" in content


def test_history_shows_status(client: TestClient, test_runs: list[Any]) -> None:
    """Test that history page shows run statuses."""
    response = client.get("/history")

    assert response.status_code == 200
    content = response.content.decode()
    assert "completed" in content.lower()
    assert "review" in content.lower()
    assert "failed" in content.lower()


def test_history_shows_costs(client: TestClient, test_runs: list[Any]) -> None:
    """Test that history page displays costs."""
    response = client.get("/history")

    assert response.status_code == 200
    content = response.content.decode()
    # Should have cost information
    assert "$" in content or "cost" in content.lower()


def test_history_has_review_links(client: TestClient, test_runs: list[Any]) -> None:
    """Test that history page has links to review pages."""
    response = client.get("/history")

    assert response.status_code == 200
    content = response.content.decode()
    # Should have links to review pages
    assert "/review/" in content


def test_history_shows_tweet_links(client: TestClient, test_runs: list[Any]) -> None:
    """Test that completed runs show tweet links."""
    response = client.get("/history")

    assert response.status_code == 200
    content = response.content.decode()
    # Should show X post IDs for completed runs
    assert "123456789" in content


def test_history_empty_state(client: TestClient) -> None:
    """Test history page with no runs."""
    response = client.get("/history")

    assert response.status_code == 200
    content = response.content.decode()
    # Should show empty state message
    assert "no" in content.lower() or "empty" in content.lower()


def test_history_sorted_by_time(client: TestClient, test_runs: list[Any]) -> None:
    """Test that history is sorted by submission time (newest first)."""
    response = client.get("/history")

    assert response.status_code == 200
    content = response.content.decode()

    # Third Article (30 min ago) should appear before First Article (2 hours ago)
    third_pos = content.find("Third Article")
    first_pos = content.find("First Article")

    assert third_pos > 0 and first_pos > 0
    assert third_pos < first_pos
