"""Tests for budget guardrails."""

from app.services.budget import (
    compress_prompt,
    within_budget,
)


def test_within_budget_under_cap() -> None:
    """Test that estimates under the cap return True."""
    assert within_budget(0.01, cap_usd=0.02) is True
    assert within_budget(0.015, cap_usd=0.02) is True
    assert within_budget(0.0001, cap_usd=0.02) is True


def test_within_budget_at_cap() -> None:
    """Test that estimates at exactly the cap return True."""
    assert within_budget(0.02, cap_usd=0.02) is True


def test_within_budget_over_cap() -> None:
    """Test that estimates over the cap return False."""
    assert within_budget(0.021, cap_usd=0.02) is False
    assert within_budget(0.03, cap_usd=0.02) is False
    assert within_budget(0.1, cap_usd=0.02) is False


def test_within_budget_default_cap() -> None:
    """Test that the default cap is 0.02 USD."""
    assert within_budget(0.01) is True  # Under default
    assert within_budget(0.02) is True  # At default
    assert within_budget(0.03) is False  # Over default


def test_within_budget_custom_cap() -> None:
    """Test with custom budget caps."""
    assert within_budget(0.05, cap_usd=0.1) is True
    assert within_budget(0.15, cap_usd=0.1) is False


def test_within_budget_zero_estimate() -> None:
    """Test that zero estimate is within budget."""
    assert within_budget(0.0, cap_usd=0.02) is True


def test_within_budget_negative_estimate() -> None:
    """Test that negative estimates are treated as zero (edge case)."""
    # In practice, estimates should never be negative, but handle gracefully
    assert within_budget(-0.01, cap_usd=0.02) is True


def test_compress_prompt_basic() -> None:
    """Test that compress_prompt reduces prompt size."""
    long_prompt = """You are creating a Twitter/X thread from the following article.

Use ONLY the author's own words from the article. Do not paraphrase, summarize, or add commentary. Extract key sentences and insights verbatim.

Create a thread of 3-8 tweets. Each tweet must be under 280 characters (following Twitter's rules).

Article Title: The Future of AI
Site: TechBlog
Author: Jane Doe

Article Content:
This is a very long article about artificial intelligence and its implications for the future of humanity. """ + (
        "More content here. " * 100
    )

    compressed = compress_prompt(long_prompt)

    # Compressed should be shorter
    assert len(compressed) < len(long_prompt)

    # Should still contain key instructions
    assert "twitter" in compressed.lower() or "thread" in compressed.lower()


def test_compress_prompt_preserves_structure() -> None:
    """Test that compression preserves essential prompt structure."""
    prompt = """You are creating a Twitter/X thread.

Extract key insights from the article.

Article Title: Test Article
Article Content:
Some content here. Some more content. Additional information. More details. Extra data. Further information."""

    compressed = compress_prompt(prompt)

    # Should preserve title and basic structure
    assert "Test Article" in compressed
    assert "Twitter" in compressed or "thread" in compressed.lower()


def test_compress_prompt_short_prompt() -> None:
    """Test that short prompts are minimally compressed."""
    short_prompt = "Create a tweet from: Test article."
    compressed = compress_prompt(short_prompt)

    # Short prompts should not change much
    assert len(compressed) <= len(short_prompt) + 10  # Allow minor formatting


def test_compress_prompt_removes_verbosity() -> None:
    """Test that compression removes verbose instructions."""
    verbose_prompt = """You are creating a Twitter/X thread from the following article.

Use ONLY the author's own words from the article. Do not paraphrase, summarize, or add commentary. Extract key sentences and insights verbatim.

Please make sure to follow all the guidelines carefully and ensure that every tweet is under 280 characters according to Twitter's official rules.

Article: Test content."""

    compressed = compress_prompt(verbose_prompt)

    # Should remove some of the verbose instructions
    assert "carefully" not in compressed.lower() or len(compressed) < len(verbose_prompt) * 0.8


def test_compress_prompt_empty_input() -> None:
    """Test that empty prompts are handled."""
    assert compress_prompt("") == ""


def test_compress_prompt_whitespace_only() -> None:
    """Test that whitespace-only prompts are handled."""
    compressed = compress_prompt("   \n\n   \n   ")
    assert compressed.strip() == ""
