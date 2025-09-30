# Threadify — Build Blueprint & TDD Prompt Pack

## A) System Blueprint (concise, actionable)

### Architecture (MVP)

* **FastAPI app** (Python 3.11+): REST + server-rendered UI (Jinja2 + HTMX)
* **CLI**: Typer (talks to FastAPI via HTTPS + API token)
* **Node microservice**: exposes `/length/check` using `twitter-text` for official tweet length rules
* **SQLite** storage + AES-GCM encryption for sensitive fields
* **OpenAI client**: GPT-4o-mini primary; GPT-4o fallback; strict JSON
* **X (Twitter) OAuth2 PKCE** + posting via v2 endpoints
* **Caddy** reverse proxy + Basic Auth (exclude `/oauth/*`)
* **Cloudflared** tunnel; HTTPS
* **Docker** for all services; Watchtower for updates

### Minimal repo layout

```
threadify/
  backend/
    app/
      __init__.py
      main.py
      config.py
      deps.py
      logging.py
      security/
        crypto.py          # AES-GCM, token sealing
        auth.py            # Basic Auth, CSRF helpers
        oauth_x.py         # OAuth2 PKCE dance
      db/
        base.py            # SQLAlchemy engine/session
        models.py
        schema.py          # Pydantic schemas
        migrations/        # Alembic (even for SQLite)
        purge.py
      services/
        canonicalize.py
        scrape.py
        images.py
        generate.py
        post_x.py
        budget.py
        jobs.py
      web/
        routes.py
        forms.py
        templates/ (jinja)
          base.html
          index.html
          review.html
          history.html
          privacy.html
          terms.html
        static/
    tests/                 # pytest (unit/integration)
      conftest.py
      e2e/
  node-helpers/
    length-service/
      package.json
      src/index.ts
      test/index.test.ts
  cli/
    threadify_cli/
      __init__.py
      app.py
    tests/
  deploy/
    Dockerfile.api
    Dockerfile.node
    Dockerfile.caddy
    Caddyfile
    docker-compose.yml
    env.example
  .github/workflows/ci.yml
  README.md
```

### Key domain objects

* `Account`, `Run`, `Tweet`, `Image`, `Settings`, `ApiToken`
* `RunStatus`: `submitted|review|approved|posting|failed|completed`
* `RunType`: `thread|single`
* `Role`: `content|reference`

### Testing strategy

* **Unit**: pure functions (canonicalizer, budget calc, split/fit tweets, AES-GCM)
* **Component**: scrape pipeline (trafilatura → readability), generator (mock OpenAI)
* **Integration**: FastAPI endpoints (httpx + sqlite tmp DB), OAuth callback flow (mock X)
* **Contract**: Node length service (`supertest`) and Python client
* **Property tests**: tweet fit and numbering invariants
* **E2E (local)**: docker-compose up → post to mock X (custom stub) → assert history entries
* **Scheduled task test**: purge at 03:30 America/Toronto (simulated clock)

---

## B) Iterative Plan → Chunks → Fine-Grained Steps

### Milestones (right-sized)

1. **Scaffold & CI** → repo, tooling, tests run green
2. **DB & Models** → schema, migrations, fixtures
3. **Node Length Service** → official length checks + client
4. **Canonicalizer** → redirects, params, canonical tag
5. **Scraper** → trafilatura + readability fallback
6. **Hero Image** → choose, validate, downscale, alt text
7. **Generator** → JSON schema output + cost estimator
8. **Budget Guardrails** → soft cap + compress/retry
9. **Poster** → OAuth2 PKCE, pacing, resume, reference reply
10. **Review UI** → HTMX edit/regenerate/toggles
11. **CLI** → Typer flags + HTTPS auth
12. **History & Observability** → logs + /history
13. **Security & Purge** → AES-GCM, basicauth, scheduler
14. **Docker & Caddy** → compose + deploy path
15. **Acceptance suite** → end-to-end checks

