# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Threadify** converts blog URLs into Twitter/X threads or single posts using AI. Built with TDD approach following a 21-prompt implementation plan.

**Tech Stack:**
- Backend: FastAPI (Python 3.11+), SQLAlchemy, SQLite
- Frontend: Server-rendered (Jinja2 + HTMX)
- Node Service: Express.js with twitter-text for official length validation
- AI: OpenAI GPT-4o-mini (primary), GPT-4o (fallback)
- Deployment: Docker Compose, Caddy reverse proxy, Cloudflared tunnel

## Essential Commands

### Development Setup
```bash
# Python dependencies
poetry install
poetry shell

# Node length service
cd node-helpers/length-service && pnpm install && cd ../..

# Generate AES key for secrets
python -c "import secrets; import base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"

# Pre-commit hooks
poetry run pre-commit install
```

### Testing
```bash
# Run all Python tests with coverage
poetry run pytest

# Run specific test file
poetry run pytest backend/tests/test_scraper.py

# Run specific test function
poetry run pytest backend/tests/test_scraper.py::test_function_name

# Run with coverage report (HTML)
poetry run pytest --cov=backend/app --cov-report=html

# Run Node tests
cd node-helpers/length-service && pnpm test

# Run Node tests in watch mode
cd node-helpers/length-service && pnpm test:watch
```

### Code Quality (Pre-commit)
```bash
# Auto-fix linting and formatting
poetry run ruff check backend/ --fix
poetry run black backend/

# Type checking
poetry run mypy backend/app

# Check without fixing (what CI runs)
poetry run ruff check backend/
poetry run black --check backend/
```

### Database Migrations
```bash
# Generate migration after model changes
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history
```

### Running Services
```bash
# Terminal 1: FastAPI backend
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Node length service
cd node-helpers/length-service && pnpm dev

# Access points:
# - http://localhost:8000 (FastAPI)
# - http://localhost:8000/docs (API docs)
# - http://localhost:8000/healthz (health check)
# - http://localhost:8080/healthz (length service)
```

## Architecture & Key Concepts

### Microservices Communication
The system is composed of two services that communicate via HTTP:

1. **FastAPI Backend** (port 8000): Main application logic
2. **Node Length Service** (port 8080): Official tweet length validation using `twitter-text`

The Python backend calls the Node service via `backend/app/clients/length_client.py` to validate tweet lengths using Twitter's official rules (URLs weighted at 23 chars, emoji handling, etc.).

### Data Flow Pipeline
```
URL Input → Canonicalize → Scrape → Generate (OpenAI) → Review/Post → History
                              ↓
                        Hero Image Selection
                              ↓
                        Budget Guardrails
                              ↓
                        Length Validation (Node)
```

### Database Architecture
**Models** (`backend/app/db/models.py`):
- `Account`: OAuth tokens (encrypted), Twitter/X handle
- `Run`: Each submission (URL, settings, status, cost)
- `Tweet`: Individual tweets in thread (text, media_alt, posted_tweet_id)
- `Image`: Hero image candidates with dimensions
- `Settings`: Default configuration
- `ApiToken`: CLI authentication (hashed)

**Key Pattern**: Sensitive fields (OAuth tokens) are encrypted at rest using AES-GCM. The `Account` model uses `@hybrid_property` to transparently encrypt/decrypt tokens.

### Security Layers
1. **AES-GCM Encryption** (`backend/app/security/crypto.py`): Encrypts OAuth tokens at rest
2. **OAuth2 PKCE** (`backend/app/security/oauth_x.py`): Twitter/X authentication flow
3. **Caddy Basic Auth**: Web UI protection (excludes `/oauth/*` paths)
4. **API Tokens**: CLI authentication (stored hashed)

### Dependency Injection Pattern
All services use dependency injection for testability:

```python
def function_name(
    param: str,
    http_get: Callable[[str], httpx.Response] | None = None,
) -> Result:
    """Injectable HTTP client for testing."""
    if http_get is None:
        http_get = _default_http_get
    # Use injected client...
```

This allows tests to mock HTTP calls without touching real APIs.

