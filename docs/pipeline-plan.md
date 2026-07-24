# AdScope Pipeline Redesign Plan

## Goal

Replace the single-pass "brief → 3 LLMs → merged website list" flow with a
two-service pipeline that has a human review gate in the middle:

```
brief → service-1 → raw queries → human review → refined queries → service-2 → final ranked websites
```

Everything numeric is configurable, and adding a new LLM provider must be a
small, localized change (subclass + register + config entry).

## Definitions

- **service-1 (query generation):** takes the brief and asks each LLM to
  generate `N` user-style queries (default 10) that a target audience might ask
  their *own* AI agent about the brief's subject. With `P` providers the raw set
  is `P × N` queries.
- **human review:** the raw queries are shown in the UI; the user can add a
  custom query, edit any query, and remove/deselect queries, then submit. The
  result is the *refined* query set.
- **service-2 (site discovery + ranking):** for each refined query, each LLM is
  asked which websites it would consult to answer that query. The `P` provider
  outputs for one query are merged into a single ranked list (level-1
  consensus). The per-query lists are then aggregated into one final ranked list
  (level-2 aggregation).

## Key decisions (confirmed)

- **Execution:** in-process FastAPI `BackgroundTasks` + an `asyncio.Semaphore`
  to bound concurrency; review/detail pages poll on campaign phase.
- **Traceability:** persist the intermediate per-query website lists
  (`QueryResult`) so ranking can be drilled into and debugged.

---

## 1. Provider layer (extensibility foundation)

- Split transport from task. `BaseProvider.complete(system_prompt, user_prompt)
  -> ProviderCallResult` becomes the single primitive; it keeps the existing
  timeout / HTTP / error handling and returns `{success, text, error}`.
  `_call_api` stays abstract per provider. The hardcoded `SYSTEM_PROMPT` import
  leaves the providers — services own their prompts and parsing.
- Registry instead of if-chains:
  `PROVIDER_REGISTRY = {"gemini": GeminiProvider, "groq": GroqProvider, "openrouter": OpenRouterProvider}`.
  Config carries a list of provider entries (`type`, `model`, `api_key`,
  `enabled`); `build_providers` iterates and instantiates from the registry.
  Adding an LLM = one subclass + one registry line + one config entry.
- Demo mode returns `DemoProvider` instances for the configured entries, with
  canned data for **both** jobs so the whole pipeline runs offline.

## 2. Config (no magic numbers)

Add to `Settings`:

- `queries_per_provider: int = 10`
- `max_websites_per_query: int = 10`
- `max_final_websites: int = 50`
- `llm_concurrency: int = 8`
- provider list driving the registry

## 3. Data model

- `Campaign.phase` (new): `generating_queries → awaiting_review →
  discovering_sites → completed / failed`. Existing `status` kept for
  success/warnings/failed.
- `GeneratedQuery` (new): `campaign_id, text, source_provider, is_selected,
  is_custom, position, created_at`. Holds the raw set and, after review, the
  refined/selected set.
- `QueryResult` (new): per-query-per-provider website output for drill-down.
- `FinalRecommendation`: keep; add `query_count` (how many queries surfaced the
  site) alongside `model_count`.

## 4. Services

- `query_service.py` (service-1): per provider, prompt for `N` audience-style
  queries; combine into `P × N` `GeneratedQuery` rows.
- `site_discovery_service.py` (service-2), two-level:
  - Level 1 (per query): each selected query × each provider →
    "which websites would you consult to answer this?" → parse →
    reuse existing `build_consensus` to merge providers into one ranked list.
  - Level 2 (across queries): `aggregate_across_queries()` groups per-query
    lists by normalized domain; more queries surfacing a site ranks it higher
    (sort by `query_count`, then mean score), capped at `max_final_websites`.

## 5. Flow, routes, UI

1. `POST /campaigns` → create, launch service-1 (bg), redirect to review.
2. `GET /campaigns/{id}/review` → poll while `generating_queries`; then show
   queries with add / edit / remove / deselect.
3. `POST /campaigns/{id}/queries` → persist refined set, launch service-2 (bg),
   redirect to detail.
4. `GET /campaigns/{id}` → progress while `discovering_sites`; final ranked list
   when `completed`. CSV export gains a `query_count` column.

## 6. Execution model

Both services run via `BackgroundTasks` with a bounded `asyncio.Semaphore`
(`llm_concurrency`). Pages poll on `Campaign.phase`.

## 7. Tests & rollout

- Unit: query parsing/combination, `aggregate_across_queries`, registry
  construction, phase transitions.
- Extend `DemoProvider` with canned data for both jobs.
- Build order: provider refactor + registry → config → models → service-1 +
  review UI → service-2 + aggregation → detail/polling/CSV → tests.