#### Example of “chunk” → “smaller steps” (Milestone 5: Scraper)

* 5.1: Add `ScrapeResult` schema (title, text, meta, hero candidates) + empty impl
* 5.2: Implement trafilatura extractor; unit tests on 3 fixtures
* 5.3: Add readability fallback; tests for short/JS pages
* 5.4: Heuristics for “too short” (<200w) → route to Review; tests
* 5.5: Metadata harvest (og:title, site, og:image); tests

> All milestones below are further decomposed inside the prompt pack.

---

## C) Right-Sizing Review

* Each milestone ends in a demonstrable UX/API surface or library with tests.
* No leap that introduces >2 novel systems at once; where that would happen, steps split (e.g., Poster: auth first, then pacing, then resume, then reference).
* Early steps (1–4) keep blast radius low (no external APIs).
* Mock external APIs consistently (OpenAI, X).
* Every step integrates—no orphan code. CI runs from step 1 onward.

---

## D) TDD Prompt Pack (feed these to a code-gen LLM)

Each prompt is standalone, incremental, test-first, and references files to create/modify. Run them **in order**.

### Prompt 01 — Repo scaffold, tooling, CI ✅ COMPLETED

```text
You are implementing Prompt 01 for the Threadify MVP.

Goal:
- Create a Python FastAPI backend skeleton, a Typer CLI skeleton, a Node length-service skeleton, and CI.

Scope:
1) Initialize repo with Poetry (Python 3.11+) and pnpm for Node subproject.
2) Add FastAPI app with a single health endpoint `GET /healthz` returning `{"ok": true}`.
3) Add pytest + coverage, ruff + black, mypy config; pre-commit hooks.
4) Add GitHub Actions CI to run lint, mypy, pytest for Python and `pnpm test` for Node.
5) Add docker-compose.yml with empty services (placeholders) + .env.example.
6) Document how to run tests locally in README.

Files to create/update:
- backend/app/main.py, backend/tests/test_health.py
- pyproject.toml, mypy.ini, .pre-commit-config.yaml, .ruff.toml
- node-helpers/length-service/package.json (pnpm), src/index.ts (placeholder), test/index.test.ts
- .github/workflows/ci.yml
- deploy/docker-compose.yml, deploy/env.example
- README.md

Tests first:
- Write `backend/tests/test_health.py` asserting 200/`{"ok": true}`.
- Write `node-helpers/length-service/test/index.test.ts` with a trivial placeholder test.

Acceptance:
- `pytest -q` passes. ✅
- `pnpm -C node-helpers/length-service test` passes. ✅
- CI workflow green on push. ✅
```

### Prompt 02 — DB engine, base models, migrations ✅ COMPLETED

```text
Implement Prompt 02: SQLAlchemy and Alembic setup.

Goal:
- SQLite database, session management, migrations, and initial models.

Scope:
1) Add SQLAlchemy engine/session factory (backend/app/db/base.py).
2) Define models in backend/app/db/models.py:
   - Account, Run, Tweet, Image, Settings, ApiToken (per spec), with enums via strings.
3) Add Alembic, generate migration for initial schema.
4) Add Pydantic schemas in backend/app/db/schema.py mirroring models without secrets.
5) Add minimal DAO helpers (create/read) for Account, Run, Tweet.

Tests first:
- backend/tests/test_db_models.py: create tables in tmp sqlite, roundtrip create/get for each model.
- backend/tests/test_migrations.py: run alembic upgrade head against fresh DB.

Acceptance:
- All tests pass; alembic revision created; `poetry run alembic upgrade head` works. ✅
```

### Prompt 03 — AES-GCM crypto for secrets ✅ COMPLETED

