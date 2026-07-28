# AdScope

AdScope is a small internal marketing tool. A user pastes a client campaign briefing in plain
text, and AdScope asks several AI models the same question, then merges their answers into one
ranked list of websites and digital publishers where the client could consider advertising.

The value is in the **consensus**: when three independent models all recommend the same publisher,
that is a stronger signal than any single model's opinion. AdScope makes that agreement visible
instead of hiding it behind one answer.

> **AdScope is an advisory tool.** AI-generated recommendations are a starting point for a media
> plan, not a decision. Website suitability, audience information, pricing, availability, and brand
> safety must be verified by an authorised marketing professional before campaign execution.

---

## Main features

- **Multi-model analysis** — sends the same briefing to Gemini, Groq, and OpenRouter concurrently.
- **Deterministic consensus** — merges results in Python by normalized domain. No LLM is asked to
  score the final list, so the ranking is reproducible and auditable.
- **Agreement levels** — every publisher shows how many models recommended it.
- **Per-model drill-down** — a modal on each row shows each model's individual scores, reasoning,
  concerns, and confidence.
- **Resilient to provider failure** — a provider that times out, rejects the key, or returns
  unparseable JSON is marked failed; the campaign still completes with the remaining models.
- **CSV export** of the final ranked list.
- **Demo mode** — the full workflow runs with no API keys at all.
- **Simple login** with a cookie session, suitable for a small internal deployment.

---

## Quick start (Docker)

```bash
docker compose up --build
```

Open <http://localhost:8000> and log in. That's it — no `.env` file is required for the first run;
the app falls back to demo-mode defaults.

For a real deployment, copy the example file first and edit it:

```bash
cp .env.example .env
docker compose up --build
```

Stop it with `docker compose down`. Campaign data lives in the `adscope-data` volume and survives
restarts.

## Local setup (without Docker)

Requires Python 3.12.

```bash
python -m venv .venv
source .venv/bin/activate
make install      # installs requirements and creates .env from .env.example
make run          # http://localhost:8000
```

Other commands:

```bash
make test         # pytest
make lint         # ruff check + format check
make format       # ruff autofix + format
make docker-up    # docker compose up --build
make docker-down  # docker compose down
```

## Demo login credentials

The defaults in `.env.example` are:

| Field    | Value       |
| -------- | ----------- |
| Username | `admin`     |
| Password | `change-me` |

**Change these before deploying anywhere.** Set `APP_USERNAME` and `APP_PASSWORD`, and set
`SESSION_SECRET` to a long random string:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## Demo mode

```env
DEMO_MODE=true
```

Demo mode is **on by default** so the app works immediately after cloning. With it enabled AdScope:

- makes no external API calls and needs no API keys;
- returns realistic mocked responses for all three providers;
- simulates a short processing delay;
- shows a **Demo Mode** badge in the header.

The demo responses deliberately overlap only partially, so you get a realistic mix of High, Medium,
and Low agreement to test the consensus logic against.

Set `DEMO_MODE=false` to call the real APIs. With demo mode off and no API keys configured, the app
shows a clear error instead of creating an empty campaign.

---

## Configuring providers

Each provider is **optional** and is enabled only when its API key is set. AdScope works fine with
just one configured — the results then show `Single model` agreement. Set `DEMO_MODE=false` for any
of these to take effect.

### Gemini

1. Create an API key at <https://aistudio.google.com/app/apikey>.
2. Set:

```env
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-2.0-flash
```

### Groq

1. Create an API key at <https://console.groq.com/keys>.
2. Set:

```env
GROQ_API_KEY=your-key
GROQ_MODEL=llama-3.3-70b-versatile
```

### OpenRouter

1. Create an API key at <https://openrouter.ai/keys>.
2. Set:

```env
OPENROUTER_API_KEY=your-key
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct
```

OpenRouter is a gateway to many models — put any model slug it supports in `OPENROUTER_MODEL`.

---

## Environment variables

