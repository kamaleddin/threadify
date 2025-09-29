"""Tests for Alembic migrations."""

import os
import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent


@pytest.fixture
def temp_db() -> str:
    """Create a temporary database file."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield f"sqlite:///{path}"
    # Cleanup
    if os.path.exists(path):
        os.unlink(path)


def test_migrations_upgrade_head(temp_db: str) -> None:
    """Test that alembic upgrade head works on a fresh database."""
    # Create Alembic config with absolute path
    alembic_ini_path = PROJECT_ROOT / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", temp_db)

    # Run upgrade to head
    command.upgrade(alembic_cfg, "head")

    # Verify tables were created
    engine = create_engine(temp_db)
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    expected_tables = {
        "accounts",
        "runs",
        "tweets",
        "images",
        "settings",
        "api_tokens",
        "alembic_version",
    }

    assert expected_tables.issubset(set(tables)), f"Missing tables. Found: {tables}"

    # Verify accounts table has expected columns
    accounts_columns = {col["name"] for col in inspector.get_columns("accounts")}
    expected_accounts_cols = {
        "id",
        "handle",
        "provider",
        "created_at",
        "updated_at",
        "token_encrypted",
        "refresh_encrypted",
        "scopes",
    }
    assert expected_accounts_cols.issubset(accounts_columns)

    # Verify runs table has expected columns
    runs_columns = {col["name"] for col in inspector.get_columns("runs")}
    expected_runs_cols = {
        "id",
        "submitted_at",
        "account_id",
        "url",
        "canonical_url",
        "mode",
        "type",
        "settings_json",
        "status",
        "cost_estimate",
        "tokens_in",
        "tokens_out",
    }
    assert expected_runs_cols.issubset(runs_columns)

    # Verify tweets table has expected columns
    tweets_columns = {col["name"] for col in inspector.get_columns("tweets")}
    expected_tweets_cols = {
        "id",
        "run_id",
        "idx",
        "role",
        "text",
        "media_alt",
        "posted_tweet_id",
        "permalink",
        "posted_at",
    }
    assert expected_tweets_cols.issubset(tweets_columns)

    engine.dispose()


def test_migrations_downgrade_upgrade(temp_db: str) -> None:
    """Test that migrations can be downgraded and re-upgraded."""
    alembic_ini_path = PROJECT_ROOT / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", temp_db)

    # Upgrade to head
    command.upgrade(alembic_cfg, "head")

    # Verify tables exist
    engine = create_engine(temp_db)
    inspector = inspect(engine)
    tables_after_upgrade = inspector.get_table_names()
    assert "accounts" in tables_after_upgrade

    # Downgrade to base
    command.downgrade(alembic_cfg, "base")

    # Verify tables are gone (except alembic_version)
    inspector = inspect(engine)
    tables_after_downgrade = inspector.get_table_names()
    assert "accounts" not in tables_after_downgrade
    assert "runs" not in tables_after_downgrade
    assert "tweets" not in tables_after_downgrade

    # Upgrade again
    command.upgrade(alembic_cfg, "head")

    # Verify tables are back
    inspector = inspect(engine)
    tables_after_reupgrade = inspector.get_table_names()
    assert "accounts" in tables_after_reupgrade
    assert "runs" in tables_after_reupgrade
    assert "tweets" in tables_after_reupgrade

    engine.dispose()