```text
Implement Prompt 03: AES-GCM utilities for sealing tokens at rest.

Scope:
1) backend/app/security/crypto.py:
   - `seal(plaintext: bytes, key: bytes) -> str` (base64url) and `unseal(token: str, key: bytes) -> bytes`.
   - Nonce generation 12B; include version prefix "v1:".
2) Integrate with models: add hybrid properties on Account for `token_encrypted` etc.
3) Config wiring: backend/app/config.py loads AES key from env.

Tests first:
- backend/tests/test_crypto.py: seal/unseal roundtrip, tamper detection, wrong key failure.
- backend/tests/test_account_secrets.py: setting token stores ciphertext; reading returns original via helper.

Acceptance:
- 100% coverage on crypto module; tests pass. ✅
```

### Prompt 04 — Node length service (twitter-text) + Python client ✅ COMPLETED

```text
Implement Prompt 04: Official tweet length checks.

Scope:
1) Node service:
   - Express server `/length/check` POST {text} -> {isValid, weightedLength, permillage, validRange}.
   - Use `twitter-text` to compute; reject >280 chars by rule.
2) Add supertest tests for boundary cases: 280 ok, 281 fail, URL weighting, emoji.
3) Python client:
   - backend/app/services/length_client.py: `check_text(text) -> dataclass`.
   - Config for LENGTH_SERVICE_URL.
4) Contract test: spin up ephemeral node server (or mock) and assert client mapping.

Acceptance:
- `pnpm test` passing with meaningful cases. ✅
- Python unit tests for client pass; failure mode handled (service down -> raises). ✅
```

### Prompt 05 — Canonicalizer ✅ COMPLETED

```text
Implement Prompt 05: URL canonicalizer.

Scope:
- backend/app/services/canonicalize.py with `canonicalize(url: str, http_get: callable) -> str`
  Rules:
  * Follow redirects to final https. ✅
  * Lowercase host; strip `www`. ✅
  * Remove trailing slash, fragments. ✅
  * Drop tracking params: utm_*, gclid, fbclid, ref. ✅
  * If page has `<link rel="canonical">`, prefer it if same registrable domain.
- Provide pure function core; inject `http_get` for HTTP. ✅
- Add domain/URL parsing edge cases. ✅

Tests first:
- backend/tests/test_canonicalize.py with fixtures: ✅
  * redirects, canonical tag present/absent, params stripped, fragment removal. ✅

Acceptance:
- All tests pass; function is pure & deterministic given mocked HTTP. ✅
```

### Prompt 06 — Scraper (trafilatura → readability fallback) ✅ COMPLETED

```text
Implement Prompt 06: Content scraping.

Scope:
1) backend/app/services/scrape.py:
   - `ScrapeResult(title, text, site, word_count, meta, hero_candidates[])` ✅
   - Try trafilatura; if < threshold or failure, use readability. ✅
   - Collect og:title, twitter:title, site name, og:image list. ✅
   - If `word_count < 200`, tag `too_short=True`. ✅
2) Embed robust charset and JS-heavy handling.

Tests first:
- backend/tests/test_scrape.py using local HTML fixtures for: ✅
  * standard blog, JS-ish blog, very short page. ✅
- Assert title/text extraction quality, og:image detection, too_short flag. ✅

Acceptance:
- Deterministic scraping on fixtures; no network needed in tests. ✅
```

### Prompt 07 — Hero image selection & processing ✅ COMPLETED

```text
Implement Prompt 07: Hero image pipeline.

Scope:
1) backend/app/services/images.py:
   - `pick_hero(candidates) -> Optional[Hero]` (choose og:image → twitter:image → largest in-article). ✅
   - `validate_and_process(url) -> (bytes,jpeg_width,height)`: ✅
       * Ensure width >= 800px (reject smaller). ✅
       * Downscale to <=1600px width, strip EXIF, re-encode JPEG. ✅
   - `alt_text_from(title, lede) <= 120 chars`. ✅
2) Save transiently; no persistent cache in MVP.

Tests first:
- Use PIL-generated images in tests. ✅
- Cases: too small rejected; large downscaled; EXIF stripped; alt text length. ✅

Acceptance:
- Unit tests pass; deterministic outputs (size, exif stripped). ✅
```

