# Threadify

Turn any public blog URL into Twitter/X threads or single posts with AI.

## Overview

Threadify is an MVP service that converts blog articles into optimized Twitter/X content:
- **Thread mode**: Numbered tweets (1/T ... T/T) with 280 char limits
- **Single post mode**: Long-form posts up to 25,000 characters
- **Reference attribution**: Optional attribution reply with UTM tracking
- **Hero images**: Automatic selection, validation, and optimization
- **Multiple accounts**: Support for multiple Twitter/X accounts via OAuth2 PKCE
- **Review UI**: Web interface for editing and regenerating content
- **CLI**: Command-line interface with API token auth

## Architecture

- **Backend**: FastAPI (Python 3.11+) with server-rendered UI (Jinja2 + HTMX)
- **CLI**: Typer-based command-line tool
- **Length Service**: Node.js microservice using `twitter-text` for official length validation
- **Database**: SQLite with AES-GCM encryption for sensitive fields
- **AI**: OpenAI GPT-4o-mini (primary) with GPT-4o fallback
- **Deployment**: Docker Compose + Caddy + Cloudflared tunnel

## Project Status

Currently implementing via TDD approach with 21 incremental prompts. See `prompt_plan.md` for the complete development roadmap.

### Completed
- ✅ Prompt 01: Scaffold & CI (repo structure, tooling, basic tests)

### In Progress
- ⏳ Prompt 02: Database models and migrations

### Upcoming
- Prompts 03-21: See `todo.md` for detailed checklist

## Prerequisites

- **Python**: 3.11 or higher
- **Node.js**: 20.x or higher
- **pnpm**: 8.x or higher
- **Poetry**: 1.7.1 or higher
- **Docker & Docker Compose**: (optional, for containerized deployment)

## Local Development Setup

### 1. Clone the repository

```bash
git clone https://github.com/kamaleddin/threadify.git
cd threadify
```

### 2. Set up Python backend

```bash
# Install Poetry if not already installed
curl -sSL https://install.python-poetry.org | python3 -

# Install Python dependencies
poetry install

# Activate virtual environment
poetry shell
```

### 3. Set up Node length service

```bash
cd node-helpers/length-service

# Install pnpm if not already installed
npm install -g pnpm

# Install dependencies
pnpm install

cd ../..
```

### 4. Set up environment variables

```bash
# Copy example env file
cp deploy/env.example .env

# Generate AES key
python -c "import secrets; import base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"

# Edit .env and add your keys
```

### 5. Set up pre-commit hooks (optional but recommended)

```bash
poetry run pre-commit install
```

## Running Tests

### Python tests

```bash
# Run all tests with coverage
poetry run pytest

# Run specific test file
poetry run pytest backend/tests/test_health.py

# Run with verbose output
poetry run pytest -v

# Run with coverage report
poetry run pytest --cov=backend/app --cov-report=html
```

### Node tests

```bash
cd node-helpers/length-service
pnpm test

# Watch mode
pnpm test:watch
```

### Linting and Type Checking

```bash
# Python
poetry run ruff check backend/
poetry run black --check backend/
poetry run mypy backend/app

# Auto-fix linting issues
poetry run ruff check --fix backend/
poetry run black backend/
```

## Running the Application

### Development mode

```bash
# Terminal 1: Start FastAPI backend
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Start Node length service
cd node-helpers/length-service
pnpm dev
```

Visit:
- FastAPI: http://localhost:8000
- Health check: http://localhost:8000/healthz
- API docs: http://localhost:8000/docs
- Length service: http://localhost:8080/health

### Docker Compose (when Dockerfiles are complete)

```bash
# Build and start all services
docker-compose -f deploy/docker-compose.yml up --build

# Run in background
docker-compose -f deploy/docker-compose.yml up -d

# View logs
docker-compose -f deploy/docker-compose.yml logs -f

# Stop services
docker-compose -f deploy/docker-compose.yml down
```

## Project Structure

```
threadify/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── config.py            # Configuration (future)
│   │   ├── deps.py              # Dependencies (future)
│   │   ├── security/            # Auth, crypto, OAuth (future)
│   │   ├── db/                  # Database models, migrations (future)
│   │   ├── services/            # Business logic (future)
│   │   └── web/                 # Web UI routes, templates (future)
│   └── tests/
│       ├── conftest.py          # Pytest fixtures
│       └── test_health.py       # Health endpoint tests
├── node-helpers/
│   └── length-service/
│       ├── src/index.ts         # Express server (placeholder)
│       ├── test/index.test.ts   # Service tests
│       └── package.json
├── cli/                         # CLI tool (future)
├── deploy/
│   ├── docker-compose.yml       # Container orchestration
│   ├── Dockerfile.api           # Backend container (placeholder)
│   ├── Dockerfile.node          # Node service container (placeholder)
│   ├── Caddyfile                # Reverse proxy config (future)
│   └── env.example              # Environment variables template
├── .github/workflows/
│   └── ci.yml                   # CI/CD pipeline
├── pyproject.toml               # Python dependencies & config
├── .pre-commit-config.yaml      # Git hooks configuration
├── prompt_plan.md               # TDD development prompts
├── spec.md                      # Functional specification
├── todo.md                      # Detailed task checklist
└── README.md                    # This file
```

## Contributing

This project follows a strict TDD (Test-Driven Development) approach:

1. Write tests first
2. Implement minimal code to pass tests
3. Refactor while keeping tests green
4. Commit with clear messages
5. Ensure CI passes before merging

See `CONTRIBUTING.md` (future) for detailed guidelines.

## Development Workflow

1. Pick a prompt from `prompt_plan.md` (in order)
2. Review the prompt's scope and acceptance criteria
3. Write tests first (following TDD)
4. Implement the feature
5. Run tests: `pytest` and `pnpm test`
6. Run linters: `ruff`, `black`, `mypy`
7. Commit changes with descriptive message
8. Update `prompt_plan.md` to mark prompt as complete
9. Push to GitHub and verify CI passes

## Testing Strategy

- **Unit tests**: Pure functions (crypto, canonicalizer, budget calc)
- **Component tests**: Services with mocked dependencies (scraper, generator)
- **Integration tests**: FastAPI endpoints with test database
- **Contract tests**: Node service and Python client interaction
- **E2E tests**: Full workflows with mocked external APIs (OpenAI, X)
- **Property tests**: Tweet fitting and numbering invariants

All external APIs (OpenAI, Twitter/X) are mocked in tests to keep CI hermetic and fast.

## Security

- Secrets encrypted at rest with AES-GCM
- OAuth2 PKCE flow for Twitter/X authentication
- Caddy Basic Auth for web UI (excludes OAuth endpoints)
- API tokens for CLI authentication
- HTTPS via Cloudflared tunnel
- CSRF protection on all state-changing operations

## License

MIT License - See LICENSE file for details

## Contact

- **Author**: Kamal Eddin
- **Email**: kamaleddin@capturia.ca
- **Support**: support@capturia.ca

## Acknowledgments

- Built with FastAPI, SQLAlchemy, OpenAI, and twitter-text
- Following TDD and best practices for maintainable code
- Inspired by the need for better content distribution tools
