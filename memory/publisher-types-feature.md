---
name: publisher-types-feature
description: AdScope multi-publisher-type discovery (websites/YouTube/apps) — architecture and where apps plug in next
metadata:
  type: project
---

AdScope is extending its Service-2 discovery from websites-only to multiple publisher types. Users pick types via checkboxes on the New Campaign form (`publisher_types`, stored comma-joined on `Campaign`); results render one CSS-only tab per type in `results.html`.

Delivered (2026-07-25): **all three types — websites, YouTube channels, and applications (mobile/desktop)**. All three checkboxes are active on the New Campaign form.

**Key design decisions (why):** discovery prompts are **per-type** (`DISCOVERY_PROMPTS` in `app/services/prompts.py`), because the question differs fundamentally — websites use a *citation* frame ("which sources would you cite"), YouTube/apps use an *attention* frame ("where does this audience spend time"); an AI doesn't cite a channel/app. Identity/dedup is generalized via `identity_key(publisher_type, rec)` in `consensus_service.py`: websites→normalized domain, YouTube→`youtube.com/@handle`, **apps→normalized name slug** (not store URL — providers give different store listings/platforms for the same app, so name is the stable cross-provider key; platform is display-only). `Recommendation`/`ConsensusEntry`/`FinalRecommendation` carry `publisher_type` + `handle` (YT @handle / app platform) + `url` (clickable link; store URL for apps, `https://{key}` for web/YT). `entry.domain` is always the normalized group key (both consensus levels group by it).

**DB:** SQLite `create_all`, no migrations — reset by deleting `data/adscope.db`. Demo mode (`DEMO_MODE=true`) returns canned per-type data for local runs without API keys.