### Prompt 08 — JSON generation schema & OpenAI wrapper

```text
Implement Prompt 08: Generator wrapper.

Scope:
1) Define strict JSON schema for outputs for:
   - Thread: `{tweets: [{text}], style_used, hook_used}`
   - Single: `{text, style_used}`
   - Reference: `{text}`
2) backend/app/services/generate.py:
   - `generate_thread(scrape_result, settings) -> GeneratedThread`
   - `generate_single(scrape_result, settings) -> GeneratedPost`
   - Implement prompt templates per spec (Extractive default, styles, hook toggle).
   - Cost estimator: approximate tokens pre/post; return estimate.
   - Fallback to GPT-4o on length >2.5k words.
   - Robust JSON parse with retry if invalid.

Tests first:
- Mock OpenAI client to return fixture JSON and malformed JSON (retry path).
- Assert style flags and extractive mode behaviors.

Acceptance:
- Unit tests pass; no external API calls in CI.
```

### Prompt 09 — Budget guardrails

```text
Implement Prompt 09: Budget checks.

Scope:
- backend/app/services/budget.py:
  - `within_budget(estimate_usd, cap_usd=0.02) -> bool`
  - Retry strategy: compress prompt once; else return "requires_review".
- Integrate into generator service path.
- Log cost estimations to Run.

Tests first:
- Unit tests for thresholds; integration test stubbing generator estimate > cap.

Acceptance:
- Behavior matches spec; tests pass.
```

### Prompt 10 — Poster (OAuth2 PKCE) — auth only

