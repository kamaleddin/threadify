# Threadify — TODO Checklist

> Work in small, test-led increments. Each milestone ends with green tests and a visible artifact (endpoint, page, or CLI output). Mark each box as you complete it. 

---

## Legend
- [ ] task to do
- [x] done
- ⛳ DoD = Definition of Done (acceptance for the milestone)

---

## 0) Pre‑flight & Environment

- [ ] Create repo `threadify` (private) with branch protection on `main`
- [ ] Add `LICENSE` (MIT), `README.md`, `CODEOWNERS`, `CONTRIBUTING.md`
- [ ] Install toolchain: Python 3.11+, Poetry, Node 20+, pnpm, Docker, Docker Compose
- [ ] Create `.gitignore` (Python, Node, Docker, macOS, VSCode)
- [ ] Decide secrets handling for local/dev: `.env` + AES key generation script
- [ ] Fill `deploy/env.example` with all env vars
  - [ ] `APP_ENV=local|dev|prod`
  - [ ] `SECRET_AES_KEY=...` (32 bytes base64url)
  - [ ] `OPENAI_API_KEY=...`
  - [ ] `LENGTH_SERVICE_URL=http://length:8080`
  - [ ] `BASIC_AUTH_USER=...`
  - [ ] `BASIC_AUTH_HASH=...` (bcrypt)
  - [ ] `X_CLIENT_ID`, `X_CLIENT_SECRET` (if used for confidential OAuth; otherwise PKCE only)
  - [ ] `OAUTH_REDIRECT_URL=https://<host>/oauth/x/callback`
  - [ ] `DATABASE_URL=sqlite:///./data/threadify.db`
  - [ ] `TZ=America/Toronto`
- [ ] Establish CI secrets in GitHub (if needed for integration tests — keep CI hermetic otherwise)
- [ ] Create `docs/` dir for additional notes if useful

⛳ **DoD**: Repo initialized, contributors can install toolchain from README and run a trivial test locally.

---

## 1) Scaffold & CI (Prompt 01)

- [ ] Initialize Poetry project (Python 3.11+) and backend skeleton
- [ ] Initialize pnpm workspace for `node-helpers/length-service`
- [ ] FastAPI `GET /healthz` returns `{ "ok": true }`
- [ ] Testing/linting config: pytest + coverage, ruff, black, mypy, pre-commit
- [ ] GitHub Actions workflow for Python (lint, type-check, test)
- [ ] Node length-service placeholder with `pnpm test` placeholder
- [ ] GitHub Actions: Node tests job
- [ ] `deploy/docker-compose.yml` (placeholders) + `deploy/env.example`
- [ ] README: local dev & test instructions

⛳ **DoD**: `pytest -q` passes; `pnpm -C node-helpers/length-service test` passes; CI green on push.

---

## 2) DB Engine, Models, Migrations (Prompt 02)

- [ ] SQLAlchemy engine/session factory (`backend/app/db/base.py`)
- [ ] Models in `models.py`: Account, Run, Tweet, Image, Settings, ApiToken; enums as strings
- [ ] Alembic init and first migration for schema
- [ ] Pydantic schemas in `schema.py` (no secrets)
- [ ] Minimal DAO helpers (create/read) for Account/Run/Tweet
- [ ] Tests: `test_db_models.py` roundtrip in tmp SQLite
- [ ] Tests: `test_migrations.py` alembic upgrade head on fresh DB

⛳ **DoD**: Alembic upgrade works; model roundtrips pass.

---

## 3) AES‑GCM Crypto for Secrets (Prompt 03)

- [ ] `security/crypto.py` with `seal` / `unseal` (v1:, 12B nonce, base64url)
- [ ] Config loads AES key from env (`config.py`)
- [ ] Hybrid props on Account for encrypted fields (e.g., tokens)
- [ ] Tests: `test_crypto.py` (roundtrip, tamper, wrong key)
- [ ] Tests: `test_account_secrets.py` (ciphertext at rest; clear on access)

⛳ **DoD**: 100% coverage on `crypto.py`; tests green.

---

## 4) Node Length Service + Python Client (Prompt 04)

- [ ] Node Express server `/length/check` POST {text}
- [ ] Use `twitter-text` for weighted length, valid range
- [ ] Reject >280 chars per rules; return `{isValid, weightedLength, permillage, validRange}`
- [ ] Supertest coverage: 280 ok, 281 fail, URL weighting, emoji
- [ ] Python client `services/length_client.py` with dataclass mapping
- [ ] Configurable `LENGTH_SERVICE_URL`
- [ ] Contract test: Python client against mock/ephemeral server; error handling when down

⛳ **DoD**: `pnpm test` passes with meaningful cases; Python client tests green.

---

## 5) Canonicalizer (Prompt 05)

