"""Service-1: turn a campaign brief into a set of audience-style queries.

Each provider is asked for N queries; the combined raw set (providers x N) is
handed to the human review step.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import ValidationError

from app.config import Settings
from app.entities.models import Campaign
from app.providers.base import TASK_GENERATE_QUERIES, extract_json
from app.schemas.campaign import ProviderCallResult, QueryGenerationResponse
from app.services.llm_service import gather_bounded, require_providers
from app.services.prompts import build_brief_context, query_system_prompt

logger = logging.getLogger(__name__)


@dataclass
class QueryDraft:
    text: str
    source_provider: str


@dataclass
class QueryGenerationOutput:
    drafts: list[QueryDraft]
    provider_results: list[ProviderCallResult]


def _parse_queries(text: str | None, limit: int) -> list[str]:
    if not text:
        return []
    try:
        parsed = QueryGenerationResponse.model_validate(extract_json(text))
    except (ValueError, ValidationError) as exc:
        logger.warning("Could not parse query-generation response: %s", exc)
        return []

    seen: set[str] = set()
    out: list[str] = []
    for q in parsed.queries:
        cleaned = q.strip()
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
        if len(out) >= limit:
            break
    return out


async def generate_queries(campaign: Campaign, settings: Settings) -> QueryGenerationOutput:
    providers = require_providers(settings)
    system = query_system_prompt(settings.queries_per_provider)
    user = build_brief_context(campaign)

    logger.info("service-1: generating queries with %d provider(s)", len(providers))
    results = await gather_bounded(
        (p.complete(system, user, task=TASK_GENERATE_QUERIES) for p in providers),
        settings.llm_concurrency,
    )

    drafts: list[QueryDraft] = []
    for result in results:
        if not result.success:
            continue
        for text in _parse_queries(result.text, settings.queries_per_provider):
            drafts.append(QueryDraft(text=text, source_provider=result.provider_name))

    return QueryGenerationOutput(drafts=drafts, provider_results=results)
