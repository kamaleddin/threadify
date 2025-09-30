"""AI-powered thread generation using OpenAI GPT models."""

import json
from dataclasses import dataclass

from openai import OpenAI
from pydantic import BaseModel, Field

from app.config import get_settings


class GenerationError(Exception):
    """Raised when generation fails."""

    pass


# JSON Schema Models for OpenAI Responses


class TweetSchema(BaseModel):
    """Schema for a single tweet in a thread."""

    text: str = Field(..., description="Tweet text content")


class GeneratedThreadSchema(BaseModel):
    """Schema for generated thread output."""

    tweets: list[TweetSchema] = Field(..., description="List of tweets in the thread")
    style_used: str | None = Field(None, description="Style applied (if any)")
    hook_used: bool = Field(False, description="Whether a hook was used")


class GeneratedSingleSchema(BaseModel):
    """Schema for generated single tweet output."""

    text: str = Field(..., description="Single tweet text")
    style_used: str | None = Field(None, description="Style applied (if any)")


class GeneratedReferenceSchema(BaseModel):
    """Schema for generated reference tweet output."""

    text: str = Field(..., description="Reference tweet text")


# Output dataclasses for service functions


@dataclass
class GeneratedThread:
    """Result of thread generation."""

    tweets: list[str]
    style_used: str | None
    hook_used: bool
    tokens_in: int
    tokens_out: int
    cost_usd: float
    model_used: str


@dataclass
class GeneratedSingle:
    """Result of single tweet generation."""

    text: str
    style_used: str | None
    tokens_in: int
    tokens_out: int
    cost_usd: float
    model_used: str


@dataclass
class GeneratedReference:
    """Result of reference tweet generation."""

    text: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    model_used: str


@dataclass
class ScrapeResult:
    """Input data from scraper (minimal interface for generator)."""

    title: str
    text: str
    word_count: int
    site_name: str | None = None
    author: str | None = None


@dataclass
class GenerationSettings:
    """Settings for content generation."""

    mode: str = "thread"  # thread, single
    style: str | None = None  # conversational, analytical, casual, enthusiastic
    hook: bool = True  # Use hook for threads
    extractive: bool = True  # Use extractive mode (default)


# Token cost estimation (approximate rates for GPT-4o-mini and GPT-4o)
COSTS = {
    "gpt-4o-mini": {"input": 0.150 / 1_000_000, "output": 0.600 / 1_000_000},  # per token
    "gpt-4o": {"input": 2.50 / 1_000_000, "output": 10.00 / 1_000_000},
}


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for text (rough approximation: 1 token ≈ 4 chars).

    Args:
        text: Input text

    Returns:
        Estimated token count
    """
    return len(text) // 4


def estimate_cost(
    prompt_text: str, expected_output_tokens: int, model: str = "gpt-4o-mini"
) -> float:
    """
    Estimate cost in USD for a generation request.

    Args:
        prompt_text: The full prompt text
        expected_output_tokens: Expected number of output tokens
        model: Model name (gpt-4o-mini or gpt-4o)

    Returns:
        Estimated cost in USD
    """
    if model not in COSTS:
        model = "gpt-4o-mini"

    input_tokens = estimate_tokens(prompt_text)
    cost_in = input_tokens * COSTS[model]["input"]
    cost_out = expected_output_tokens * COSTS[model]["output"]

    return cost_in + cost_out


def choose_model(word_count: int) -> str:
    """
    Choose the appropriate model based on content length.

    Args:
        word_count: Number of words in the content

    Returns:
        Model name (gpt-4o-mini or gpt-4o)
    """
    if word_count > 2500:
        return "gpt-4o"
    return "gpt-4o-mini"


def build_thread_prompt(scrape: ScrapeResult, settings: GenerationSettings) -> str:
    """
    Build the prompt for thread generation.

    Args:
        scrape: Scraped content
        settings: Generation settings

    Returns:
        Formatted prompt string
    """
    # Base extractive instructions
    if settings.extractive:
        mode_instruction = (
            "Use ONLY the author's own words from the article. "
            "Do not paraphrase, summarize, or add commentary. "
            "Extract key sentences and insights verbatim."
        )
    else:
        mode_instruction = (
            "Summarize and distill the key insights from the article in your own words."
        )

    # Style instruction
    style_instruction = ""
    if settings.style == "conversational":
        style_instruction = "Write in a conversational, friendly tone."
    elif settings.style == "analytical":
        style_instruction = "Write in an analytical, data-driven tone."
    elif settings.style == "casual":
        style_instruction = "Write in a casual, relaxed tone."
    elif settings.style == "enthusiastic":
        style_instruction = "Write in an enthusiastic, energetic tone."

    # Hook instruction
    hook_instruction = ""
    if settings.hook:
        hook_instruction = (
            "Start with a compelling hook tweet that grabs attention and "
            "makes people want to read the thread."
        )

    prompt = f"""You are creating a Twitter/X thread from the following article.