| Variable               | Default                      | Description                                              |
| ---------------------- | ---------------------------- | -------------------------------------------------------- |
| `APP_NAME`             | `AdScope`                    | Name shown in the UI.                                     |
| `APP_ENV`              | `development`                | Free-form environment label.                              |
| `DEBUG`                | `true`                       | Verbose logging.                                          |
| `APP_USERNAME`         | `admin`                      | Login username.                                           |
| `APP_PASSWORD`         | `change-me`                  | Login password. **Change this.**                          |
| `SESSION_SECRET`       | `change-this-secret`         | Signs the session cookie. **Change this.**                |
| `COOKIE_SECURE`        | `false`                      | Set `true` behind HTTPS to send cookies only over TLS.    |
| `DATABASE_URL`         | `sqlite:///./data/adscope.db`| SQLite database location.                                 |
| `DEMO_MODE`            | `true`                       | Use mocked providers instead of real APIs.                |
| `LLM_TIMEOUT_SECONDS`  | `60`                         | Per-provider request timeout.                             |
| `QUERIES_PER_PROVIDER` | `10`                         | Queries each model drafts in service-1.                   |
| `MAX_WEBSITES_PER_QUERY` | `10`                       | Max websites a model returns per query.                   |
| `MAX_YOUTUBE_PER_QUERY`| `10`                         | Max YouTube channels a model returns per query.           |
| `MAX_APPS_PER_QUERY`   | `10`                         | Max apps a model returns per query.                       |
| `MAX_FINAL_WEBSITES`   | `50`                         | Cap on the final ranked list, per publisher type.         |
| `LLM_CONCURRENCY`      | `8`                          | Max concurrent provider calls.                            |
| `POLL_INTERVAL_SECONDS`| `10`                         | Auto-refresh interval on the two waiting pages.           |
| `GEMINI_API_KEY`       | empty                        | Enables Gemini when set.                                  |
| `GEMINI_MODEL`         | `gemini-2.0-flash`           | Gemini model id.                                          |
| `GROQ_API_KEY`         | empty                        | Enables Groq when set.                                    |
| `GROQ_MODEL`           | `llama-3.3-70b-versatile`    | Groq model id.                                            |
| `OPENROUTER_API_KEY`   | empty                        | Enables OpenRouter when set.                              |
| `OPENROUTER_MODEL`     | `meta-llama/llama-3.3-70b-instruct` | OpenRouter model slug.                            |

Secrets are never hardcoded and never rendered into HTML.

---

## How the consensus works

1. **Match** — each model's recommendations are keyed by normalized domain: scheme, `www.`, path,
   query, and case are stripped, so `https://www.Vogue.in/fashion` and `vogue.in` are one publisher.
2. **Score** — `final_score` is the average of the scores from the models that recommended it.
3. **Count** — `model_count` is how many models recommended it.
4. **Agreement**:
   - **High** — recommended by every model that succeeded.
   - **Medium** — recommended by at least two.
   - **Low** — recommended by only one.
   - **Single model** — only one provider succeeded, so agreement cannot be measured.
5. **Sort** — by model count descending, then final score descending.

A publisher two models agree on outranks one that a single model scored higher. Every model's
original assessment is stored and viewable in the row's Details modal.

### Campaign statuses

| Status                     | Meaning                                        |
| -------------------------- | ---------------------------------------------- |
| `processing`               | Providers are being queried.                    |
| `completed`                | Every enabled provider succeeded.               |
| `completed_with_warnings`  | At least one succeeded and at least one failed. |
| `failed`                   | Every enabled provider failed.                  |

---

## Project structure

```text
adscope/
├── app/
│   ├── routers/          # HTTP only - thin, no business logic
│   │   ├── auth.py           # login, logout
│   │   ├── campaigns.py      # dashboard, form, create
│   │   └── recommendations.py# results page, CSV export
│   ├── handlers/         # form parsing and user-facing error messages
│   ├── services/         # business logic
│   │   ├── campaign_service.py   # orchestration, CSV building
│   │   ├── llm_service.py        # provider selection, concurrent calls
│   │   └── consensus_service.py  # domain matching, scoring, agreement
│   ├── providers/        # all provider-specific API details live here
│   │   ├── base.py           # shared interface, prompt, JSON extraction
│   │   ├── gemini.py / groq.py / openrouter.py
│   │   └── demo.py           # mocked providers for DEMO_MODE
│   ├── repositories/     # all database access
│   ├── entities/         # SQLAlchemy models
│   ├── schemas/          # Pydantic validation
│   ├── templates/        # Jinja2 + Bootstrap 5
│   ├── static/           # CSS, vanilla JS
│   ├── config.py         # pydantic-settings
│   ├── database.py       # engine, session
│   ├── security.py       # password check, session cookie
│   └── main.py           # app, auth middleware, error handlers
├── tests/
├── data/                 # SQLite lives here
├── Dockerfile
├── docker-compose.yml
├── Makefile
└── requirements.txt
```

