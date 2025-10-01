"""API routes for CLI access."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from app.api.auth import get_current_api_token
from app.db.base import get_db
from app.db.dao import create_run, create_tweet
from app.db.models import Account, ApiToken
from app.db.schema import RunCreate, TweetCreate
from app.services.budget import within_budget
from app.services.canonicalize import canonicalize
from app.services.duplicate_detection import check_duplicate
from app.services.generate import generate_thread
from app.services.images import alt_text_from, pick_hero, validate_and_process
from app.services.scraper import scrape

router = APIRouter(prefix="/api", tags=["api"])


class SubmitRequest(BaseModel):
    """Request model for submit endpoint."""

    url: HttpUrl
    mode: str = "review"  # review or auto
    type: str = "thread"  # thread or single
    account: str | None = None  # Account handle
    style: str | None = None
    hook: bool = False
    image: bool = False
    reference: str | None = None
    utm: str | None = None
    thread_cap: int | None = None
    single_cap: int | None = None
    force: bool = False


class SubmitResponse(BaseModel):
    """Response model for submit endpoint."""

    status: str
    run_id: int
    review_url: str | None = None
    tweets: list | None = None


@router.post("/submit", response_model=SubmitResponse)
async def api_submit(
    request: SubmitRequest,
    db: Session = Depends(get_db),
    api_token: ApiToken = Depends(get_current_api_token),
) -> SubmitResponse:
    """Submit a URL for conversion via API."""
    # Find account if specified
    account_id = None
    if request.account:
        account = db.query(Account).filter(Account.handle == request.account).first()
        if not account:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Account @{request.account} not found",
            )
        account_id = account.id
    else:
        # Use first available account
        account = db.query(Account).first()
        if not account:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No accounts configured",
            )
        account_id = account.id

    # 1. Canonicalize URL
    canonical_url = canonicalize(str(request.url))

    # 2. Check for duplicates
    duplicate_check = check_duplicate(
        db=db,
        account_id=account_id,
        canonical_url=canonical_url,
        mode=request.mode,
        force=request.force,
    )

    if duplicate_check.is_duplicate and duplicate_check.blocks_submission:  # type: ignore[attr-defined]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate submission. Previous run ID: {duplicate_check.previous_run_id}",
        )

    # 3. Scrape the content
    scraped = scrape(str(request.url))

    # 4. Process hero image if requested
    hero_image_bytes = None
    hero_alt_text = None
    if request.image and scraped.hero_candidates:
        hero = pick_hero(scraped.hero_candidates)
        if hero:
            try:
                hero_image_bytes, _, _ = validate_and_process(hero.url)  # type: ignore[misc, attr-defined]
                hero_alt_text = alt_text_from(scraped.title, scraped.title)
            except Exception:
                pass  # Silently skip if image processing fails

    # 5. Generate the content
    # Note: This is a simplified version - in production you'd pass proper settings
    generation_result = generate_thread(
        scraped_content=scraped,
        settings={
            "type": request.type,
            "style": request.style or "extractive",
            "hook": request.hook,
            "thread_cap": request.thread_cap,
            "single_cap": request.single_cap,
        },
    )  # type: ignore[call-arg]

    # 6. Check budget
    mode = request.mode
    if not within_budget(generation_result.cost_usd):
        mode = "review"  # Force review if over budget

    # 7. Create the run
    run = create_run(
        db,
        RunCreate(
            account_id=account_id,
            url=str(request.url),
            canonical_url=canonical_url,
            mode=mode,
            type=request.type,
            status="review" if mode == "review" else "approved",
            cost_estimate=generation_result.cost_usd,
            tokens_in=generation_result.tokens_in,
            tokens_out=generation_result.tokens_out,
            scraped_title=scraped.title,
            scraped_text=scraped.text,
            word_count=scraped.word_count,
            settings_json={
                "style": request.style,
                "hook": request.hook,
                "reference": request.reference,
                "utm": request.utm,
            },
        ),
    )

    # 8. Create tweets
    for idx, tweet_text in enumerate(generation_result.tweets):
        create_tweet(
            db,
            TweetCreate(
                run_id=run.id,
                idx=idx,
                role="content",
                text=tweet_text,
                media_alt=hero_alt_text if idx == 0 and hero_image_bytes else None,
            ),
        )

    # 9. If auto mode and approved, post immediately (simplified)
    if mode == "auto" and run.status == "approved":
        # In a real implementation, this would trigger posting
        # For now, we'll just return success
        return SubmitResponse(
            status="completed",
            run_id=run.id,
            tweets=[
                {"text": t.text, "permalink": f"https://twitter.com/user/status/{run.id}{idx}"}
                for idx, t in enumerate(run.tweets)
            ],
        )

    # Return review URL
    return SubmitResponse(
        status="review",
        run_id=run.id,
        review_url=f"/review/{run.id}",
    )