{mode_instruction}
{style_instruction}
{hook_instruction}

Create a thread of 3-8 tweets. Each tweet must be under 280 characters (following Twitter's rules).

Article Title: {scrape.title}
{f"Site: {scrape.site_name}" if scrape.site_name else ""}
{f"Author: {scrape.author}" if scrape.author else ""}

Article Content:
{scrape.text}

Return your response as a JSON object with this structure:
{{
  "tweets": [{{"text": "First tweet..."}}, {{"text": "Second tweet..."}}, ...],
  "style_used": "{settings.style or "none"}",
  "hook_used": {str(settings.hook).lower()}
}}
"""
    return prompt


def build_single_prompt(scrape: ScrapeResult, settings: GenerationSettings) -> str:
    """
    Build the prompt for single tweet generation.

    Args:
        scrape: Scraped content
        settings: Generation settings

    Returns:
        Formatted prompt string
    """
    # Style instruction
    style_instruction = ""
    if settings.style == "conversational":
        style_instruction = "Write in a conversational, friendly tone."
    elif settings.style == "analytical":
        style_instruction = "Write in an analytical, data-driven tone."
    elif settings.style == "casual":
        style_instruction = "Write in a casual, relaxed tone."
    elif settings.style == "enthusiastic":
        style_instruction = "Write in an enthusiastic, energetic tone."

    prompt = f"""You are creating a single Twitter/X post from the following article.

Distill the key insight or most compelling point from the article into one tweet.
The tweet must be under 280 characters (following Twitter's rules).
{style_instruction}

Article Title: {scrape.title}
{f"Site: {scrape.site_name}" if scrape.site_name else ""}
{f"Author: {scrape.author}" if scrape.author else ""}

Article Content:
{scrape.text}

Return your response as a JSON object with this structure:
{{
  "text": "Your single tweet here...",
  "style_used": "{settings.style or "none"}"
}}
"""
    return prompt


def build_reference_prompt(scrape: ScrapeResult) -> str:
    """
    Build the prompt for reference tweet generation.

    Args:
        scrape: Scraped content

    Returns:
        Formatted prompt string
    """
    prompt = f"""You are creating a reference tweet to accompany a Twitter/X thread.

Create a simple reference tweet that credits the original article.
Format: "Original: [Title] by [Author/Site]"
Keep it under 280 characters.

Article Title: {scrape.title}
{f"Site: {scrape.site_name}" if scrape.site_name else ""}
{f"Author: {scrape.author}" if scrape.author else ""}

Return your response as a JSON object with this structure:
{{
  "text": "Your reference tweet here..."
}}
"""
    return prompt


def _default_openai_client() -> OpenAI:
    """Create default OpenAI client."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise GenerationError("OPENAI_API_KEY not configured")
    return OpenAI(api_key=settings.openai_api_key)


def _call_openai(
    prompt: str,
    model: str,
    response_format: type[BaseModel],
    openai_client: OpenAI | None = None,
    max_retries: int = 2,
) -> tuple[BaseModel, int, int]:
    """
    Call OpenAI API with structured output and retry logic.

    Args:
        prompt: The prompt text
        model: Model name
        response_format: Pydantic model for structured output
        openai_client: Optional OpenAI client (for testing)
        max_retries: Maximum number of retries for invalid JSON

    Returns:
        Tuple of (parsed_response, tokens_in, tokens_out)

    Raises:
        GenerationError: If all retries fail or API error occurs
    """
    if openai_client is None:
        openai_client = _default_openai_client()

    for attempt in range(max_retries + 1):
        try:
            # Use beta.chat.completions.parse for structured outputs
            completion = openai_client.beta.chat.completions.parse(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format=response_format,
            )

            # Extract usage
            tokens_in = completion.usage.prompt_tokens if completion.usage else 0
            tokens_out = completion.usage.completion_tokens if completion.usage else 0

            # Parse response
            if completion.choices and completion.choices[0].message.parsed:
                return (completion.choices[0].message.parsed, tokens_in, tokens_out)
            else:
                # Fall back to manual JSON parsing if structured output failed
                content = completion.choices[0].message.content
                if content:
                    parsed = response_format.model_validate_json(content)
                    return (parsed, tokens_in, tokens_out)
                else:
                    raise GenerationError("Empty response from OpenAI")

        except json.JSONDecodeError as e:
            if attempt < max_retries:
                continue  # Retry
            raise GenerationError(f"Invalid JSON after {max_retries} retries: {e}") from e
        except Exception as e:
            raise GenerationError(f"OpenAI API error: {e}") from e

    raise GenerationError(f"Failed after {max_retries} retries")


def generate_thread(
    scrape: ScrapeResult,
    settings: GenerationSettings,
    openai_client: OpenAI | None = None,
) -> GeneratedThread:
    """
    Generate a Twitter thread from scraped content.

    Args:
        scrape: Scraped content
        settings: Generation settings
        openai_client: Optional OpenAI client (for testing)

    Returns:
        Generated thread with metadata

    Raises:
        GenerationError: If generation fails
    """
    # Choose model
    model = choose_model(scrape.word_count)

    # Build prompt
    prompt = build_thread_prompt(scrape, settings)

    # Call OpenAI
    parsed_base, tokens_in, tokens_out = _call_openai(
        prompt, model, GeneratedThreadSchema, openai_client
    )

    # Cast to the correct type
    parsed = GeneratedThreadSchema.model_validate(parsed_base)

    # Calculate cost
    cost_usd = (tokens_in * COSTS[model]["input"]) + (tokens_out * COSTS[model]["output"])

    # Convert to output format
    return GeneratedThread(
        tweets=[tweet.text for tweet in parsed.tweets],
        style_used=parsed.style_used,
        hook_used=parsed.hook_used,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        model_used=model,
    )


def generate_single(
    scrape: ScrapeResult,
    settings: GenerationSettings,
    openai_client: OpenAI | None = None,
) -> GeneratedSingle:
    """
    Generate a single tweet from scraped content.

    Args:
        scrape: Scraped content
        settings: Generation settings
        openai_client: Optional OpenAI client (for testing)

    Returns:
        Generated single tweet with metadata

    Raises:
        GenerationError: If generation fails
    """
    # Choose model
    model = choose_model(scrape.word_count)

    # Build prompt
    prompt = build_single_prompt(scrape, settings)

    # Call OpenAI
    parsed_base, tokens_in, tokens_out = _call_openai(
        prompt, model, GeneratedSingleSchema, openai_client
    )

    # Cast to the correct type
    parsed = GeneratedSingleSchema.model_validate(parsed_base)

    # Calculate cost
    cost_usd = (tokens_in * COSTS[model]["input"]) + (tokens_out * COSTS[model]["output"])

    # Convert to output format
    return GeneratedSingle(
        text=parsed.text,
        style_used=parsed.style_used,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        model_used=model,
    )


def generate_reference(
    scrape: ScrapeResult, openai_client: OpenAI | None = None
) -> GeneratedReference:
    """
    Generate a reference tweet for the original article.

    Args:
        scrape: Scraped content
        openai_client: Optional OpenAI client (for testing)

    Returns:
        Generated reference tweet with metadata

    Raises:
        GenerationError: If generation fails
    """
    # Always use gpt-4o-mini for simple reference tweets
    model = "gpt-4o-mini"

    # Build prompt
    prompt = build_reference_prompt(scrape)

    # Call OpenAI
    parsed_base, tokens_in, tokens_out = _call_openai(
        prompt, model, GeneratedReferenceSchema, openai_client
    )

    # Cast to the correct type
    parsed = GeneratedReferenceSchema.model_validate(parsed_base)

    # Calculate cost
    cost_usd = (tokens_in * COSTS[model]["input"]) + (tokens_out * COSTS[model]["output"])

    # Convert to output format
    return GeneratedReference(
        text=parsed.text,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        model_used=model,
    )
