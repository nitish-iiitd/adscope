"""Service-2: turn refined queries into a final ranked list of websites.

Level 1: for each query, ask every provider which sites it would consult, then
merge the providers into one ranked list (reusing build_consensus).
Level 2: aggregate those per-query lists into a single final ranking.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import ValidationError

from app.config import Settings
from app.entities.models import PER_TYPE_LIMIT_FIELDS, GeneratedQuery, PublisherType
from app.providers.base import (
    TASK_DISCOVER_APP,
    TASK_DISCOVER_SITES,
    TASK_DISCOVER_YOUTUBE,
    extract_json,
)
from app.schemas.campaign import ProviderCallResult, ProviderOutcome, Recommendation
from app.services.competitor_service import filter_competitors
from app.services.consensus_service import (
    ConsensusEntry,
    aggregate_across_queries,
    build_consensus,
)
from app.services.llm_service import gather_bounded, require_providers
from app.services.progress import (
    STEP_CALLING_MODELS,
    STEP_MERGING,
    STEP_RANKING,
    ProgressFn,
    ProgressUpdate,
    noop_progress,
)
from app.services.prompts import (
    build_site_user_prompt,
    competitor_exclusion_clause,
    discovery_system_prompt,
)

logger = logging.getLogger(__name__)

# Which demo-task hint each publisher type maps to (real providers ignore it).
DISCOVERY_TASKS = {
    PublisherType.WEBSITE: TASK_DISCOVER_SITES,
    PublisherType.YOUTUBE: TASK_DISCOVER_YOUTUBE,
    PublisherType.APP: TASK_DISCOVER_APP,
}


@dataclass
class QueryResultRecord:
    """One provider's publisher output for one query (persisted for drill-down)."""

    query_id: int | None
    query_text: str
    provider_name: str
    success: bool
    recommendations: list[Recommendation]
    error_message: str | None
    publisher_type: str = PublisherType.WEBSITE


@dataclass
class DiscoveryOutput:
    query_results: list[QueryResultRecord]
    # Final ranked entries keyed by publisher type (website, youtube, ...).
    final_by_type: dict[str, list[ConsensusEntry]]
    total_calls: int
    successful_calls: int
    # How many returned publishers the competitor filter dropped (0 when off).
    competitors_removed: int = 0


def resolve_per_query_limits(
    settings: Settings, overrides: dict[str, int | None] | None = None
) -> dict[str, int]:
    """How many results each model may return per query, for every type.

    A campaign's override wins; ``None`` or 0 falls back to the global default.
    """
    overrides = overrides or {}
    return {
        ptype: overrides.get(ptype) or getattr(settings, field)
        for ptype, field in PER_TYPE_LIMIT_FIELDS.items()
    }


def _raw_recommendations(text: str | None, kind: str) -> list[dict]:
    """Extract the ``recommendations`` array from a provider response, leniently."""
    if not text:
        return []
    try:
        data = extract_json(text)
    except ValueError as exc:
        logger.warning("Could not parse %s response: %s", kind, exc)
        return []
    raw = data.get("recommendations", []) if isinstance(data, dict) else []
    return [item for item in raw if isinstance(item, dict)]


def _parse_sites(text: str | None, limit: int) -> list[Recommendation]:
    """Parse a website list leniently: skip bad items rather than drop the call."""
    recs: list[Recommendation] = []
    for item in _raw_recommendations(text, "site-discovery")[:limit]:
        try:
            recs.append(Recommendation.model_validate({**item, "publisher_type": PublisherType.WEBSITE}))
        except ValidationError:
            continue
    return recs


def _parse_youtube(text: str | None, limit: int) -> list[Recommendation]:
    """Parse a YouTube channel list, mapping channel fields onto Recommendation."""
    recs: list[Recommendation] = []
    for item in _raw_recommendations(text, "youtube-discovery")[:limit]:
        handle = str(item.get("handle") or "").strip()
        name = item.get("channel_name") or item.get("website_name") or item.get("name") or handle
        locator = item.get("channel_url") or item.get("url") or handle
        data = {
            "publisher_type": PublisherType.YOUTUBE,
            "website_name": name,
            "domain": locator or "",
            "handle": handle,
            "category": item.get("category"),
            "score": item.get("score", 0),
            "audience_match_score": item.get("audience_match_score", 0),
            "objective_fit_score": item.get("objective_fit_score", 0),
            "brand_safety_score": item.get("brand_safety_score", 0),
            "short_reason": item.get("short_reason", ""),
            "concerns": item.get("concerns", ""),
            "confidence": item.get("confidence", "medium"),
        }
        try:
            recs.append(Recommendation.model_validate(data))
        except ValidationError:
            continue
    return recs


def _parse_app(text: str | None, limit: int) -> list[Recommendation]:
    """Parse an app list, mapping app fields onto Recommendation.

    ``domain`` carries the store URL, ``handle`` carries the platform label.
    """
    recs: list[Recommendation] = []
    for item in _raw_recommendations(text, "app-discovery")[:limit]:
        name = item.get("app_name") or item.get("website_name") or item.get("name") or ""
        platform = str(item.get("platform") or "").strip()
        store_url = item.get("store_url") or item.get("url") or item.get("domain") or ""
        data = {
            "publisher_type": PublisherType.APP,
            "website_name": name,
            "domain": store_url or "",
            "handle": platform,
            "category": item.get("category"),
            "score": item.get("score", 0),
            "audience_match_score": item.get("audience_match_score", 0),
            "objective_fit_score": item.get("objective_fit_score", 0),
            "brand_safety_score": item.get("brand_safety_score", 0),
            "short_reason": item.get("short_reason", ""),
            "concerns": item.get("concerns", ""),
            "confidence": item.get("confidence", "medium"),
        }
        try:
            recs.append(Recommendation.model_validate(data))
        except ValidationError:
            continue
    return recs


