"""Tests for review page routes."""

from collections.abc import Generator
from typing import Any
from unittest.mock import patch

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
def test_run(db_session: Session, test_account: Any) -> Any:
    """Create a test run with tweets."""
    from app.db.models import Run, Tweet

    run = Run(
        account_id=test_account.id,
        url="https://example.com/article",
        canonical_url="https://example.com/article",
        mode="review",
        type="thread",
        status="review",
        scraped_title="Test Article",
        scraped_text="Test content",
        word_count=100,
        tokens_in=50,
        tokens_out=30,
        cost_estimate=0.001,
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    # Add tweets
    for idx, text in enumerate(["Tweet 1/3", "Tweet 2/3", "Tweet 3/3"]):
        tweet = Tweet(
            run_id=run.id,
            idx=idx,
            role="content",
            text=text,
        )
        db_session.add(tweet)

    db_session.commit()
    return run


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


def test_review_page_loads(client: TestClient, test_run: Any) -> None:
    """Test that review page loads successfully."""
    response = client.get(f"/review/{test_run.id}")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_review_page_shows_tweets(client: TestClient, test_run: Any) -> None:
    """Test that review page displays all tweets."""
    response = client.get(f"/review/{test_run.id}")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Tweet 1/3" in content
    assert "Tweet 2/3" in content
    assert "Tweet 3/3" in content


def test_review_page_shows_article_title(client: TestClient, test_run: Any) -> None:
    """Test that review page shows scraped article title."""
    response = client.get(f"/review/{test_run.id}")

    assert response.status_code == 200
    assert b"Test Article" in response.content


def test_review_page_has_edit_buttons(client: TestClient, test_run: Any) -> None:
    """Test that review page has edit functionality."""
    response = client.get(f"/review/{test_run.id}")

    assert response.status_code == 200
    content = response.content.decode()
    # Should have textareas for editing tweets
    assert "textarea" in content.lower()


def test_review_page_has_regenerate_button(client: TestClient, test_run: Any) -> None:
    """Test that review page has regenerate button."""
    response = client.get(f"/review/{test_run.id}")

    assert response.status_code == 200
    content = response.content.decode()
    assert "regenerate" in content.lower()


def test_review_page_has_approve_button(client: TestClient, test_run: Any) -> None:
    """Test that review page has approve/post button."""
    response = client.get(f"/review/{test_run.id}")

    assert response.status_code == 200
    content = response.content.decode()
    assert "approve" in content.lower() or "post" in content.lower()


def test_review_page_not_found(client: TestClient) -> None:
    """Test that non-existent run returns 404."""
    response = client.get("/review/99999")

    assert response.status_code == 404


def test_review_page_shows_cost(client: TestClient, test_run: Any) -> None:
    """Test that review page displays cost estimate."""
    response = client.get(f"/review/{test_run.id}")

    assert response.status_code == 200
    content = response.content.decode()
    assert "cost" in content.lower() or "$" in content


def test_update_tweet_text(client: TestClient, test_run: Any, db_session: Session) -> None:
    """Test updating tweet text via HTMX."""
    from app.db.models import Tweet

    tweet = db_session.query(Tweet).filter(Tweet.run_id == test_run.id, Tweet.idx == 0).first()
    assert tweet is not None

    response = client.post(
        f"/review/{test_run.id}/tweet/{tweet.id}",
        data={"text": "Updated tweet text 1/3"},
    )

    assert response.status_code in [200, 303]  # Success or redirect

    # Verify tweet was updated
    db_session.refresh(tweet)
    assert tweet.text == "Updated tweet text 1/3"


def test_regenerate_thread(client: TestClient, test_run: Any, db_session: Session) -> None:
    """Test regenerating entire thread."""
    from app.db.models import Tweet

    with (
        patch("app.web.routes.scrape") as mock_scrape,
        patch("app.web.routes.generate_thread") as mock_gen,
    ):

        from app.services.generate import GeneratedThread
        from app.services.scraper import ScrapedContent

        mock_scrape.return_value = ScrapedContent(
            title="Test Article",
            text="Test content",
            site_name="example.com",
            word_count=100,
            too_short=False,
            hero_candidates=[],
            metadata={},
        )

        mock_gen.return_value = GeneratedThread(
            tweets=["New tweet 1/3", "New tweet 2/3", "New tweet 3/3"],
            style_used="punchy",
            hook_used=True,
            tokens_in=100,
            tokens_out=50,
            cost_usd=0.002,
            model_used="gpt-4o-mini",
        )

        response = client.post(f"/review/{test_run.id}/regenerate")

        assert response.status_code in [200, 303]  # Success or redirect

        # Verify tweets were updated
        tweets = (
            db_session.query(Tweet).filter(Tweet.run_id == test_run.id).order_by(Tweet.idx).all()
        )
        assert tweets[0].text == "New tweet 1/3"
        assert tweets[1].text == "New tweet 2/3"
        assert tweets[2].text == "New tweet 3/3"
