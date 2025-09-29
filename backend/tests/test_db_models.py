"""Tests for database models and DAO operations."""

import pytest
from app.db.base import Base
from app.db.dao import (
    create_account,
    create_run,
    create_tweet,
    get_account,
    get_account_by_handle,
    get_run,
    get_runs_by_account,
    get_tweet,
    get_tweets_by_run,
)
from app.db.schema import AccountCreate, RunCreate, TweetCreate
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture
def db_session() -> Session:
    """Create a temporary in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_create_and_get_account(db_session: Session) -> None:
    """Test creating and retrieving an account."""
    account_data = AccountCreate(handle="@testuser", provider="x", scopes="tweet.read tweet.write")

    # Create account
    account = create_account(db_session, account_data)
    assert account.id is not None
    assert account.handle == "@testuser"
    assert account.provider == "x"
    assert account.scopes == "tweet.read tweet.write"
    assert account.created_at is not None
    assert account.updated_at is not None

    # Get by ID
    retrieved = get_account(db_session, account.id)
    assert retrieved is not None
    assert retrieved.id == account.id
    assert retrieved.handle == "@testuser"

    # Get by handle
    by_handle = get_account_by_handle(db_session, "@testuser")
    assert by_handle is not None
    assert by_handle.id == account.id


def test_create_and_get_run(db_session: Session) -> None:
    """Test creating and retrieving a run."""
    # First create an account
    account = create_account(
        db_session, AccountCreate(handle="@runner", provider="x")
    )

    # Create run
    run_data = RunCreate(
        account_id=account.id,
        url="https://example.com/article",
        mode="review",
        type="thread",
        settings_json='{"style": "punchy"}',
    )
    run = create_run(db_session, run_data)

    assert run.id is not None
    assert run.account_id == account.id
    assert run.url == "https://example.com/article"
    assert run.mode == "review"
    assert run.type == "thread"
    assert run.status == "submitted"  # default
    assert run.submitted_at is not None

    # Get by ID
    retrieved = get_run(db_session, run.id)
    assert retrieved is not None
    assert retrieved.id == run.id
    assert retrieved.url == "https://example.com/article"

    # Get by account
    runs = get_runs_by_account(db_session, account.id)
    assert len(runs) == 1
    assert runs[0].id == run.id


def test_create_and_get_tweet(db_session: Session) -> None:
    """Test creating and retrieving tweets."""
    # Create account and run first
    account = create_account(
        db_session, AccountCreate(handle="@tweeter", provider="x")
    )
    run = create_run(
        db_session,
        RunCreate(account_id=account.id, url="https://example.com/test", mode="auto", type="thread"),
    )

    # Create tweets
    tweet1_data = TweetCreate(
        run_id=run.id, idx=0, role="content", text="First tweet in thread"
    )
    tweet1 = create_tweet(db_session, tweet1_data)

    tweet2_data = TweetCreate(
        run_id=run.id, idx=1, role="content", text="Second tweet in thread"
    )
    create_tweet(db_session, tweet2_data)

    assert tweet1.id is not None
    assert tweet1.run_id == run.id
    assert tweet1.idx == 0
    assert tweet1.text == "First tweet in thread"
    assert tweet1.role == "content"

    # Get by ID
    retrieved = get_tweet(db_session, tweet1.id)
    assert retrieved is not None
    assert retrieved.id == tweet1.id
    assert retrieved.text == "First tweet in thread"

    # Get all tweets for run
    tweets = get_tweets_by_run(db_session, run.id)
    assert len(tweets) == 2
    assert tweets[0].idx == 0
    assert tweets[1].idx == 1
    assert tweets[0].text == "First tweet in thread"
    assert tweets[1].text == "Second tweet in thread"


def test_account_runs_relationship(db_session: Session) -> None:
    """Test the relationship between accounts and runs."""
    account = create_account(
        db_session, AccountCreate(handle="@reltest", provider="x")
    )

    # Create multiple runs
    run1 = create_run(
        db_session,
        RunCreate(account_id=account.id, url="https://example.com/1", mode="review", type="thread"),
    )
    run2 = create_run(
        db_session,
        RunCreate(account_id=account.id, url="https://example.com/2", mode="auto", type="single"),
    )

    # Access runs through relationship
    db_session.refresh(account)
    assert len(account.runs) == 2
    assert run1 in account.runs
    assert run2 in account.runs


def test_run_tweets_relationship(db_session: Session) -> None:
    """Test the relationship between runs and tweets."""
    account = create_account(
        db_session, AccountCreate(handle="@tweetrel", provider="x")
    )
    run = create_run(
        db_session,
        RunCreate(account_id=account.id, url="https://example.com/test", mode="review", type="thread"),
    )

    # Create tweets
    tweet1 = create_tweet(
        db_session, TweetCreate(run_id=run.id, idx=0, role="content", text="Tweet 1")
    )
    tweet2 = create_tweet(
        db_session, TweetCreate(run_id=run.id, idx=1, role="content", text="Tweet 2")
    )

    # Access tweets through relationship
    db_session.refresh(run)
    assert len(run.tweets) == 2
    assert tweet1 in run.tweets
    assert tweet2 in run.tweets
