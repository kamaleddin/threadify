"""Tests for web UI routes."""

import pytest
from app.db.base import Base, engine
from app.db.models import Account
from app.main import app
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
def client(db_session: Session) -> TestClient:
    """Create test client with overridden database dependency."""
    from app.db.base import get_db

    def override_get_db() -> Session:
        return db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_index_page_loads(client: TestClient) -> None:
    """Test that index page loads successfully."""
    # Act
    response = client.get("/")

    # Assert
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_index_page_has_form(client: TestClient) -> None:
    """Test that index page contains submission form."""
    # Act
    response = client.get("/")

    # Assert
    assert response.status_code == 200
    assert b"<form" in response.content
    assert b'name="url"' in response.content
    assert b'name="account_id"' in response.content


def test_index_page_has_mode_options(client: TestClient) -> None:
    """Test that index page has review/auto mode options."""
    # Act
    response = client.get("/")

    # Assert
    assert response.status_code == 200
    content = response.content.decode()
    assert "review" in content.lower()
    assert "auto" in content.lower()


def test_index_page_has_type_options(client: TestClient) -> None:
    """Test that index page has thread/single type options."""
    # Act
    response = client.get("/")

    # Assert
    assert response.status_code == 200
    content = response.content.decode()
    assert "thread" in content.lower()
    assert "single" in content.lower()


def test_index_page_has_style_options(client: TestClient) -> None:
    """Test that index page has style profile options."""
    # Act
    response = client.get("/")

    # Assert
    assert response.status_code == 200
    content = response.content.decode()
    # Check for some style options from spec
    assert "punchy" in content.lower() or "explainer" in content.lower()


def test_index_page_has_advanced_options(client: TestClient) -> None:
    """Test that index page has advanced options section."""
    # Act
    response = client.get("/")

    # Assert
    assert response.status_code == 200
    content = response.content.decode()
    # Check for some advanced options
    assert "thread_cap" in content or "thread-cap" in content.lower()
    assert "reference" in content.lower()
    assert "hook" in content.lower()


def test_index_page_includes_htmx(client: TestClient) -> None:
    """Test that index page includes HTMX library."""
    # Act
    response = client.get("/")

    # Assert
    assert response.status_code == 200
    content = response.content.decode()
    assert "htmx" in content.lower()


def test_index_page_has_submit_button(client: TestClient) -> None:
    """Test that index page has submit button."""
    # Act
    response = client.get("/")

    # Assert
    assert response.status_code == 200
    assert b'type="submit"' in response.content or b"Submit" in response.content