```text
Implement Prompt 10A: X OAuth2 PKCE.

Scope:
- backend/app/security/oauth_x.py:
  - Start: generate code_verifier/challenge, state; redirect URL.
  - Callback: exchange code -> tokens; store encrypted.
  - Scopes: tweet.read, users.read, tweet.write, media.write, offline.access.
- Routes under `/oauth/x/*`; exempt from Basic Auth later.

Tests first:
- Mock HTTP to X endpoints; end-to-end route tests with httpx test client: start → callback stores Account with tokens.

Acceptance:
- OAuth flow passes with mocks; tokens encrypted at rest.
```

### Prompt 11 — Poster (tweet/thread posting, pacing)

```text
Implement Prompt 11B: Posting core.

Scope:
1) backend/app/services/post_x.py:
   - `post_single(text, media=None)` and `post_thread(texts[], media_first=None, delay_jitter=3±0.5s)`.
   - Resume from last success (store posted_tweet_id).
   - Reference reply not counted in T.
2) Rate-limit & retry (up to 3); respect headers.

Tests first:
- Mock X API (post tweet, media upload).
- Simulate mid-thread failure → resume once; second failure → return "requires_review".

Acceptance:
- Posting integration tests pass with mocks; pacing logic unit-tested (without sleeping; inject sleeper).
```

### Prompt 12 — Duplicate detection & canonical integration

```text
Implement Prompt 12: Duplicate rules.

Scope:
- On submission, canonicalize URL; if a completed/approved Run exists for same account+canonical, block unless `force`.
- In Review, warn but allow.

Tests first:
- Unit test scenarios: auto-post duplicate blocked; review allowed; force overrides.

Acceptance:
- Tests pass; wiring into submission endpoint is complete.
```

### Prompt 13 — Web: form + Review UI (HTMX/Jinja)

```text
Implement Prompt 13: Server-rendered UI.

Scope:
1) Routes:
   - GET `/` form (URL, account, mode=review default, type, style, hook, reference, image toggles, caps).
   - POST `/submit` creates Run; if too_short or over_budget, redirect to Review.
   - GET `/review/{run_id}` shows editable tweets/post, hero toggle/alt, reference toggle+UTM, regenerate button.
2) HTMX actions:
   - Inline edit tweet text → length check via Node service.
   - Regenerate whole with same settings.
3) Basic History page `/history`.

Tests first:
- Template rendering tests.
- Review actions: edit → save; regenerate sets new version; length check endpoint returns valid/invalid.

Acceptance:
- All UI tests pass with httpx test client.
```

### Prompt 14 — CLI (Typer) + API token auth

```text
Implement Prompt 14: CLI command.

Scope:
- `threadify <URL> [flags]` per spec; default `--review`.
- Settings stored in `~/.threadify/config.json` (API token).
- Calls backend HTTPS; prints review URL or final links.

Tests first:
- Unit tests for flag parsing; mock HTTP; config file handling.
- Integration against test FastAPI app (token auth required).

Acceptance:
- `pytest` for CLI passes; happy path + failure modes handled.
```

### Prompt 15 — Reference reply + UTM builder

```text
Implement Prompt 15: Reference logic.

Scope:
- Build `utm_source=twitter&utm_medium=social&utm_campaign=<value>` appended to canonical URL for the reference reply.
- Post as unnumbered reply to last tweet when enabled.
- Store as `role='reference'` in `tweets` table.

Tests first:
- Unit test UTM builder; integration test that ensures reference tweet posted after thread.

Acceptance:
- Tests pass; DB row persisted; permalinks stored.
```

### Prompt 16 — Jobs & concurrency caps

```text
Implement Prompt 16: In-process job queue.

Scope:
- FIFO per-account; global cap 3.
- Job kinds: submit, review-approve, resume-thread.
- Locking with `asyncio.Semaphore` + per-account map.

Tests first:
- Concurrency tests with async jobs: ensure 1/account, 3 global.

Acceptance:
- Deterministic scheduling tests pass.
```

### Prompt 17 — Observability & /history details

```text
Implement Prompt 17: Logs + history.

Scope:
- Structured logs (request IDs, model usage, X post IDs).
- `/history` table shows time, URL, account, status, tweet links/IDs, tokens used, approx cost.

Tests first:
- Render tests for history; ensure cost/token columns show.

Acceptance:
- Tests pass; log fields present in sample requests.
```

### Prompt 18 — Security: Caddy Basic Auth (exclude `/oauth/*`)

```text
Implement Prompt 18: Reverse proxy and auth.

Scope:
- Add `deploy/Caddyfile` with:
  * vhost `social.capturia.ca`
  * `@oauth path /oauth/*` allow
  * `basicauth` for others (bcrypt hash configurable)
  * reverse_proxy to FastAPI
- Provide script snippet to create bcrypt hash (doc only).
- FastAPI should also enforce API token for CLI endpoints.

Tests:
- Config is static; add README validation and a simple integration doc test.

Acceptance:
- Manual sanity commands included; not runtime-tested in CI.
```

### Prompt 19 — Purge job (03:30 America/Toronto)

```text
Implement Prompt 19: Retention purge.

Scope:
- backend/app/db/purge.py scheduled daily via APScheduler or custom loop.
- Delete cleaned article text & outputs older than 30 days; keep minimal audit fields.

Tests first:
- Freeze time; create old/new records; run purge; assert deletions.

Acceptance:
- Tests pass; cron spec documented.
```

### Prompt 20 — Docker compose & Watchtower

```text
Implement Prompt 20: Containerization.

Scope:
- Dockerfiles for api, node, caddy; docker-compose with volumes for DB, Caddy, .env.
- Healthchecks; depends_on order.
- README deploy steps with Cloudflared.

Acceptance:
- `docker-compose build` and `docker-compose up` instructions validated in README (no CI run).
```

### Prompt 21 — Acceptance test suite

```text
Implement Prompt 21: Spec-to-tests.

Scope:
- Convert Acceptance Checklist items to pytest markers.
- Add a single “happy path” integration: submit URL → Review → approve → mock post → history shows IDs + costs.

Acceptance:
- `pytest -m acceptance` passes locally with mocks.
```

---

## E) Final TDD Prompts (continuous, integrated)

> Below is the **complete** prompt series—including the ones above—ready to paste step by step. They are intentionally small, test-led, and fully integrated.

#### 01 — Scaffold & CI

```text
[Prompt 01 — Scaffold & CI]
(…same content as Prompt 01 above…)
```

#### 02 — DB & Migrations

```text
[Prompt 02 — DB & Migrations]
(…same content as Prompt 02 above…)
```

#### 03 — AES-GCM Crypto

```text
[Prompt 03 — AES-GCM crypto for secrets]
(…same content as Prompt 03 above…)
```

#### 04 — Node Length Service + Client

```text
[Prompt 04 — Node length service + Python client]
(…same content as Prompt 04 above…)
```

#### 05 — Canonicalizer

```text
[Prompt 05 — Canonicalizer]
(…same content as Prompt 05 above…)
```

#### 06 — Scraper

```text
[Prompt 06 — Scraper (trafilatura → readability)]
(…same content as Prompt 06 above…)
```

#### 07 — Hero Image

```text
[Prompt 07 — Hero image selection & processing]
(…same content as Prompt 07 above…)
```

#### 08 — Generator

```text
[Prompt 08 — JSON generation & OpenAI wrapper]
(…same content as Prompt 08 above…)
```

#### 09 — Budget Guardrails

```text
[Prompt 09 — Budget guardrails]
(…same content as Prompt 09 above…)
```

#### 10 — OAuth2 PKCE

```text
[Prompt 10 — Poster auth (OAuth2 PKCE)]
(…same content as Prompt 10 above…)
```

#### 11 — Posting Core

```text
[Prompt 11 — Posting (thread/single), pacing, resume]
(…same content as Prompt 11 above…)
```

#### 12 — Duplicate Detection

```text
[Prompt 12 — Duplicate detection + canonical integration]
(…same content as Prompt 12 above…)
```

#### 13 — Web UI + Review

```text
[Prompt 13 — Web form + Review UI (HTMX/Jinja)]
(…same content as Prompt 13 above…)
```

#### 14 — CLI

```text
[Prompt 14 — CLI (Typer) + API token auth]
(…same content as Prompt 14 above…)
```

#### 15 — Reference Reply + UTM

```text
[Prompt 15 — Reference reply + UTM builder]
(…same content as Prompt 15 above…)
```

#### 16 — Jobs & Concurrency

```text
[Prompt 16 — Jobs & concurrency caps]
(…same content as Prompt 16 above…)
```

#### 17 — Observability & History

```text
[Prompt 17 — Observability & /history]
(…same content as Prompt 17 above…)
```

#### 18 — Caddy Auth

```text
[Prompt 18 — Caddy Basic Auth + reverse proxy]
(…same content as Prompt 18 above…)
```

#### 19 — Purge Scheduler

```text
[Prompt 19 — Daily purge at 03:30 America/Toronto]
(…same content as Prompt 19 above…)
```

#### 20 — Docker & Deploy

```text
[Prompt 20 — Docker compose & Watchtower]
(…same content as Prompt 20 above…)
```

#### 21 — Acceptance Suite

```text
[Prompt 21 — Acceptance tests from checklist]
(…same content as Prompt 21 above…)
```

---

## F) Notes on Best Practices Embedded

* **Test-first** at every step; mocks for X/OpenAI keep CI hermetic.
* **Strict JSON** from LLM + retries prevent flaky outputs.
* **Isolation boundaries** (canonicalize/scrape/generate/post) enable independent iteration.
* **Security**: secrets sealed at rest; Basic Auth front door; API tokens for CLI; CSRF + PKCE on OAuth.
* **Ops**: structured logs + history page give immediate observability; purge job enforces retention.

If you want, I can drop these prompts into a printable **spec.md + prompts.md** pair, or merge them into your repo’s `/docs/` folder.
