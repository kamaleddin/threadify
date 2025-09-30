"""Duplicate detection service for URL submissions."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import Run


@dataclass
class DuplicateDetectionResult:
    """Result of duplicate detection check."""

    is_duplicate: bool
    previous_run_id: int | None = None
    should_block: bool = False


def check_duplicate(
    db: Session,
    account_id: int,
    canonical_url: str,
    mode: str = "review",
    force: bool = False,
) -> DuplicateDetectionResult:
    """
    Check if a URL has already been posted by this account.

    Duplicate detection rules:
    - A URL is considered a duplicate if a completed or approved Run exists
      for the same account + canonical URL combination
    - In auto mode: block unless force=True
    - In review mode: warn but allow (never block)
    - Failed/submitted runs are not considered duplicates

    Args:
        db: Database session
        account_id: Account ID to check
        canonical_url: Canonicalized URL to check
        mode: Submission mode ("auto" or "review")
        force: Force flag to override duplicate blocking

    Returns:
        DuplicateDetectionResult with duplicate status and blocking decision
    """
    # Query for existing runs with same account + canonical URL
    # Only consider completed or approved runs as duplicates
    existing_run = (
        db.query(Run)
        .filter(
            Run.account_id == account_id,
            Run.canonical_url == canonical_url,
            Run.status.in_(["completed", "approved"]),
        )
        .order_by(Run.submitted_at.desc())
        .first()
    )

    # No duplicate found
    if not existing_run:
        return DuplicateDetectionResult(is_duplicate=False)

    # Duplicate found - determine if should block
    should_block = False

    if mode == "auto" and not force:
        # Auto mode blocks duplicates unless force flag is set
        should_block = True
    elif mode == "review":
        # Review mode warns but never blocks
        should_block = False

    return DuplicateDetectionResult(
        is_duplicate=True, previous_run_id=existing_run.id, should_block=should_block
    )