def _parse_publishers(text: str | None, publisher_type: str, limit: int) -> list[Recommendation]:
    if publisher_type == PublisherType.YOUTUBE:
        return _parse_youtube(text, limit)
    if publisher_type == PublisherType.APP:
        return _parse_app(text, limit)
    return _parse_sites(text, limit)


async def discover_sites(
    queries: list[GeneratedQuery],
    settings: Settings,
    *,
    publisher_types: list[str] | None = None,
    max_per_query: dict[str, int | None] | None = None,
    max_final: int | None = None,
    client_name: str = "",
    competitors: list[str] | None = None,
    exclude_competitors: bool = False,
    progress: ProgressFn = noop_progress,
) -> DiscoveryOutput:
    # Per-campaign overrides fall back to the configured defaults.
    limits = resolve_per_query_limits(settings, max_per_query)
    max_final = max_final or settings.max_final_websites
    publisher_types = publisher_types or [PublisherType.WEBSITE]

    competitors = competitors or []
    # The prompt asks the models to skip competitors; the filter below enforces
    # it. Naming no competitors still leaves the models the "own-brand" rule.
    exclusion_clause = (
        competitor_exclusion_clause(client_name, competitors) if exclude_competitors else ""
    )
    filter_names = competitors if exclude_competitors else []

    providers = require_providers(settings)

    # Fan out to (types x queries x providers). Keep the tuple so the flat result
    # list can be regrouped by (type, query) afterwards.
    jobs = [(t, q, p) for t in publisher_types for q in queries for p in providers]
    logger.info(
        "service-2: %d type(s) x %d quer(ies) x %d provider(s) = %d calls",
        len(publisher_types),
        len(queries),
        len(providers),
        len(jobs),
    )

    # One unit per model call, plus one for the merge and ranking that follow.
    total_units = len(jobs) + 1
    done = 0
    progress(
        ProgressUpdate(
            STEP_CALLING_MODELS,
            0,
            total_units,
            f"Sending {len(jobs)} AI calls: {len(queries)} quer"
            f"{'y' if len(queries) == 1 else 'ies'} x {len(providers)} model"
            f"{'' if len(providers) == 1 else 's'} x {len(publisher_types)} publisher type"
            f"{'' if len(publisher_types) == 1 else 's'}…",
        )
    )

    def _tick() -> None:
        nonlocal done
        done += 1
        progress(
            ProgressUpdate(
                STEP_CALLING_MODELS,
                done,
                total_units,
                f"{done} of {len(jobs)} model answers received",
            )
        )

    results = await gather_bounded(
        (
            p.complete(
                discovery_system_prompt(t, limits[t], exclusion_clause),
                build_site_user_prompt(q.text),
                task=DISCOVERY_TASKS.get(t, TASK_DISCOVER_SITES),
            )
            for (t, q, p) in jobs
        ),
        settings.llm_concurrency,
        on_done=_tick,
    )

    progress(
        ProgressUpdate(
            STEP_MERGING,
            len(jobs),
            total_units,
            "Merging the models' answers for each question…",
        )
    )

    # Regroup flat results by (type, query), preserving order.
    grouped: dict[tuple[str, int], list[ProviderCallResult]] = {}
    for (t, query, _provider), result in zip(jobs, results, strict=True):
        grouped.setdefault((t, id(query)), []).append(result)

    query_records: list[QueryResultRecord] = []
    final_by_type: dict[str, list[ConsensusEntry]] = {}
    successful_calls = 0
    competitors_removed = 0

    for publisher_type in publisher_types:
        per_query_consensus: list[tuple[str, list[ConsensusEntry]]] = []
        for query in queries:
            outcomes: list[ProviderOutcome] = []
            for result in grouped.get((publisher_type, id(query)), []):
                recs = (
                    _parse_publishers(result.text, publisher_type, limits[publisher_type])
                    if result.success
                    else []
                )
                recs, dropped = filter_competitors(recs, publisher_type, filter_names)
                competitors_removed += dropped
                # A call that returned only competitors still answered - it just
                # has nothing usable left, which is what "success" means here.
                success = result.success and bool(recs)
                if success:
                    successful_calls += 1
                query_records.append(
                    QueryResultRecord(
                        query_id=query.id,
                        query_text=query.text,
                        provider_name=result.provider_name,
                        success=success,
                        recommendations=recs,
                        error_message=result.error_message
                        or (None if success else "No usable recommendations returned"),
                        publisher_type=publisher_type,
                    )
                )
                outcomes.append(
                    ProviderOutcome(
                        provider_name=result.provider_name,
                        success=success,
                        recommendations=recs,
                        error_message=result.error_message,
                    )
                )
            per_query_consensus.append((query.text, build_consensus(outcomes, publisher_type)))

        progress(
            ProgressUpdate(
                STEP_RANKING,
                len(jobs),
                total_units,
                f"Ranking the final {publisher_type} list by breadth and agreement…",
            )
        )
        final_by_type[publisher_type] = aggregate_across_queries(
            per_query_consensus, max_final, publisher_type
        )

    total_entries = sum(len(entries) for entries in final_by_type.values())
    progress(
        ProgressUpdate(
            STEP_RANKING, total_units, total_units, f"{total_entries} publishers ranked"
        )
    )
    if competitors_removed:
        logger.info("service-2: removed %d competitor-owned publishers", competitors_removed)

    return DiscoveryOutput(
        query_results=query_records,
        final_by_type=final_by_type,
        total_calls=len(jobs),
        successful_calls=successful_calls,
        competitors_removed=competitors_removed,
    )
