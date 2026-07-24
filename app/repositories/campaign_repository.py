from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.entities.models import (
    Campaign,
    CampaignPhase,
    CampaignStatus,
    FinalRecommendation,
    GeneratedQuery,
    ProviderResult,
    QueryResult,
)
from app.schemas.campaign import CampaignCreate, ProviderCallResult
from app.services.consensus_service import ConsensusEntry
from app.services.query_service import QueryDraft
from app.services.site_discovery_service import QueryResultRecord


def create_campaign(db: Session, data: CampaignCreate) -> Campaign:
    campaign = Campaign(
        client_name=data.client_name,
        campaign_name=data.campaign_name,
        briefing=data.briefing,
        target_country=data.target_country,
        objective=data.objective,
        budget=data.budget,
        queries_per_provider=data.queries_per_provider,
        max_websites_per_query=data.max_websites_per_query,
        max_final_websites=data.max_final_websites,
        status=CampaignStatus.PROCESSING,
        phase=CampaignPhase.GENERATING_QUERIES,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


def get_campaign(db: Session, campaign_id: int) -> Campaign | None:
    stmt = (
        select(Campaign)
        .where(Campaign.id == campaign_id)
        .options(
            selectinload(Campaign.queries),
            selectinload(Campaign.provider_results),
            selectinload(Campaign.query_results),
            selectinload(Campaign.recommendations),
        )
    )
    return db.execute(stmt).scalar_one_or_none()


def list_recent_campaigns(db: Session, limit: int = 20) -> list[Campaign]:
    stmt = select(Campaign).order_by(Campaign.created_at.desc(), Campaign.id.desc()).limit(limit)
    return list(db.execute(stmt).scalars())


def get_stats(db: Session) -> dict[str, int]:
    rows = db.execute(select(Campaign.status, func.count(Campaign.id)).group_by(Campaign.status)).all()
    counts = {status: count for status, count in rows}
    return {
        "total": sum(counts.values()),
        "completed": counts.get(CampaignStatus.COMPLETED, 0)
        + counts.get(CampaignStatus.COMPLETED_WITH_WARNINGS, 0),
        "failed": counts.get(CampaignStatus.FAILED, 0),
    }


# --- Generated queries (service-1 output + human review) ---------------------


def save_generated_queries(db: Session, campaign_id: int, drafts: list[QueryDraft]) -> None:
    for position, draft in enumerate(drafts):
        db.add(
            GeneratedQuery(
                campaign_id=campaign_id,
                text=draft.text,
                source_provider=draft.source_provider,
                is_custom=False,
                is_selected=True,
                position=position,
            )
        )
    db.commit()


def get_queries(db: Session, campaign_id: int) -> list[GeneratedQuery]:
    stmt = (
        select(GeneratedQuery)
        .where(GeneratedQuery.campaign_id == campaign_id)
        .order_by(GeneratedQuery.position.asc(), GeneratedQuery.id.asc())
    )
    return list(db.execute(stmt).scalars())


def replace_queries(db: Session, campaign_id: int, items: list[dict]) -> None:
    """Replace the campaign's query set with the human-reviewed one.

    Each item: {text, source_provider, is_custom, is_selected}. Rebuilding is
    simpler and safer than diffing edits, and the raw set is already captured in
    provider_results for audit.
    """
    db.query(GeneratedQuery).filter(GeneratedQuery.campaign_id == campaign_id).delete()
    for position, item in enumerate(items):
        db.add(
            GeneratedQuery(
                campaign_id=campaign_id,
                text=item["text"],
                source_provider=item.get("source_provider"),
                is_custom=bool(item.get("is_custom")),
                is_selected=bool(item.get("is_selected")),
                position=position,
            )
        )
    db.commit()


def get_selected_queries(db: Session, campaign_id: int) -> list[GeneratedQuery]:
    return [q for q in get_queries(db, campaign_id) if q.is_selected and q.text.strip()]


# --- Provider results (raw per-stage audit) ---------------------------------


def save_stage_results(
    db: Session, campaign_id: int, results: list[ProviderCallResult], stage: str
) -> None:
    for result in results:
        db.add(
            ProviderResult(
                campaign_id=campaign_id,
                stage=stage,
                provider_name=result.provider_name,
                status="success" if result.success else "failed",
                raw_response=result.text,
                parsed_response=None,
                error_message=result.error_message,
            )
        )
    db.commit()


# --- Query results (service-2 intermediate lists) ---------------------------


def save_query_results(db: Session, campaign_id: int, records: list[QueryResultRecord]) -> None:
    for record in records:
        db.add(
            QueryResult(
                campaign_id=campaign_id,
                query_id=record.query_id,
                query_text=record.query_text,
                provider_name=record.provider_name,
                status="success" if record.success else "failed",
                recommendations=json.dumps([r.model_dump() for r in record.recommendations])
                if record.recommendations
                else None,
                error_message=record.error_message,
            )
        )
    db.commit()


# --- Final recommendations ---------------------------------------------------


def save_recommendations(db: Session, campaign_id: int, entries: list[ConsensusEntry]) -> None:
    for entry in entries:
        db.add(
            FinalRecommendation(
                campaign_id=campaign_id,
                website_name=entry.website_name,
                domain=entry.domain,
                category=entry.category,
                final_score=entry.final_score,
                query_count=entry.query_count,
                model_count=entry.model_count,
                agreement=entry.agreement,
                combined_reason=entry.combined_reason,
                provider_details=json.dumps(entry.provider_details),
            )
        )
    db.commit()


def get_ranked_recommendations(db: Session, campaign_id: int) -> list[FinalRecommendation]:
    stmt = (
        select(FinalRecommendation)
        .where(FinalRecommendation.campaign_id == campaign_id)
        .order_by(
            FinalRecommendation.query_count.desc(),
            FinalRecommendation.final_score.desc(),
            FinalRecommendation.domain.asc(),
        )
    )
    return list(db.execute(stmt).scalars())


# --- Phase / status transitions ---------------------------------------------


def set_phase(
    db: Session,
    campaign_id: int,
    phase: str,
    *,
    status: str | None = None,
    error_message: str | None = None,
    mark_completed: bool = False,
) -> None:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        return
    campaign.phase = phase
    if status is not None:
        campaign.status = status
    campaign.error_message = error_message
    if mark_completed:
        campaign.completed_at = datetime.now(UTC)
    db.commit()
