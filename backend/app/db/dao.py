"""Data Access Objects (DAO) for database operations."""

from sqlalchemy.orm import Session

from app.db.models import Account, Run, Tweet
from app.db.schema import AccountCreate, RunCreate, TweetCreate


# Account DAO
def create_account(db: Session, account: AccountCreate) -> Account:
    """
    Create a new account.

    Args:
        db: Database session
        account: Account data

    Returns:
        Created account instance
    """
    db_account = Account(
        handle=account.handle,
        provider=account.provider,
        scopes=account.scopes,
    )
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account


def get_account(db: Session, account_id: int) -> Account | None:
    """
    Get account by ID.

    Args:
        db: Database session
        account_id: Account ID

    Returns:
        Account instance or None
    """
    return db.query(Account).filter(Account.id == account_id).first()


def get_account_by_handle(db: Session, handle: str) -> Account | None:
    """
    Get account by handle.

    Args:
        db: Database session
        handle: Account handle

    Returns:
        Account instance or None
    """
    return db.query(Account).filter(Account.handle == handle).first()


# Run DAO
def create_run(db: Session, run: RunCreate) -> Run:
    """
    Create a new run.

    Args:
        db: Database session
        run: Run data

    Returns:
        Created run instance
    """
    db_run = Run(
        account_id=run.account_id,
        url=run.url,
        mode=run.mode,
        type=run.type,
        settings_json=run.settings_json,
    )
    db.add(db_run)
    db.commit()
    db.refresh(db_run)
    return db_run


def get_run(db: Session, run_id: int) -> Run | None:
    """
    Get run by ID.

    Args:
        db: Database session
        run_id: Run ID

    Returns:
        Run instance or None
    """
    return db.query(Run).filter(Run.id == run_id).first()


def get_runs_by_account(db: Session, account_id: int, limit: int = 100) -> list[Run]:
    """
    Get runs for an account.

    Args:
        db: Database session
        account_id: Account ID
        limit: Maximum number of runs to return

    Returns:
        List of run instances
    """
    return (
        db.query(Run)
        .filter(Run.account_id == account_id)
        .order_by(Run.submitted_at.desc())
        .limit(limit)
        .all()
    )


# Tweet DAO
def create_tweet(db: Session, tweet: TweetCreate) -> Tweet:
    """
    Create a new tweet.

    Args:
        db: Database session
        tweet: Tweet data

    Returns:
        Created tweet instance
    """
    db_tweet = Tweet(
        run_id=tweet.run_id,
        idx=tweet.idx,
        role=tweet.role,
        text=tweet.text,
        media_alt=tweet.media_alt,
    )
    db.add(db_tweet)
    db.commit()
    db.refresh(db_tweet)
    return db_tweet


def get_tweet(db: Session, tweet_id: int) -> Tweet | None:
    """
    Get tweet by ID.

    Args:
        db: Database session
        tweet_id: Tweet ID

    Returns:
        Tweet instance or None
    """
    return db.query(Tweet).filter(Tweet.id == tweet_id).first()


def get_tweets_by_run(db: Session, run_id: int) -> list[Tweet]:
    """
    Get all tweets for a run, ordered by index.

    Args:
        db: Database session
        run_id: Run ID

    Returns:
        List of tweet instances ordered by idx
    """
    return db.query(Tweet).filter(Tweet.run_id == run_id).order_by(Tweet.idx).all()


def find_duplicate_run(db: Session, account_id: int, canonical_url: str) -> Run | None:
    """
    Find a completed or approved run for the same account and canonical URL.

    Args:
        db: Database session
        account_id: Account ID
        canonical_url: Canonical URL to check

    Returns:
        Most recent matching run or None
    """
    return (
        db.query(Run)
        .filter(
            Run.account_id == account_id,
            Run.canonical_url == canonical_url,
            Run.status.in_(["completed", "approved"]),
        )
        .order_by(Run.submitted_at.desc())
        .first()
    )