### Endpoints

```text
GET  /health                          public
GET  /login                           public
POST /login
POST /logout
GET  /                                dashboard
GET  /campaigns/new
POST /campaigns
GET  /campaigns/{id}/review           human review of the drafted queries
POST /campaigns/{id}/queries          submit the reviewed queries
GET  /campaigns/{id}                  results
GET  /campaigns/{id}/export.csv
GET  /how-it-works                    plain-English guide to the pipeline
```

Everything except `/login` and `/health` requires a session.

### Processing model

Providers are queried **during the HTTP request** using `asyncio.gather`, so all models run
concurrently and the request takes about as long as the slowest one. The browser shows a loading
spinner and the submit button is disabled to prevent double submission.

This is a deliberate MVP tradeoff: no Celery, Redis, workers, or polling. The cost is that a
campaign is bounded by the request timeout — see Future improvements.

---

## Tests

```bash
make test
```

Covers login success and failure, protected-route redirects, session tampering, domain
normalization, consensus scoring and agreement levels, campaign creation in demo mode, CSV export,
provider timeout / auth failure / invalid JSON handling, and the all-providers-fail path.

---

## Security limitations of this MVP

Be clear-eyed about what this is. AdScope has:

- **A single shared username and password** from environment variables. No user accounts, no
  signup, no password reset, no roles, no OAuth, no SSO. Everyone shares one login, so you cannot
  tell who ran a campaign, and offboarding someone means changing the password for everybody.
- **No audit trail** of who did what.
- **No rate limiting or brute-force protection** on the login endpoint.
- **No CSRF tokens.** Session cookies are `SameSite=lax`, which blocks the common cross-site form
  POST, but that is not a substitute for CSRF tokens.
- **SQLite with no backups** configured. Fine for one user; not for a team relying on the history.
- **No encryption at rest.** Briefings may contain confidential client information.

What it does do: passwords are compared with `secrets.compare_digest` (constant-time), session
cookies are signed, HTTP-only, `SameSite=lax`, and can be marked `Secure`; all Jinja2 output is
escaped; input lengths are capped; API keys are never rendered into HTML; raw provider responses
are stored but never shown in the UI; and technical errors are logged server-side while users see
generic messages, so stack traces and secrets don't leak.

**This login is appropriate for a small internal MVP behind a trusted network or VPN. Company SSO
and stronger access controls should be added before wider production usage.**

## Deploying behind HTTPS

Do not expose AdScope directly to the internet over plain HTTP — the session cookie and password
would travel in the clear.

1. Set a strong `APP_PASSWORD` and a random `SESSION_SECRET`.
2. Set `COOKIE_SECURE=true` so cookies are only sent over TLS.
3. Set `APP_ENV=production` and `DEBUG=false`.
4. Terminate TLS at a reverse proxy (nginx, Caddy, or a cloud load balancer) and forward to
   port 8000.

A minimal Caddy config, which obtains a certificate automatically:

```caddy
adscope.example.com {
    reverse_proxy localhost:8000
}
```

Keep the `adscope-data` volume on persistent storage and back it up.

## Future improvements

- Company SSO (OIDC/SAML) with real user accounts, roles, and an audit trail.
- Move provider calls to a background job with polling, so large analyses aren't bound by the HTTP
  request timeout.
- Postgres instead of SQLite once more than one person uses it concurrently.
- Response caching so re-running a similar briefing doesn't re-spend API budget.
- Let users pick which models to query and adjust the prompt per campaign.
- Campaign history: comparison, re-running, editing, and deletion.
- Publisher allowlists/blocklists and brand-safety rules per client.
- CSRF tokens and login rate limiting.
