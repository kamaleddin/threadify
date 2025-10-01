"""Command-line interface for Threadify."""

import json
from pathlib import Path

import httpx
import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

VERSION = "0.1.0"
DEFAULT_API_URL = "http://localhost:8000"

app = typer.Typer(help="Convert blog posts to Twitter/X threads")
console = Console()


def get_config_path() -> Path:
    """Get the configuration file path."""
    return Path.home() / ".threadify" / "config.json"


def load_config() -> dict[str, str]:
    """Load configuration from file."""
    config_path = get_config_path()
    if not config_path.exists():
        rprint("[red]No configuration found.[/red]")
        rprint("Run [cyan]threadify configure[/cyan] to set up your API token.")
        raise typer.Exit(1)

    try:
        with open(config_path) as f:
            return json.load(f)
    except Exception as e:
        rprint(f"[red]Error loading config:[/red] {e}")
        raise typer.Exit(1) from e


def save_config(api_token: str, api_url: str) -> None:
    """Save configuration to file."""
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    config = {
        "api_token": api_token,
        "api_url": api_url,
    }

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


@app.command("configure")
def configure() -> None:
    """Configure API token and URL."""
    rprint("[cyan]Threadify Configuration[/cyan]")
    rprint()

    api_token = typer.prompt("API Token", hide_input=True)
    api_url = typer.prompt("API URL", default=DEFAULT_API_URL)

    save_config(api_token, api_url)
    rprint()
    rprint("[green]Configuration saved![/green]")


@app.command("submit")
def submit(
    url: str = typer.Argument(..., help="URL of the blog post to convert"),
    auto: bool = typer.Option(False, "--auto", help="Post automatically without review"),
    account: str | None = typer.Option(None, "--account", "-a", help="Twitter/X account handle"),
    style: str | None = typer.Option(
        None,
        "--style",
        "-s",
        help="Writing style: extractive, explanatory, provocative, academic, punchy",
    ),
    single: bool = typer.Option(False, "--single", help="Create single post instead of thread"),
    hook: bool = typer.Option(False, "--hook", help="Add engaging hook to first tweet"),
    image: bool = typer.Option(False, "--image", help="Include hero image if available"),
    reference: str | None = typer.Option(None, "--reference", "-r", help="Reference reply text"),
    utm: str | None = typer.Option(None, "--utm", "-u", help="UTM campaign parameter"),
    thread_cap: int | None = typer.Option(None, "--thread-cap", help="Maximum tweets in thread"),
    single_cap: int | None = typer.Option(
        None, "--single-cap", help="Maximum characters in single post"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Force submission even if duplicate"),
) -> None:
    """Submit a blog post URL for conversion to Twitter/X thread or post."""
    # Load configuration
    config = load_config()

    # Build request payload
    payload = {
        "url": url,
        "mode": "auto" if auto else "review",
        "type": "single" if single else "thread",
    }

    # Add optional parameters
    if account:
        payload["account"] = account
    if style:
        payload["style"] = style
    if hook:
        payload["hook"] = hook
    if image:
        payload["image"] = image
    if reference:
        payload["reference"] = reference
    if utm:
        payload["utm"] = utm
    if thread_cap:
        payload["thread_cap"] = thread_cap
    if single_cap:
        payload["single_cap"] = single_cap
    if force:
        payload["force"] = force

    # Make API request
    api_url = config["api_url"]
    headers = {"Authorization": f"Bearer {config['api_token']}"}

    with console.status("[cyan]Submitting URL...[/cyan]"):
        try:
            response = httpx.post(
                f"{api_url}/api/submit",
                json=payload,
                headers=headers,
                timeout=60.0,
                follow_redirects=False,
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            rprint(f"[red]Error submitting URL:[/red] {e}")
            if hasattr(e, "response") and e.response:
                rprint(f"[red]Response:[/red] {e.response.text}")
            raise typer.Exit(1) from e

    # Handle response based on mode
    if response.status_code == 303:  # Redirect to review
        location = response.headers.get("Location", "")
        review_url = f"{api_url}{location}"
        rprint()
        rprint("[green]✓ Submitted successfully![/green]")
        rprint(f"Review at: [cyan]{review_url}[/cyan]")

    elif response.status_code == 200:  # Auto mode completed
        result = response.json()
        rprint()
        rprint("[green]✓ Posted successfully![/green]")
        rprint()

        if "tweets" in result:
            table = Table(title="Posted Tweets")
            table.add_column("Tweet", style="cyan", no_wrap=False)
            table.add_column("Link", style="green")

            for _i, tweet in enumerate(result["tweets"], 1):
                tweet_text = tweet.get("text", "")
                if len(tweet_text) > 50:
                    tweet_text = tweet_text[:50] + "..."
                permalink = tweet.get("permalink", "N/A")
                table.add_row(tweet_text, permalink)

            console.print(table)
    else:
        rprint(f"[yellow]Unexpected response:[/yellow] {response.status_code}")
        rprint(response.text)


@app.callback()
def main() -> None:
    """Threadify - Convert blog posts to Twitter/X threads.

    Default command is 'submit'. Run 'threadify submit --help' for options.
    """
    pass


@app.command("version")
def version() -> None:
    """Show version information."""
    rprint(f"Threadify CLI version {VERSION}")


if __name__ == "__main__":
    app()
