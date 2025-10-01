"""Tests for POST /submit endpoint."""

from unittest.mock import patch

import pytest
from app.db.base import Base, engine
from app.db.models import Account, Run
from app.main import app
from app.services.generate import GeneratedThread
from app.services.scraper import ScrapedContent
from fastapi.testclient import TestClient
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


@pytest.fixture
def mock_services():
    """Mock all external services for testing."""
    mock_scraped = ScrapedContent(
        title="Test Article Title",
        text="This is test article content that is long enough to be valid.",
        site_name="example.com",
        word_count=100,
        too_short=False,
        hero_candidates=["https://example.com/image.jpg"],
        metadata={},
    )

    mock_generation = GeneratedThread(
        tweets=["Tweet 1/3", "Tweet 2/3", "Tweet 3/3"],
        style_used="punchy",
        hook_used=True,
        tokens_in=100,
        tokens_out=50,
        cost_usd=0.001,
        model_used="gpt-4o-mini",
    )

    with (
        patch("app.web.routes.canonicalize") as mock_canon,
        patch("app.web.routes.scrape") as mock_scrape,
        patch("app.web.routes.generate_thread") as mock_gen,
        patch("app.web.routes.pick_hero") as mock_hero,
        patch("app.web.routes.validate_and_process") as mock_img,
    ):

        mock_canon.side_effect = (
            lambda url: url.lower().replace("http://", "https://").split("?")[0]
        )
        mock_scrape.return_value = mock_scraped
        mock_gen.return_value = mock_generation
        mock_hero.return_value = "https://example.com/image.jpg"
        mock_img.return_value = b"fake_image_bytes"

        yield {
            "canonicalize": mock_canon,
            "scrape": mock_scrape,
            "generate_thread": mock_gen,
            "pick_hero": mock_hero,
            "validate_and_process": mock_img,
        }


@pytest.fixture
def client(db_session: Session, mock_services) -> TestClient:
    """Create test client with overridden database dependency."""
    from app.db.base import get_db

    def override_get_db() -> Session:
        return db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_submit_requires_url(client: TestClient, test_account: Account) -> None:
    """Test that submit endpoint requires URL field."""
    # Arrange
    form_data = {
        "account_id": str(test_account.id),
        "mode": "review",
        "type": "thread",
    }

    # Act
    response = client.post("/submit", data=form_data)

    # Assert
    assert response.status_code == 422  # Validation error


def test_submit_requires_account_id(client: TestClient) -> None:
    """Test that submit endpoint requires account_id field."""
    # Arrange
    form_data = {
        "url": "https://example.com/blog-post",
        "mode": "review",
        "type": "thread",
    }

    # Act
    response = client.post("/submit", data=form_data)

    # Assert
    assert response.status_code == 422  # Validation error


def test_submit_creates_run_in_database(
    client: TestClient, test_account: Account, db_session: Session
) -> None:
    """Test that successful submit creates a Run in database."""
    # Arrange
    form_data = {
        "url": "https://example.com/article",
        "account_id": str(test_account.id),
        "mode": "review",
        "type": "thread",
        "style": "punchy",
        "summary_mode": "extractive",
    }

    # Act
    response = client.post("/submit", data=form_data, follow_redirects=False)

    # Assert
    assert response.status_code in [302, 303]  # Redirect to review page

    # Check that Run was created
    run = db_session.query(Run).first()
    assert run is not None
    assert run.account_id == test_account.id
    assert run.url == "https://example.com/article"
    assert run.mode == "review"
    assert run.type == "thread"


def test_submit_redirects_to_review_page(client: TestClient, test_account: Account) -> None:
    """Test that submit redirects to review page with run_id."""
    # Arrange
    form_data = {
        "url": "https://example.com/article",
        "account_id": str(test_account.id),
        "mode": "review",
        "type": "thread",
    }

    # Act
    response = client.post("/submit", data=form_data, follow_redirects=False)

    # Assert
    assert response.status_code in [302, 303]
    assert "/review/" in response.headers["location"]