- [ ] `services/canonicalize.py` pure function w/ injected `http_get`
- [ ] Rules: follow redirects → https; lowercase host; strip `www`, trailing slash, fragments
- [ ] Drop params: `utm_*`, `gclid`, `fbclid`, `ref`
- [ ] Respect `<link rel="canonical">` if same registrable domain
- [ ] Tests: redirects, canonical tag, params stripped, fragment removal

⛳ **DoD**: All canonicalization tests pass; deterministic given mock HTTP.

---

## 6) Scraper (trafilatura → readability) (Prompt 06)

- [ ] `services/scrape.py` with `ScrapeResult(title, text, site, word_count, meta, hero_candidates[])`
- [ ] Try trafilatura; fallback to readability if failure/too short
- [ ] Gather og:title, twitter:title, site, og:image list
- [ ] `too_short` flag when `word_count < 200`
- [ ] Fixtures: standard blog, JS-ish blog, very short
- [ ] Tests: extraction quality, og:image detection, too_short flag

⛳ **DoD**: Deterministic scraping on fixtures; no network in tests.

---

## 7) Hero Image Selection & Processing (Prompt 07)

- [ ] `services/images.py` — `pick_hero(candidates)` prioritization
- [ ] `validate_and_process(url) -> (bytes, width, height)` using PIL
- [ ] Enforce min width ≥ 800px; downscale to ≤ 1600px; strip EXIF; re-encode JPEG
- [ ] `alt_text_from(title, lede)` ≤ 120 chars
- [ ] Tests with synthetic PIL images: too small rejected; downscale; EXIF stripped; alt length

⛳ **DoD**: Image pipeline tests pass; deterministic output sizes.

---

## 8) JSON Generation Schema & OpenAI Wrapper (Prompt 08)

- [ ] Define strict JSON schemas:
  - [ ] Thread `{tweets: [{text}], style_used, hook_used}`
  - [ ] Single `{text, style_used}`
  - [ ] Reference `{text}`
- [ ] `services/generate.py`: `generate_thread`, `generate_single`
- [ ] Prompt templates (Extractive default; style/hook toggles)
- [ ] Cost estimator (pre/post token approx) and return estimate
- [ ] Fallback to GPT‑4o on long inputs (>2.5k words)
- [ ] Robust JSON parse & retry on malformed output
- [ ] Tests: mock OpenAI valid & malformed JSON; assert style flags and extractive mode

⛳ **DoD**: Generator unit tests pass; no external API calls in CI.

---

## 9) Budget Guardrails (Prompt 09)

- [ ] `services/budget.py` with `within_budget(estimate_usd, cap=0.02)`
- [ ] Integrate into generator path: compress once then `requires_review` if still over
- [ ] Log estimation to `Run`
- [ ] Tests: threshold behavior; integration stub where estimate > cap

⛳ **DoD**: Guardrails behave per spec; tests green.

---

## 10) Poster (OAuth2 PKCE) — Auth Only (Prompt 10A)

- [ ] `security/oauth_x.py`: start (code_verifier/challenge, state) + callback
- [ ] Exchange code → tokens; store encrypted; scopes: tweet.read/users.read/tweet.write/media.write/offline.access
- [ ] Routes under `/oauth/x/*`; prepare to exempt from Basic Auth
- [ ] Tests: httpx client flow with mocked X endpoints (start → callback → stored Account)

⛳ **DoD**: OAuth flow passes in tests; tokens sealed at rest.

---

## 11) Posting Core (thread/single, pacing) (Prompt 11B)

- [ ] `services/post_x.py`: `post_single`, `post_thread`
- [ ] Resume mid-thread using stored `posted_tweet_id`
- [ ] Reference reply not counted in T (posted later)
- [ ] Rate-limit aware retries (up to 3); respect response headers
- [ ] Inject sleeper for tests (no real sleep)
- [ ] Tests: mock X API post + media upload; mid-thread failure → resume; second failure → `requires_review`

⛳ **DoD**: Posting integration tests pass with mocks; pacing logic unit-tested.

---

## 12) Duplicate Detection & Canonical Integration (Prompt 12)

- [ ] On submission, canonicalize URL
- [ ] If completed/approved run exists for same account+canonical, block unless `force`
- [ ] In Review UI, warn but allow override
- [ ] Tests: auto-post duplicate blocked; review allowed; `force` overrides

⛳ **DoD**: Duplicate rules enforced; tests pass; submission wiring complete.

---

## 13) Web: Form + Review UI (HTMX/Jinja) (Prompt 13)

- [ ] Routes:
  - [ ] `GET /` — form (URL, account, mode=review default, type, style, hook, reference toggle, image toggle, caps)
  - [ ] `POST /submit` — create Run; redirect to Review when too_short/over_budget
  - [ ] `GET /review/{run_id}` — editable tweets/post, hero toggle/alt, reference toggle + UTM, regenerate
