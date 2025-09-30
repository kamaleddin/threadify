"""Tests for AI generation service."""

import pytest
from app.services.generate import (
    GeneratedReference,
    GeneratedSingle,
    GeneratedThread,
    GenerationError,
    GenerationSettings,
    ScrapeResult,
    build_reference_prompt,
    build_single_prompt,
    build_thread_prompt,
    choose_model,
    estimate_cost,
    estimate_tokens,
    generate_reference,
    generate_single,
    generate_thread,
)


@pytest.fixture
def sample_scrape() -> ScrapeResult:
    """Create a sample scrape result for testing."""
    return ScrapeResult(
        title="The Future of AI",
        text="This is a sample article about AI. " * 50,  # ~500 chars
        word_count=100,
        site_name="TechBlog",
        author="Jane Doe",
    )


@pytest.fixture
def long_scrape() -> ScrapeResult:
    """Create a long scrape result (>2500 words) for testing."""
    return ScrapeResult(
        title="Comprehensive Guide to Machine Learning",
        text="Machine learning is a complex field. " * 500,  # ~18k chars
        word_count=3000,
        site_name="DeepDive",
        author="Dr. Smith",
    )


@pytest.fixture
def mock_openai_thread():
    """Create a mock OpenAI client that returns a thread response."""

    class MockMessage:
        def __init__(self):
            from app.services.generate import GeneratedThreadSchema, TweetSchema

            self.parsed = GeneratedThreadSchema(
                tweets=[
                    TweetSchema(text="First tweet in the thread"),
                    TweetSchema(text="Second tweet with more details"),
                    TweetSchema(text="Final tweet with conclusion"),
                ],
                style_used="conversational",
                hook_used=True,
            )

    class MockChoice:
        def __init__(self):
            self.message = MockMessage()

    class MockUsage:
        def __init__(self):
            self.prompt_tokens = 500
            self.completion_tokens = 150

    class MockCompletion:
        def __init__(self):
            self.choices = [MockChoice()]
            self.usage = MockUsage()

    class MockBetaChat:
        def __init__(self):
            self.completions = self

        def parse(self, **kwargs):
            return MockCompletion()

    class MockClient:
        def __init__(self):
            self.beta = MockBeta()

    class MockBeta:
        def __init__(self):
            self.chat = MockBetaChat()

    return MockClient()


@pytest.fixture
def mock_openai_single():
    """Create a mock OpenAI client that returns a single tweet response."""

    class MockMessage:
        def __init__(self):
            from app.services.generate import GeneratedSingleSchema

            self.parsed = GeneratedSingleSchema(
                text="A compelling single tweet summarizing the article",
                style_used="analytical",
            )

    class MockChoice:
        def __init__(self):
            self.message = MockMessage()

    class MockUsage:
        def __init__(self):
            self.prompt_tokens = 400
            self.completion_tokens = 50

    class MockCompletion:
        def __init__(self):
            self.choices = [MockChoice()]
            self.usage = MockUsage()

    class MockBetaChat:
        def __init__(self):
            self.completions = self

        def parse(self, **kwargs):
            return MockCompletion()

    class MockClient:
        def __init__(self):
            self.beta = MockBeta()

    class MockBeta:
        def __init__(self):
            self.chat = MockBetaChat()

    return MockClient()


@pytest.fixture
def mock_openai_reference():
    """Create a mock OpenAI client that returns a reference tweet response."""

    class MockMessage:
        def __init__(self):
            from app.services.generate import GeneratedReferenceSchema

            self.parsed = GeneratedReferenceSchema(
                text="Original: The Future of AI by Jane Doe on TechBlog"
            )

    class MockChoice:
        def __init__(self):
            self.message = MockMessage()

    class MockUsage:
        def __init__(self):
            self.prompt_tokens = 200
            self.completion_tokens = 20

    class MockCompletion:
        def __init__(self):
            self.choices = [MockChoice()]
            self.usage = MockUsage()

    class MockBetaChat:
        def __init__(self):
            self.completions = self

        def parse(self, **kwargs):
            return MockCompletion()

    class MockClient:
        def __init__(self):
            self.beta = MockBeta()

    class MockBeta:
        def __init__(self):
            self.chat = MockBetaChat()

    return MockClient()


def test_estimate_tokens() -> None:
    """Test token estimation (rough approximation)."""
    text = "This is a test string"  # 21 chars
    tokens = estimate_tokens(text)
    assert tokens == 5  # 21 // 4