### Content Generation Pipeline

**Scraping** (`backend/app/services/scraper.py`):
- Primary: trafilatura (fast, metadata-aware)
- Fallback: readability-lxml (handles JS-heavy pages)
- Extracts: title, body text, hero image candidates, metadata
- Flags articles <200 words for Review mode

**Image Processing** (`backend/app/services/images.py`):
- Selection priority: og:image → twitter:image → largest in-article
- Validation: width ≥800px required
- Processing: downscale to ≤1600px, strip EXIF, re-encode JPEG
- Alt text: auto-generated from title/lede (≤120 chars)

**AI Generation** (`backend/app/services/generate.py`):
- Primary: GPT-4o-mini (temp 0.35)
- Fallback: GPT-4o for articles >2500 words
- Strict JSON schema output
- Cost estimation before/after generation
- Budget guardrails: $0.02 soft cap per run

**Length Validation**:
- Python calls Node service via HTTP
- Uses official `twitter-text` library
- Validates 280 char limit with proper weighting
- Batch validation endpoint available

### Testing Strategy by Layer

**Unit Tests**: Pure functions, no I/O
- Crypto seal/unseal
- URL canonicalization rules
- Budget calculations
- Alt text generation

**Component Tests**: Services with mocked dependencies
- Scraper (mock HTML responses)
- Generator (mock OpenAI)
- Image processor (programmatic test images)
- Length client (mock Node service)

**Integration Tests**: FastAPI endpoints with test DB
- OAuth flow (mocked X API)
- Web form submission
- Review page rendering
- In-memory SQLite for isolation

**Contract Tests**: Service boundaries
- Python length client ↔ Node service
- Verify API contracts match

**Property Tests**: Invariants that must hold
- Thread numbering: 1/T through T/T
- No tweet >280 chars (official rules)
- Reference tweet not counted in T

## Code Style Requirements

### Python (Enforced by CI)
- **Black** formatting: 100 char line length
- **Ruff** linting: pycodestyle, pyflakes, isort, flake8-bugbear
- **Mypy** strict mode: all functions typed
- Modern type syntax: `str | None` not `Optional[str]`
- Imports: `from collections.abc import Callable`
- Docstrings: Google style, all public functions
- Type ignores: Always specify error code `# type: ignore[assignment]`

### TypeScript/Node
- **Strict mode** enabled
- **Prettier** formatting
- **ESLint** with TypeScript plugin
- Prefer interfaces over types
- Use async/await (not promises)

### Database Conventions
- SQLAlchemy 2.0 mapped_column syntax
- Pydantic v2 schemas with `ConfigDict(from_attributes=True)`
- Alembic migrations must be reversible (upgrade/downgrade)
- Migrations stored in `backend/app/db/migrations/versions/`

## TDD Workflow (Critical)

This project follows **strict TDD** with a 21-prompt implementation plan (`prompt_plan.md`):

### Process for Each Feature:
1. **Read prompt** from `prompt_plan.md` to understand scope
2. **Write tests FIRST** before any implementation
3. **Run tests** to verify they fail (red phase)
4. **Implement minimal code** to pass tests (green phase)
5. **Run all checks** (pytest, ruff, black, mypy)
6. **Commit** with descriptive message
7. **Mark prompt complete** in `prompt_plan.md`
8. **Verify CI passes** on GitHub Actions

### Completed Prompts (✅)
1. Scaffold & CI
2. DB & Models & Migrations
3. AES-GCM Crypto
4. Node Length Service + Client
5. Canonicalize
6. Scraper
7. Hero Image
8. Generator
9. Budget Guardrails
10. OAuth2 PKCE

### Next Prompts (Upcoming)
11. Posting Core (thread/single, pacing, resume)
12. Duplicate Detection
13. Web UI + Review (HTMX/Jinja)
14. CLI (Typer)
15-21. See `prompt_plan.md` for complete roadmap

## Configuration Management

