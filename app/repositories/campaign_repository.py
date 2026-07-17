from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.entities.models import Campaign, CampaignStatus, FinalRecommendation, ProviderResult
from app.schemas.campaign import CampaignCreate, ProviderOutcome
from app.services.consensus_service import ConsensusEntry


def create_campaign(db: Session, data: CampaignCreate) -> Campaign:
    campaign = Campaign(
        client_name=data.client_name,
        campaign_name=data.campaign_name,
        briefing=data.briefing,
        target_country=data.target_country,
        objective=data.objective,
        budget=data.budget,
        status=CampaignStatus.PROCESSING,
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
            selectinload(Campaign.provider_results),
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


def save_provider_results(db: Session, campaign_id: int, outcomes: list[ProviderOutcome]) -> None:
    for outcome in outcomes:
        db.add(
            ProviderResult(
                campaign_id=campaign_id,
                provider_name=outcome.provider_name,
                status="success" if outcome.success else "failed",
                raw_response=outcome.raw_response,
                parsed_response=json.dumps([r.model_dump() for r in outcome.recommendations])
                if outcome.success
                else None,
                error_message=outcome.error_message,
            )
        )
    db.commit()


def save_recommendations(db: Session, campaign_id: int, entries: list[ConsensusEntry]) -> None:
    for entry in entries:
        db.add(
            FinalRecommendation(
                campaign_id=campaign_id,
                website_name=entry.website_name,
                domain=entry.domain,
                category=entry.category,
                final_score=entry.final_score,
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
            FinalRecommendation.model_count.desc(),
            FinalRecommendation.final_score.desc(),
            FinalRecommendation.domain.asc(),
        )
    )
    return list(db.execute(stmt).scalars())


def update_status(db: Session, campaign_id: int, status: str, error_message: str | None = None) -> None:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        return
    campaign.status = status
    campaign.error_message = error_message
    if status != CampaignStatus.PROCESSING:
        campaign.completed_at = datetime.now(UTC)
    db.commit()