def test_estimate_tokens_empty() -> None:
    """Test token estimation with empty string."""
    assert estimate_tokens("") == 0


def test_estimate_cost_gpt4o_mini() -> None:
    """Test cost estimation for gpt-4o-mini."""
    prompt = "a" * 400  # 400 chars = ~100 tokens
    cost = estimate_cost(prompt, expected_output_tokens=50, model="gpt-4o-mini")
    # 100 * 0.150/1M + 50 * 0.600/1M = 0.000015 + 0.00003 = 0.000045
    assert cost == pytest.approx(0.000045, rel=1e-6)


def test_estimate_cost_gpt4o() -> None:
    """Test cost estimation for gpt-4o."""
    prompt = "a" * 400  # 400 chars = ~100 tokens
    cost = estimate_cost(prompt, expected_output_tokens=50, model="gpt-4o")
    # 100 * 2.50/1M + 50 * 10.00/1M = 0.00025 + 0.0005 = 0.00075
    assert cost == pytest.approx(0.00075, rel=1e-6)


def test_choose_model_short() -> None:
    """Test model selection for short content."""
    assert choose_model(1000) == "gpt-4o-mini"


def test_choose_model_long() -> None:
    """Test model selection for long content (>2500 words)."""
    assert choose_model(3000) == "gpt-4o"


def test_choose_model_boundary() -> None:
    """Test model selection at the boundary."""
    assert choose_model(2500) == "gpt-4o-mini"
    assert choose_model(2501) == "gpt-4o"


def test_build_thread_prompt_extractive(sample_scrape: ScrapeResult) -> None:
    """Test building a thread prompt with extractive mode."""
    settings = GenerationSettings(mode="thread", extractive=True, hook=True)
    prompt = build_thread_prompt(sample_scrape, settings)

    assert "Use ONLY the author's own words" in prompt
    assert "The Future of AI" in prompt
    assert "TechBlog" in prompt
    assert "Jane Doe" in prompt
    assert "hook" in prompt.lower()


def test_build_thread_prompt_summarize(sample_scrape: ScrapeResult) -> None:
    """Test building a thread prompt with summarize mode."""
    settings = GenerationSettings(mode="thread", extractive=False, hook=False)
    prompt = build_thread_prompt(sample_scrape, settings)

    assert "Summarize and distill" in prompt
    assert "Do not paraphrase" not in prompt


def test_build_thread_prompt_with_style(sample_scrape: ScrapeResult) -> None:
    """Test building a thread prompt with a specific style."""
    settings = GenerationSettings(mode="thread", style="conversational", hook=True)
    prompt = build_thread_prompt(sample_scrape, settings)

    assert "conversational" in prompt.lower()


def test_build_single_prompt(sample_scrape: ScrapeResult) -> None:
    """Test building a single tweet prompt."""
    settings = GenerationSettings(mode="single", style="analytical")
    prompt = build_single_prompt(sample_scrape, settings)

    assert "single Twitter/X post" in prompt
    assert "analytical" in prompt.lower()
    assert "The Future of AI" in prompt


def test_build_reference_prompt(sample_scrape: ScrapeResult) -> None:
    """Test building a reference tweet prompt."""
    prompt = build_reference_prompt(sample_scrape)

    assert "reference tweet" in prompt.lower()
    assert "The Future of AI" in prompt
    assert "TechBlog" in prompt


def test_generate_thread_success(sample_scrape: ScrapeResult, mock_openai_thread) -> None:
    """Test successful thread generation."""
    settings = GenerationSettings(mode="thread", style="conversational", hook=True)
    result = generate_thread(sample_scrape, settings, openai_client=mock_openai_thread)

    assert isinstance(result, GeneratedThread)
    assert len(result.tweets) == 3
    assert result.tweets[0] == "First tweet in the thread"
    assert result.style_used == "conversational"
    assert result.hook_used is True
    assert result.tokens_in == 500
    assert result.tokens_out == 150
    assert result.cost_usd > 0
    assert result.model_used == "gpt-4o-mini"


def test_generate_thread_long_content(long_scrape: ScrapeResult, mock_openai_thread) -> None:
    """Test thread generation with long content uses gpt-4o."""
    settings = GenerationSettings(mode="thread")
    result = generate_thread(long_scrape, settings, openai_client=mock_openai_thread)

    assert result.model_used == "gpt-4o"


