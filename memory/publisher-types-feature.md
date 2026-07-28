---
name: publisher-types-feature
description: AdScope multi-publisher-type discovery (websites/YouTube/apps) — architecture and where apps plug in next
metadata:
  type: project
---

AdScope is extending its Service-2 discovery from websites-only to multiple publisher types. Users pick types via checkboxes on the New Campaign form (`publisher_types`, stored comma-joined on `Campaign`); results render one CSS-only tab per type in `results.html`.

Delivered (2026-07-25): **all three types — websites, YouTube channels, and applications (mobile/desktop)**. All three checkboxes are active on the New Campaign form.

**Key design decisions (why):** discovery prompts are **per-type** (`DISCOVERY_PROMPTS` in `app/services/prompts.py`), because the question differs fundamentally — websites use a *citation* frame ("which sources would you cite"), YouTube/apps use an *attention* frame ("where does this audience spend time"); an AI doesn't cite a channel/app. Identity/dedup is generalized via `identity_key(publisher_type, rec)` in `consensus_service.py`: websites→normalized domain, YouTube→`youtube.com/@handle`, **apps→normalized name slug** (not store URL — providers give different store listings/platforms for the same app, so name is the stable cross-provider key; platform is display-only). `Recommendation`/`ConsensusEntry`/`FinalRecommendation` carry `publisher_type` + `handle` (YT @handle / app platform) + `url` (clickable link; store URL for apps, `https://{key}` for web/YT). `entry.domain` is always the normalized group key (both consensus levels group by it).

Per-type **"results per query" limits** are separate settings/columns wired by one mapping, `PER_TYPE_LIMIT_FIELDS` in `entities/models.py` (type → attribute name shared by both `Settings` and `Campaign`, so `resolve_per_query_limits` resolves override-then-default generically). `max_final_websites` stays single and applies per type.

**DB:** SQLite `create_all` plus `_add_missing_columns()` in `database.py`, which ALTERs in any column present in the models but missing from the file. Adding columns is the only schema change this project has needed; anything more (renames, type changes, backfills) needs a real migration tool. Demo mode (`DEMO_MODE=true`) returns canned per-type data for local runs without API keys.

See also [[competitor-exclusion]] and [[pipeline-progress-reporting]].