def test_submit_canonicalizes_url(
    client: TestClient, test_account: Account, db_session: Session
) -> None:
    """Test that submit canonicalizes the URL before storing."""
    # Arrange
    form_data = {
        "url": "https://Example.COM/Article?utm_source=twitter",
        "account_id": str(test_account.id),
        "mode": "review",
        "type": "thread",
    }

    # Act
    response = client.post("/submit", data=form_data, follow_redirects=False)

    # Assert
    assert response.status_code in [302, 303]

    # Check canonical URL was normalized
    run = db_session.query(Run).first()
    assert run is not None
    assert run.canonical_url is not None
    assert run.canonical_url.startswith("https://example.com")
    assert "utm_source" not in run.canonical_url


def test_submit_blocks_duplicate_in_auto_mode(
    client: TestClient, test_account: Account, db_session: Session
) -> None:
    """Test that duplicate URLs are blocked in auto mode."""
    # Arrange - create existing completed run
    existing_run = Run(
        account_id=test_account.id,
        url="https://example.com/article",
        canonical_url="https://example.com/article",
        mode="auto",
        type="thread",
        status="completed",
    )
    db_session.add(existing_run)
    db_session.commit()

    form_data = {
        "url": "https://example.com/article",
        "account_id": str(test_account.id),
        "mode": "auto",
        "type": "thread",
    }

    # Act
    response = client.post("/submit", data=form_data)

    # Assert
    assert response.status_code in [400, 500]  # Duplicate or error
    assert b"duplicate" in response.content.lower() or b"already" in response.content.lower()


def test_submit_allows_duplicate_with_force_flag(
    client: TestClient, test_account: Account, db_session: Session
) -> None:
    """Test that force flag allows duplicate URLs in auto mode."""
    # Arrange - create existing completed run
    existing_run = Run(
        account_id=test_account.id,
        url="https://example.com/article",
        canonical_url="https://example.com/article",
        mode="auto",
        type="thread",
        status="completed",
    )
    db_session.add(existing_run)
    db_session.commit()

    form_data = {
        "url": "https://example.com/article",
        "account_id": str(test_account.id),
        "mode": "auto",
        "type": "thread",
        "force": "on",  # Force checkbox
    }

    # Act
    response = client.post("/submit", data=form_data, follow_redirects=False)

    # Assert
    assert response.status_code in [302, 303]  # Success despite duplicate


def test_submit_allows_duplicate_in_review_mode(
    client: TestClient, test_account: Account, db_session: Session
) -> None:
    """Test that review mode allows duplicates with warning."""
    # Arrange - create existing completed run
    existing_run = Run(
        account_id=test_account.id,
        url="https://example.com/article",
        canonical_url="https://example.com/article",
        mode="review",
        type="thread",
        status="completed",
    )
    db_session.add(existing_run)
    db_session.commit()

    form_data = {
        "url": "https://example.com/article",
        "account_id": str(test_account.id),
        "mode": "review",
        "type": "thread",
    }

    # Act
    response = client.post("/submit", data=form_data, follow_redirects=False)

    # Assert
    assert response.status_code in [302, 303]  # Allowed in review mode


def test_submit_stores_settings_json(
    client: TestClient, test_account: Account, db_session: Session
) -> None:
    """Test that submit stores all settings in settings_json field."""
    # Arrange
    form_data = {
        "url": "https://example.com/article",
        "account_id": str(test_account.id),
        "mode": "review",
        "type": "thread",
        "style": "expert",
        "summary_mode": "commentary",
        "thread_cap": "15",
        "include_hook": "on",
        "include_reference": "on",
        "utm_campaign": "custom-campaign",
    }

    # Act
    response = client.post("/submit", data=form_data, follow_redirects=False)

    # Assert
    assert response.status_code in [302, 303]

    # Check settings were stored
    run = db_session.query(Run).first()
    assert run is not None
    assert run.settings_json is not None
    import json

    settings = json.loads(run.settings_json)
    assert settings["style"] == "expert"
    assert settings["summary_mode"] == "commentary"
    assert settings["thread_cap"] == 15


def test_submit_with_invalid_account_id(client: TestClient) -> None:
    """Test that submit with non-existent account returns error."""
    # Arrange
    form_data = {
        "url": "https://example.com/article",
        "account_id": "999999",  # Non-existent
        "mode": "review",
        "type": "thread",
    }

    # Act
    response = client.post("/submit", data=form_data)

    # Assert
    assert response.status_code in [400, 404]  # Bad request or not found