- [ ] HTMX actions: inline edit + length check; regenerate whole
- [ ] Basic `/history` page
- [ ] Tests: template rendering; edit→save; regenerate creates new version; length-check endpoint valid/invalid

⛳ **DoD**: UI tests pass; manual smoke possible locally.

---

## 14) CLI (Typer) + API Token Auth (Prompt 14)

- [ ] `threadify <URL> [flags]` default `--review`
- [ ] Config at `~/.threadify/config.json` with API token
- [ ] Backend enforces token on CLI endpoints
- [ ] CLI prints Review URL or final links
- [ ] Tests: flag parsing; config handling; mock HTTP; integration against test FastAPI app

⛳ **DoD**: CLI tests green; happy/failure paths covered.

---

## 15) Reference Reply + UTM Builder (Prompt 15)

- [ ] Build `utm_source=twitter&utm_medium=social&utm_campaign=<value>` for canonical URL
- [ ] Post as unnumbered reply after thread (when enabled)
- [ ] Store as `role='reference'` in `tweets` table
- [ ] Tests: UTM builder unit; integration ensures reference posts last and persists IDs

⛳ **DoD**: Reference reply appears after thread; DB row persisted.

---

## 16) Jobs & Concurrency Caps (Prompt 16)

- [ ] In-process FIFO per-account; global cap = 3
- [ ] Job kinds: submit, review-approve, resume-thread
- [ ] Use `asyncio.Semaphore` + per-account map
- [ ] Tests: deterministic scheduling; ensure 1/account, 3 global

⛳ **DoD**: Concurrency tests pass consistently.

---

## 17) Observability & /history Details (Prompt 17)

- [ ] Structured logs (request IDs, model usage, X post IDs)
- [ ] `/history` table shows time, URL, account, status, tweet links/IDs, tokens used, approx cost
- [ ] Tests: render history; cost/token columns shown; log fields present in sample flow

⛳ **DoD**: History page useful for audits; tests pass.

---

## 18) Security: Caddy Basic Auth (exclude `/oauth/*`) (Prompt 18)

- [ ] `deploy/Caddyfile` for `social.capturia.ca`
- [ ] `@oauth path /oauth/*` allow; `basicauth` for others (bcrypt hash configurable)
- [ ] Reverse proxy to FastAPI; TLS via Cloudflared/HTTPS
- [ ] Doc: script snippet to generate bcrypt hash
- [ ] Backend also enforces API token for CLI endpoints
- [ ] Doc test: validate config snippets in README

⛳ **DoD**: Config documented; manual sanity steps included.

---

## 19) Purge Job — 03:30 America/Toronto (Prompt 19)

- [ ] `db/purge.py` scheduled daily (APScheduler or loop)
- [ ] Delete article text & outputs > 30 days; keep minimal audit fields
- [ ] Tests: freeze time; old/new records; run purge; assert deletions only on old

⛳ **DoD**: Purge behaves as expected in tests; cron spec documented.

---

## 20) Docker Compose & Watchtower (Prompt 20)

- [ ] Dockerfiles: API, Node, Caddy
- [ ] docker-compose with volumes for DB, Caddy, `.env`
- [ ] Healthchecks and `depends_on` ordering
- [ ] README: `docker-compose build`/`up` instructions; Cloudflared steps
- [ ] (Optional) Watchtower service for updates

⛳ **DoD**: Local `compose up` instructions validated (manually) and documented.

---

## 21) Acceptance Test Suite (Prompt 21)

- [ ] Convert Acceptance Checklist items to pytest markers
- [ ] End-to-end happy path: submit URL → Review → approve → mock post → history shows IDs + costs
- [ ] `pytest -m acceptance` target documented

⛳ **DoD**: Acceptance suite passes locally with mocks.

---

## 22) Repo Hygiene & Nice‑to‑Haves (Backlog)

- [ ] Add code coverage badge & CI artifacts upload (coverage.xml)
- [ ] Add `make`/`just` commands for common tasks
- [ ] Pre-commit hook to run ruff/black/mypy/pytest -q on staged areas
- [ ] Devcontainer or Nix flake for reproducible dev
- [ ] Load testing stub for posting (rate-limit safe using mocks)
- [ ] Add `/privacy.html` & `/terms.html` templates with minimal content
- [ ] Add `/history` filters (account, date range)

---

## Quick Daily Checklist (scratchpad)

- [ ] Pull latest `main`; run all tests locally
- [ ] Tackle the next milestone step(s)
- [ ] Update README or docs if behavior changes
- [ ] Open PR with passing CI; request review
- [ ] Tag & note any follow-up tasks into backlog above