**Environment Variables** (`.env` file):
```bash
SECRET_AES_KEY=<base64url-encoded 32-byte key>
OPENAI_API_KEY=<openai-api-key>
X_CLIENT_ID=<twitter-client-id>
X_CLIENT_SECRET=<twitter-client-secret>
LENGTH_SERVICE_URL=http://localhost:8080
DATABASE_URL=sqlite:///./data/threadify.db
```

**Loading**: Via Pydantic Settings (`backend/app/config.py`)
- Auto-loads from `.env` file
- Type-safe with defaults
- Access via `get_settings()` singleton

## Common Patterns & Templates

### Service Module Pattern
Every service module follows this structure:
- Custom exception class (`ModuleError`)
- Result dataclass
- Main function with injectable dependencies
- Private `_default_http_get` helper
- Full type hints and docstrings

See `.cursorrules` file for complete templates.

### Test File Pattern
- Mirror structure: `app/services/scraper.py` → `tests/test_scraper.py`
- Descriptive names: `test_function_scenario_expected_result`
- Arrange-Act-Assert structure
- Mock external dependencies
- Never make real network calls

### Mock Fixtures
Tests create fixtures programmatically:
- HTML: via string templates
- Images: via PIL Image.new()
- HTTP responses: dataclass with status/content
- OpenAI: mock client returning fixture JSON

## Important Files & References

- **`.cursorrules`**: Complete coding standards, patterns, test templates
- **`prompt_plan.md`**: TDD implementation roadmap (21 prompts)
- **`spec.md`**: Complete functional specification
- **`pyproject.toml`**: Dependencies, tool configs, pytest settings
- **`alembic.ini`**: Migration configuration
- **`deploy/env.example`**: Environment variable template

## CI/CD Pipeline

**GitHub Actions** (`.github/workflows/ci.yml`) runs on every push:

Python Checks:
1. `ruff check backend/`
2. `black --check backend/`
3. `mypy backend/app`
4. `pytest --cov=backend/app --cov-report=xml`

Node Checks:
1. `pnpm test` (in length-service)

**All checks must pass** before merge. Coverage target: >90%

## Special Considerations

### OAuth Flow
- Routes under `/oauth/x/*` are exempt from Basic Auth
- Uses PKCE (code_verifier/code_challenge) for security
- State parameter validated to prevent CSRF
- Tokens encrypted before storage using AES-GCM

### Data Retention
- Article text/outputs purged after 30 days
- Scheduled purge: 03:30 America/Toronto timezone
- Minimal audit fields retained (IDs, timestamps, cost)

### Posting Reliability
- Thread pacing: ~3s jittered delay between tweets
- Resume from last success if mid-thread failure
- Second failure → convert to Review mode
- Rate limit respect with up to 3 retries

### Duplicate Prevention
- URL canonicalization: lowercase host, drop www, strip tracking params, follow redirects
- Duplicate check: canonical URL + account combination
- Auto-post: block unless `--force` flag
- Review mode: warn but allow override

## Troubleshooting

### Common Test Failures
- **Import errors**: Ensure `poetry shell` is active
- **Database errors**: Tests use in-memory SQLite, check fixtures
- **Type errors**: Add specific `# type: ignore[error-code]`
- **Mypy in tests**: Disabled for test files (see pyproject.toml)

### Node Service Issues
- Check port 8080 is available
- Ensure twitter-text dependency installed
- Python client expects JSON response format

### Migration Issues
- Create data/ directory: `mkdir -p data`
- Test migrations in temp DB before applying
- Always include upgrade AND downgrade

## Development Checklist

Before committing:
- [ ] Tests written first (TDD)
- [ ] All tests pass: `poetry run pytest`
- [ ] Linting passes: `poetry run ruff check backend/`
- [ ] Formatting applied: `poetry run black backend/`
- [ ] Type checking passes: `poetry run mypy backend/app`
- [ ] Node tests pass (if changed): `cd node-helpers/length-service && pnpm test`
- [ ] Coverage >90%
- [ ] Commit message follows convention (feat/fix/docs/etc)

Before marking prompt complete:
- [ ] All acceptance criteria met
- [ ] `prompt_plan.md` updated with ✅
- [ ] GitHub Actions CI passes
- [ ] No skipped tests
- [ ] Documentation updated if needed
