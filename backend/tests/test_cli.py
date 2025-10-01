"""Tests for CLI commands."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from app.cli import app
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def mock_config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory."""
    config_dir = tmp_path / ".threadify"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def mock_config_file(mock_config_dir: Path) -> Path:
    """Create a config file with test API token."""
    config_file = mock_config_dir / "config.json"
    config_data = {"api_token": "test-token-123", "api_url": "http://localhost:8000"}
    config_file.write_text(json.dumps(config_data))
    return config_file


def test_cli_help() -> None:
    """Test CLI help command."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "threadify" in result.output.lower()
    assert "url" in result.output.lower()


def test_cli_version() -> None:
    """Test CLI version command."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output or "version" in result.output.lower()


@patch("app.cli.Path.home")
@patch("httpx.post")
def test_cli_submit_review_mode(
    mock_post: MagicMock, mock_home: MagicMock, mock_config_file: Path
) -> None:
    """Test submitting URL in review mode (default)."""
    mock_home.return_value = mock_config_file.parent.parent

    mock_response = MagicMock()
    mock_response.status_code = 303
    mock_response.headers = {"Location": "/review/123"}
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    result = runner.invoke(app, ["submit", "https://example.com/article"])

    assert result.exit_code == 0
    assert "Review at: http://localhost:8000/review/123" in result.output
    mock_post.assert_called_once()

    # Check the call arguments
    call_args = mock_post.call_args
    assert call_args[0][0] == "http://localhost:8000/api/submit"
    assert call_args[1]["headers"]["Authorization"] == "Bearer test-token-123"
    assert call_args[1]["json"]["url"] == "https://example.com/article"
    assert call_args[1]["json"]["mode"] == "review"


@patch("app.cli.Path.home")
@patch("httpx.post")
def test_cli_submit_auto_mode(
    mock_post: MagicMock, mock_home: MagicMock, mock_config_file: Path
) -> None:
    """Test submitting URL in auto mode."""
    mock_home.return_value = mock_config_file.parent.parent

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "completed",
        "tweets": [
            {"text": "Tweet 1", "permalink": "https://twitter.com/user/status/123"},
            {"text": "Tweet 2", "permalink": "https://twitter.com/user/status/124"},
        ],
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    result = runner.invoke(app, ["submit", "https://example.com/article", "--auto"])

    assert result.exit_code == 0
    assert "Posted successfully!" in result.output
    assert "https://twitter.com/user/status/123" in result.output

    call_args = mock_post.call_args
    assert call_args[1]["json"]["mode"] == "auto"


@patch("app.cli.Path.home")
@patch("httpx.post")
def test_cli_with_account(
    mock_post: MagicMock, mock_home: MagicMock, mock_config_file: Path
) -> None:
    """Test specifying account."""
    mock_home.return_value = mock_config_file.parent.parent

    mock_response = MagicMock()
    mock_response.status_code = 303
    mock_response.headers = {"Location": "/review/123"}
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    result = runner.invoke(app, ["submit", "https://example.com/article", "--account", "myhandle"])

    assert result.exit_code == 0
    call_args = mock_post.call_args
    assert call_args[1]["json"]["account"] == "myhandle"


@patch("app.cli.Path.home")
@patch("httpx.post")
def test_cli_with_style(mock_post: MagicMock, mock_home: MagicMock, mock_config_file: Path) -> None:
    """Test specifying style."""
    mock_home.return_value = mock_config_file.parent.parent

    mock_response = MagicMock()
    mock_response.status_code = 303
    mock_response.headers = {"Location": "/review/123"}
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    result = runner.invoke(app, ["submit", "https://example.com/article", "--style", "academic"])

    assert result.exit_code == 0
    call_args = mock_post.call_args
    assert call_args[1]["json"]["style"] == "academic"


@patch("app.cli.Path.home")
@patch("httpx.post")
def test_cli_with_type_single(
    mock_post: MagicMock, mock_home: MagicMock, mock_config_file: Path
) -> None:
    """Test creating single post instead of thread."""
    mock_home.return_value = mock_config_file.parent.parent

    mock_response = MagicMock()
    mock_response.status_code = 303
    mock_response.headers = {"Location": "/review/123"}
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    result = runner.invoke(app, ["submit", "https://example.com/article", "--single"])

    assert result.exit_code == 0
    call_args = mock_post.call_args
    assert call_args[1]["json"]["type"] == "single"


@patch("app.cli.Path.home")
def test_cli_configure(mock_home: MagicMock, tmp_path: Path) -> None:
    """Test configure command."""
    mock_home.return_value = tmp_path

    # Simulate user input
    result = runner.invoke(app, ["configure"], input="my-api-token\nhttps://api.example.com\n")

    assert result.exit_code == 0
    assert "Configuration saved" in result.output

    # Check config file was created
    config_file = tmp_path / ".threadify" / "config.json"
    assert config_file.exists()

    config = json.loads(config_file.read_text())
    assert config["api_token"] == "my-api-token"
    assert config["api_url"] == "https://api.example.com"


@patch("app.cli.Path.home")
def test_cli_no_config_file(mock_home: MagicMock, tmp_path: Path) -> None:
    """Test CLI when config file doesn't exist."""
    mock_home.return_value = tmp_path

    result = runner.invoke(app, ["submit", "https://example.com/article"])

    assert result.exit_code != 0
    assert "No configuration found" in result.output
    assert "threadify configure" in result.output


@patch("app.cli.Path.home")
@patch("httpx.post")
def test_cli_api_error(mock_post: MagicMock, mock_home: MagicMock, mock_config_file: Path) -> None:
    """Test handling API errors."""
    mock_home.return_value = mock_config_file.parent.parent

    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Invalid URL"
    mock_response.raise_for_status.side_effect = Exception("Bad Request")
    mock_post.return_value = mock_response

    result = runner.invoke(app, ["submit", "https://example.com/article"])

    assert result.exit_code != 0
    assert "Error" in result.output or "Failed" in result.output


@patch("app.cli.Path.home")
@patch("httpx.post")
def test_cli_with_all_options(
    mock_post: MagicMock, mock_home: MagicMock, mock_config_file: Path
) -> None:
    """Test CLI with all options."""
    mock_home.return_value = mock_config_file.parent.parent

    mock_response = MagicMock()
    mock_response.status_code = 303
    mock_response.headers = {"Location": "/review/123"}
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    result = runner.invoke(
        app,
        [
            "submit",
            "https://example.com/article",
            "--auto",
            "--account",
            "myhandle",
            "--style",
            "punchy",
            "--single",
            "--hook",
            "--image",
            "--reference",
            "Check this out",
            "--utm",
            "summer_campaign",
            "--force",
        ],
    )

    assert result.exit_code == 0
    call_args = mock_post.call_args
    json_data = call_args[1]["json"]
    assert json_data["mode"] == "auto"
    assert json_data["account"] == "myhandle"
    assert json_data["style"] == "punchy"
    assert json_data["type"] == "single"
    assert json_data["hook"] is True
    assert json_data["image"] is True
    assert json_data["reference"] == "Check this out"
    assert json_data["utm"] == "summer_campaign"
    assert json_data["force"] is True
