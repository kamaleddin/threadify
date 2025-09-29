Awesome—since you said “use best practice for the rest,” I’ve consolidated everything we decided into a **hand-offable MVP spec** for **Threadify**. It’s tight but complete so a dev can build it.

# Threadify — MVP Functional Spec

## 1) Goal

Turn any **public blog URL** into either a **tweet thread** or a **single long post** on X, with optional reference attribution as a reply. Support **CLI** and **web form**, plus a minimal **Review** UI.

---

## 2) Core Requirements & Defaults

* **Submission sources:** Manual URL (publicly accessible).
* **Modes:**

  * **Thread** (default): numbered `1/T … T/T` (no dash), **280-char cap per tweet** using official length rules; tiny paced delay (~3s ±0.5s).
  * **Single long post:** default cap **~1,400 chars**, optional **Longform up to 25,000** (explicit toggle).
* **Reference (attribution):** **ON by default**. Posted as **unnumbered reply** to the last tweet; URL with UTM (see below).
* **Language:** **English only**.
* **Hook:** **ON by default** for threads (toggle available).
* **Style profiles (choose one; default = Punchy Explainer):**

  1. Neutral Summarizer
  2. Punchy Explainer (default)
  3. Expert Analyst
  4. Data-Driven Pragmatist
  5. Narrative Threader
* **Summary mode default:** **Extractive** (toggle to “Light commentary”).
* **Hashtags:** none. **Emojis:** allowed.
* **Link placement:** Only in **Reference reply** when enabled; otherwise none.

---

## 3) Posting Targets & Auth

* **Multiple X accounts** supported; **preselect last-used account** in forms.
* **OAuth 2 + PKCE** with scopes: `tweet.read`, `users.read`, `tweet.write`, `media.write`, `offline.access`.
* **Redirect URI:** `https://social.capturia.ca/oauth/x/callback`
* **Token storage:** saved for reuse; refresh handled automatically.

---

## 4) UX Surfaces

### 4.1 Web Form (server-rendered: FastAPI + Jinja2/HTMX)

**Front-and-center:**

* URL, Target account, Post mode (**default Review**), Output type (Thread vs Single), Style profile (default Punchy), Summary mode (Extractive vs Commentary).

**Advanced:**

* Thread cap (**default 12**, hard 20), Single-post cap (**1,400**; Longform toggle), Include Reference (default ON) + UTM campaign value, Hero image ON/OFF (default ON), Hook ON/OFF (default ON).

**Review UI (MVP actions):**

1. Inline edit text per tweet
2. Regenerate whole thread/post (same settings)
3. Toggle hero image on/off + edit alt text
4. Toggle “Reference” ON/OFF + set UTM campaign

**History page `/history`:** time, URL, account, status, tweet links/IDs, tokens used, **approx cost**.

**Privacy & Terms:** static `/privacy`, `/terms` with contact `support@capturia.ca`.

**Access control:** **Caddy Basic Auth** (`kamaleddin` + bcrypt hash). **Exclude `/oauth/*`** paths from auth.

### 4.2 CLI (Typer)

Single command with flags (preapproved):

```
threadify <URL>
  --account "@handle"
  --auto | --review                  # default: --review
  --type thread | single             # default: thread
  --style neutral|punchy|expert|data|narrative   # default: punchy
  --summary extractive|commentary    # default: extractive
  --hook | --no-hook                 # default: --hook
  --reference | --no-reference       # default: --reference
  --utm-campaign "<value>"           # default: "threadify"
  --image | --no-image               # default: --image
  --thread-cap <int>                 # default: 12 (hard 20)
  --single-cap <int>                 # default: 1400
  --longform                         # enable up to 25k in single mode
  --force                            # bypass duplicate detector (auto-post only)
  --budget "$0.02"                   # soft cap override; default $0.02
```

**CLI Auth:** Bearer **API token** (generated on Settings page), stored in `~/.threadify/config.json`. CLI calls the FastAPI backend over HTTPS.

---

## 5) Content Pipeline

### 5.1 Scraping (Hybrid, best practice)

1. **Trafilatura** (title/body/metadata/hero) →
2. Fallback **Readability** →
3. If text < **200 words**, **convert to Review**; else proceed.
4. Hero image selection:

   * `og:image` → `twitter:image` → largest in-article
   * Require width ≥ **800px**; downscale to ≤1600px, re-encode JPEG, strip EXIF.
   * **Alt text** from title/lede (≤120 chars), editable.

### 5.2 Generation (OpenAI)

* **Default model:** **GPT-4o-mini**, **temp 0.35** (concise).
* **Fallback:** **GPT-4o** (long/tricky pages, auto-trigger).
* **Two-step for long articles (>2,500 words):** Outline → Draft (internal; not shown in UI).
* **Strict JSON output** (approved schema).
* **Per-tweet fit:** number prefix computed `i/T `; official length check via Node **twitter-text** helper; **auto-rewrite to fit** if over.

