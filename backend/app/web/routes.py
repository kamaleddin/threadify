"""Web UI routes for Threadify."""

import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.dao import create_run, create_tweet
from app.db.models import Account, Run, Tweet
from app.db.schema import RunCreate, TweetCreate
from app.services.budget import within_budget
from app.services.canonicalize import CanonicalizationError, canonicalize
from app.services.duplicate_detection import check_duplicate
from app.services.generate import GenerationError, generate_thread
from app.services.images import alt_text_from, pick_hero, validate_and_process
from app.services.scraper import ScraperError, scrape

router = APIRouter()

# Setup Jinja2 templates
templates = Jinja2Templates(directory="backend/app/web/templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """
    Render the main submission form page.

    Args:
        request: FastAPI request object
        db: Database session

    Returns:
        HTML response with submission form
    """
    # Get list of connected accounts
    accounts = db.query(Account).all()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "accounts": accounts,
        },
    )


@router.post("/submit")
async def submit(
    url: str = Form(...),
    account_id: int = Form(...),
    mode: str = Form("review"),
    type: str = Form("thread"),
    style: str = Form("punchy"),
    summary_mode: str = Form("extractive"),
    thread_cap: int = Form(12),
    single_cap: int = Form(1400),
    include_reference: str | None = Form(None),
    utm_campaign: str = Form("threadify"),
    include_image: str | None = Form(None),
    include_hook: str | None = Form(None),
    force: str | None = Form(None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """
    Handle form submission to create a thread/post.

    This endpoint integrates all services:
    1. Canonicalize URL
    2. Check for duplicates
    3. Scrape content
    4. Select hero image
    5. Generate thread/post with AI
    6. Check budget
    7. Store Run and Tweets

    Args:
        url: Blog URL to convert
        account_id: Target X/Twitter account ID
        mode: "review" or "auto"
        type: "thread" or "single"
        style: Style profile for generation
        summary_mode: "extractive" or "commentary"
        thread_cap: Max tweets in thread
        single_cap: Max characters in single post
        include_reference: Whether to include reference reply
        utm_campaign: UTM campaign parameter
        include_image: Whether to include hero image
        include_hook: Whether to include hook (for threads)
        force: Force flag to override duplicate detection
        db: Database session

    Returns:
        Redirect to review page

    Raises:
        HTTPException: On validation or processing errors
    """
    # Convert checkbox values to booleans
    force_bool = force == "on"
    include_reference_bool = include_reference == "on"
    include_image_bool = include_image == "on"
    include_hook_bool = include_hook == "on"

    # Validate account exists
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    try:
        # Step 1: Canonicalize URL
        canonical_url = canonicalize(url)

        # Step 2: Check for duplicates
        duplicate_check = check_duplicate(
            db, account_id, canonical_url, mode=mode, force=force_bool
        )

        if duplicate_check.should_block:
            raise HTTPException(
                status_code=400,
                detail=f"This URL has already been posted from this account (Run #{duplicate_check.previous_run_id}). Use --force to override.",
            )

        # Step 3: Scrape content
        scraped = scrape(url)

        # Step 4: Select and process hero image (if enabled)
        hero_image_bytes = None
        hero_alt_text = None

        if include_image_bool and scraped.hero_candidates:
            hero_url = pick_hero(scraped.hero_candidates)
            if hero_url:
                try:
                    hero_image_bytes = validate_and_process(hero_url)
                    # Generate alt text from title + lede
                    hero_alt_text = alt_text_from(scraped.title, scraped.title)
                except Exception:
                    # If image processing fails, continue without image
                    pass

        # Step 5: Generate thread/post with AI
        if type == "thread":
            generation_result = generate_thread(  # type: ignore[call-arg]
                title=scraped.title,
                content=scraped.text,
                word_count=scraped.word_count,
                style=style,
                summary_mode=summary_mode,
                max_tweets=thread_cap,
                include_hook=include_hook_bool,
            )
        else:
            # Single post generation would go here
            # For now, simplified version
            generation_result = generate_thread(  # type: ignore[call-arg]
                title=scraped.title,
                content=scraped.text,
                word_count=scraped.word_count,
                style=style,
                summary_mode=summary_mode,
                max_tweets=1,
                include_hook=False,
            )

        # Step 6: Check budget
        if not within_budget(generation_result.cost_usd):
            # Over budget - force to review mode
            mode = "review"

        # Step 7: Store Run in database
        settings = {
            "style": style,
            "summary_mode": summary_mode,
            "thread_cap": thread_cap,
            "single_cap": single_cap,
            "include_reference": include_reference_bool,
            "utm_campaign": utm_campaign,
            "include_image": include_image_bool,
            "include_hook": include_hook_bool,
        }

        run = create_run(
            db,
            RunCreate(
                account_id=account_id,
                url=url,
                mode=mode,
                type=type,
                settings_json=json.dumps(settings),
            ),
        )

        # Update run with scraped data and costs
        run.canonical_url = canonical_url
        run.scraped_title = scraped.title
        run.scraped_text = scraped.text
        run.word_count = scraped.word_count
        run.tokens_in = generation_result.tokens_in
        run.tokens_out = generation_result.tokens_out
        run.cost_estimate = generation_result.cost_usd
        run.status = "review"  # Always go to review in MVP
        db.commit()
        db.refresh(run)

        # Step 8: Store Tweets
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

        # Redirect to review page
        return RedirectResponse(
            url=f"/review/{run.id}",
            status_code=303,  # See Other (POST -> GET redirect)
        )

    except CanonicalizationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid URL: {e}") from e
    except ScraperError as e:
        raise HTTPException(status_code=400, detail=f"Failed to scrape content: {e}") from e
    except GenerationError as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate content: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}") from e


@router.get("/review/{run_id}", response_class=HTMLResponse)
async def review(run_id: int, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """
    Display review page for a run with editable tweets.

    Args:
        run_id: Run ID to review
        request: FastAPI request
        db: Database session

    Returns:
        HTML review page

    Raises:
        HTTPException: If run not found
    """
    # Get run with tweets
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Get associated account
    account = db.query(Account).filter(Account.id == run.account_id).first()

    # Get tweets ordered by index
    from app.db.dao import get_tweets_by_run

    tweets = get_tweets_by_run(db, run_id)

    return templates.TemplateResponse(
        request=request,
        name="review.html",
        context={
            "run": run,
            "account": account,
            "tweets": tweets,
        },
    )


@router.post("/review/{run_id}/tweet/{tweet_id}")
async def update_tweet(
    run_id: int,
    tweet_id: int,
    text: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """
    Update tweet text (HTMX endpoint).

    Args:
        run_id: Run ID
        tweet_id: Tweet ID to update
        text: New tweet text
        db: Database session

    Returns:
        Redirect to review page
    """
    tweet = db.query(Tweet).filter(Tweet.id == tweet_id, Tweet.run_id == run_id).first()
    if not tweet:
        raise HTTPException(status_code=404, detail="Tweet not found")

    tweet.text = text
    db.commit()

    return RedirectResponse(url=f"/review/{run_id}", status_code=303)


@router.post("/review/{run_id}/tweet/{tweet_id}/alt")
async def update_alt_text(
    run_id: int,
    tweet_id: int,
    media_alt: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """
    Update tweet media alt text.

    Args:
        run_id: Run ID
        tweet_id: Tweet ID to update
        media_alt: New alt text
        db: Database session

    Returns:
        Redirect to review page
    """
    tweet = db.query(Tweet).filter(Tweet.id == tweet_id, Tweet.run_id == run_id).first()
    if not tweet:
        raise HTTPException(status_code=404, detail="Tweet not found")

    tweet.media_alt = media_alt
    db.commit()

    return RedirectResponse(url=f"/review/{run_id}", status_code=303)


@router.post("/review/{run_id}/regenerate")
async def regenerate_thread(
    run_id: int,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """
    Regenerate entire thread with same settings.

    Args:
        run_id: Run ID to regenerate
        db: Database session

    Returns:
        Redirect to review page with new content
    """
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    try:
        # Re-scrape content
        scraped = scrape(run.url)

        # Parse settings from JSON
        settings = {}
        if run.settings_json:
            settings = json.loads(run.settings_json)

        # Regenerate with same settings
        generation_result = generate_thread(  # type: ignore[call-arg]
            title=scraped.title,
            content=scraped.text,
            word_count=scraped.word_count,
            style=settings.get("style", "punchy"),
            summary_mode=settings.get("summary_mode", "extractive"),
            max_tweets=settings.get("thread_cap", 12),
            include_hook=settings.get("include_hook", True),
        )

        # Delete old tweets
        db.query(Tweet).filter(Tweet.run_id == run_id).delete()

        # Create new tweets
        for idx, tweet_text in enumerate(generation_result.tweets):
            create_tweet(
                db,
                TweetCreate(
                    run_id=run_id,
                    idx=idx,
                    role="content",
                    text=tweet_text,
                ),
            )

        # Update run with new costs
        run.tokens_in = generation_result.tokens_in
        run.tokens_out = generation_result.tokens_out
        run.cost_estimate = generation_result.cost_usd
        db.commit()

        return RedirectResponse(url=f"/review/{run_id}", status_code=303)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Regeneration failed: {e}") from e


@router.post("/review/{run_id}/approve")
async def approve_and_post(
    run_id: int,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """
    Approve thread and post to X/Twitter.

    Args:
        run_id: Run ID to approve
        db: Database session

    Returns:
        Redirect to history page
    """
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Update status to approved
    run.status = "approved"
    db.commit()

    # TODO: Implement actual posting logic
    # This will be part of Prompt 11 integration
    # For now, just mark as approved

    return RedirectResponse(url="/history", status_code=303)
