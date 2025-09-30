"""Budget guardrails for API cost management."""


class BudgetExceededError(Exception):
    """Raised when a generation request exceeds budget cap."""

    pass


def within_budget(estimate_usd: float, cap_usd: float = 0.02) -> bool:
    """
    Check if estimated cost is within budget cap.

    Args:
        estimate_usd: Estimated cost in USD
        cap_usd: Budget cap in USD (default: $0.02)

    Returns:
        True if estimate is within budget, False otherwise
    """
    # Treat negative estimates as zero (edge case protection)
    if estimate_usd < 0:
        estimate_usd = 0.0

    return estimate_usd <= cap_usd


def compress_prompt(prompt: str) -> str:
    """
    Compress a prompt by removing verbosity while preserving key information.

    Strategy:
    - Remove redundant whitespace
    - Trim verbose instructions
    - Keep essential: task description, article title/content, output format

    Args:
        prompt: Original prompt text

    Returns:
        Compressed prompt text
    """
    if not prompt or not prompt.strip():
        return prompt.strip()

    # Normalize whitespace (collapse multiple spaces/newlines)
    lines = [line.strip() for line in prompt.split("\n")]
    # Remove empty lines
    lines = [line for line in lines if line]

    # Rejoin with single newlines
    compressed = "\n".join(lines)

    # Further compression: remove verbose phrases
    verbose_phrases = [
        "Do not paraphrase, summarize, or add commentary. ",
        "Extract key sentences and insights verbatim. ",
        "Please make sure to ",
        "carefully and ",
        "ensure that ",
        "according to Twitter's official rules",
        "following Twitter's rules",
        "(following Twitter's rules)",
    ]

    for phrase in verbose_phrases:
        compressed = compressed.replace(phrase, "")

    # Collapse multiple spaces that may have been created
    while "  " in compressed:
        compressed = compressed.replace("  ", " ")

    # Clean up any resulting empty lines
    lines = [line.strip() for line in compressed.split("\n")]
    lines = [line for line in lines if line]
    compressed = "\n".join(lines)

    return compressed