def test_generate_single_success(sample_scrape: ScrapeResult, mock_openai_single) -> None:
    """Test successful single tweet generation."""
    settings = GenerationSettings(mode="single", style="analytical")
    result = generate_single(sample_scrape, settings, openai_client=mock_openai_single)

    assert isinstance(result, GeneratedSingle)
    assert result.text == "A compelling single tweet summarizing the article"
    assert result.style_used == "analytical"
    assert result.tokens_in == 400
    assert result.tokens_out == 50
    assert result.cost_usd > 0
    assert result.model_used == "gpt-4o-mini"


def test_generate_reference_success(sample_scrape: ScrapeResult, mock_openai_reference) -> None:
    """Test successful reference tweet generation."""
    result = generate_reference(sample_scrape, openai_client=mock_openai_reference)

    assert isinstance(result, GeneratedReference)
    assert "Original:" in result.text
    assert result.tokens_in == 200
    assert result.tokens_out == 20
    assert result.cost_usd > 0
    assert result.model_used == "gpt-4o-mini"


def test_generate_thread_with_different_styles(
    sample_scrape: ScrapeResult, mock_openai_thread
) -> None:
    """Test thread generation with different style settings."""
    styles = ["conversational", "analytical", "casual", "enthusiastic"]

    for style in styles:
        settings = GenerationSettings(mode="thread", style=style)
        prompt = build_thread_prompt(sample_scrape, settings)
        assert style in prompt.lower()


def test_generate_thread_no_hook(sample_scrape: ScrapeResult) -> None:
    """Test that hook instruction is excluded when hook=False."""
    settings = GenerationSettings(mode="thread", hook=False)
    prompt = build_thread_prompt(sample_scrape, settings)

    # Hook instruction "Start with a compelling hook" should not be present
    assert "compelling hook" not in prompt.lower()


def test_generate_with_api_error() -> None:
    """Test that API errors are properly wrapped."""

    class MockBrokenClient:
        def __init__(self):
            self.beta = MockBrokenBeta()

    class MockBrokenBeta:
        def __init__(self):
            self.chat = MockBrokenChat()

    class MockBrokenChat:
        def __init__(self):
            self.completions = self

        def parse(self, **kwargs):
            raise Exception("API connection failed")

    scrape = ScrapeResult(title="Test", text="Test content", word_count=10)
    settings = GenerationSettings(mode="thread")

    with pytest.raises(GenerationError, match="OpenAI API error"):
        generate_thread(scrape, settings, openai_client=MockBrokenClient())


def test_cost_calculation_thread(sample_scrape: ScrapeResult, mock_openai_thread) -> None:
    """Test that cost is calculated correctly for thread generation."""
    settings = GenerationSettings(mode="thread")
    result = generate_thread(sample_scrape, settings, openai_client=mock_openai_thread)

    # Mock returns 500 input, 150 output tokens
    # gpt-4o-mini: 500 * 0.150/1M + 150 * 0.600/1M
    expected_cost = (500 * 0.150 / 1_000_000) + (150 * 0.600 / 1_000_000)
    assert result.cost_usd == pytest.approx(expected_cost, rel=1e-6)


def test_cost_calculation_single(sample_scrape: ScrapeResult, mock_openai_single) -> None:
    """Test that cost is calculated correctly for single tweet generation."""
    settings = GenerationSettings(mode="single")
    result = generate_single(sample_scrape, settings, openai_client=mock_openai_single)

    # Mock returns 400 input, 50 output tokens
    expected_cost = (400 * 0.150 / 1_000_000) + (50 * 0.600 / 1_000_000)
    assert result.cost_usd == pytest.approx(expected_cost, rel=1e-6)


def test_extractive_vs_summarize_prompts(sample_scrape: ScrapeResult) -> None:
    """Test that extractive and summarize modes produce different prompts."""
    extractive_settings = GenerationSettings(extractive=True)
    summarize_settings = GenerationSettings(extractive=False)

    extractive_prompt = build_thread_prompt(sample_scrape, extractive_settings)
    summarize_prompt = build_thread_prompt(sample_scrape, summarize_settings)

    assert "ONLY the author's own words" in extractive_prompt
    assert "ONLY the author's own words" not in summarize_prompt
    assert "Summarize and distill" in summarize_prompt
