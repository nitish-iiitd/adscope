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
from app.entities.models import GeneratedQuery
from app.providers.base import TASK_DISCOVER_SITES, extract_json
from app.schemas.campaign import ProviderCallResult, ProviderOutcome, Recommendation
from app.services.consensus_service import (
    ConsensusEntry,
    aggregate_across_queries,
    build_consensus,
)
from app.services.llm_service import gather_bounded, require_providers
from app.services.prompts import build_site_user_prompt, site_system_prompt

logger = logging.getLogger(__name__)


@dataclass
class QueryResultRecord:
    """One provider's website output for one query (persisted for drill-down)."""

    query_id: int | None
    query_text: str
    provider_name: str
    success: bool
    recommendations: list[Recommendation]
    error_message: str | None


@dataclass
class DiscoveryOutput:
    query_results: list[QueryResultRecord]
    final_entries: list[ConsensusEntry]
    total_calls: int
    successful_calls: int


def _parse_sites(text: str | None, limit: int) -> list[Recommendation]:
    """Parse a site list leniently: skip bad items rather than drop the whole call."""
    if not text:
        return []
    try:
        data = extract_json(text)
    except ValueError as exc:
        logger.warning("Could not parse site-discovery response: %s", exc)
        return []

    raw_list = data.get("recommendations", []) if isinstance(data, dict) else []
    recs: list[Recommendation] = []
    for item in raw_list[:limit]:
        try:
            recs.append(Recommendation.model_validate(item))
        except ValidationError:
            continue
    return recs


async def discover_sites(queries: list[GeneratedQuery], settings: Settings) -> DiscoveryOutput:
    providers = require_providers(settings)
    system = site_system_prompt(settings.max_websites_per_query)

    # Fan out to (queries x providers). Keep the (query, provider) pairing so the
    # flat result list can be regrouped by query afterwards.
    jobs = [(q, p) for q in queries for p in providers]
    logger.info(
        "service-2: %d quer(ies) x %d provider(s) = %d calls",
        len(queries),
        len(providers),
        len(jobs),
    )
    results = await gather_bounded(
        (
            p.complete(system, build_site_user_prompt(q.text), task=TASK_DISCOVER_SITES)
            for (q, p) in jobs
        ),
        settings.llm_concurrency,
    )

    # Regroup flat results by query, preserving query order.
    per_query_jobs: dict[int, list[tuple[GeneratedQuery, ProviderCallResult]]] = {}
    for (query, _provider), result in zip(jobs, results, strict=True):
        per_query_jobs.setdefault(id(query), []).append((query, result))

    query_records: list[QueryResultRecord] = []
    per_query_consensus: list[tuple[str, list[ConsensusEntry]]] = []
    successful_calls = 0

    for query in queries:
        pairs = per_query_jobs.get(id(query), [])
        outcomes: list[ProviderOutcome] = []
        for _query, result in pairs:
            recs = _parse_sites(result.text, settings.max_websites_per_query) if result.success else []
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
        per_query_consensus.append((query.text, build_consensus(outcomes)))

    final_entries = aggregate_across_queries(per_query_consensus, settings.max_final_websites)

    return DiscoveryOutput(
        query_results=query_records,
        final_entries=final_entries,
        total_calls=len(jobs),
        successful_calls=successful_calls,
    )