### 5.3 Cost/Budget guardrail

* **Soft cap = $0.02/run** (estimate before/after). If over: compress & retry once; if still over → **convert to Review**. (Override via `--budget`.)

---

## 6) Posting Logic & Reliability

* **Auto-post default:** immediate (no scheduling in MVP).
* **Thread pacing:** ~**3s jittered delay** between tweets.
* **Mid-thread failure:** **resume once** from last successful; on second failure → **convert to Review** with “Continue thread”.
* **Duplicate detection** (canonical URL + account):

  * **Auto-post:** abort unless `--force`.
  * **Review:** warn; allow override.
* **Canonicalization rules:** follow redirects; https; lowercase host; drop `www`; strip trailing slash/fragments; remove tracking params (`utm_*`, `gclid`, `fbclid`, `ref`, etc.); respect `<link rel="canonical">`; keep no query params by default.
* **Reference tweet** (if ON): separate short reply with template:
  `Reference: “{title}” by {site}. Full post: {url_with_utm}`
  **Not counted** in `T`.

**UTM:** always append when Reference is ON:
`utm_source=twitter&utm_medium=social&utm_campaign=<value>`; default campaign = **threadify**; **no custom shortener** (t.co only).

---

## 7) Queueing & Concurrency

* **Per-account:** **1 job at a time** (FIFO).
* **Global cap:** **3 concurrent jobs**.
* **Job types:** submit, review-approve, resume-thread.
* **In-process queue** within FastAPI app (MVP).

---

## 8) Data Retention & Storage

* **SQLite** (file volume). **Unencrypted DB**, but **encrypt sensitive fields** (X tokens) with AES-GCM using key from `.env`.
* **Retention:** **30 days** for cleaned article text and generated outputs; daily purge **03:30 America/Toronto**.

**Tables (high-level):**

* `accounts(id, handle, provider='x', created_at, updated_at, token_encrypted, refresh_encrypted, scopes)`
* `runs(id, submitted_at, account_id, url, canonical_url, mode, type, settings_json, status, cost_estimate, tokens_in, tokens_out)`
* `tweets(run_id, idx, role='content|reference', text, media_alt, posted_tweet_id, permalink)`
* `images(run_id, source_url, width, height, used BOOLEAN)`
* `settings(id, defaults_json)`
* `api_tokens(id, label, token_hash, created_at, revoked_at)`

---

## 9) Security & Access

* **Caddy Basic Auth** for web UI; **exclude `/oauth/*`** from auth.
* **Best practice for password hash:** setup script runs `caddy hash-password` on the server and injects bcrypt hash into Caddyfile (no plaintext stored).
* **Secrets:** `.env` for MVP (OpenAI key, X client id/secret, AES key, Cloudflared token).
* **HTTPS via Cloudflare Tunnel** to `social.capturia.ca`.
* **CSRF & PKCE** for OAuth; `state` validated on callback.

---

## 10) Observability

* **Minimal structured logs** (request IDs, errors, model usage, X post IDs).
* **/history** page as specified (with tokens & cost).
* **Retry policy (locked):**

  * Scrape: 1 retry then model-assisted extraction.
  * OpenAI: up to 2 retries (exp backoff).
  * X API: up to 3 retries; honor rate-limit headers; then convert to Review.

---

## 11) Deployment

* **Docker** (recommended): FastAPI app + tiny Node `twitter-text` helper + Caddy + Cloudflared.
* **CI/CD:** GitHub Actions builds private image → push to GHCR on `main`; **Watchtower** auto-pulls & restarts.
* **Volumes:** SQLite DB, Caddy config, `.env`.
* **No media caching** (download → upload to X → discard immediately).

**Caddyfile (essentials):**

* Virtual host `social.capturia.ca`
* `@oauth path /oauth/x/callback` (no auth)
* `basicauth` for all else (bcrypt hash)
* Reverse proxy to FastAPI app.

---

## 12) Backlog (post-MVP)

* Telegram review channel delivery; scheduling posts; batch URLs; per-account hourly caps; SPA UI; Redis queue; SQLCipher; domain allow/block lists; style profile editor; per-tweet regenerate/split/merge/reorder; language auto-detect; custom link shortener; email/Telegram alerts; metrics `/metrics`.

---

## 13) Acceptance Checklist

* [ ] OAuth connect flow works; account selectable.
* [ ] CLI + web form both submit and respect defaults/settings.
* [ ] Scraper → generator → poster runs within budget guardrail; duplicate rules enforced.
* [ ] Thread numbering correct; official length checks pass; no overflow.
* [ ] Reference reply posted (when ON) with UTM.
* [ ] Hero image attached when quality allows; alt text editable.
* [ ] Review mode can edit inline, toggle image/reference, and regenerate whole.
* [ ] History lists IDs, permalinks, tokens, cost.
* [ ] 30-day purge runs at 03:30 America/Toronto.
