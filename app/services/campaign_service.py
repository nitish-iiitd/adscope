from __future__ import annotations

import csv
import io
import logging

from sqlalchemy.orm import Session

from app.config import Settings
from app.entities.models import Campaign, CampaignStatus
from app.repositories import campaign_repository as repo
from app.schemas.campaign import CampaignCreate
from app.services.consensus_service import build_consensus
from app.services.llm_service import run_providers

logger = logging.getLogger(__name__)


def resolve_status(successful: int, failed: int) -> str:
    if successful == 0:
        return CampaignStatus.FAILED
    if failed > 0:
        return CampaignStatus.COMPLETED_WITH_WARNINGS
    return CampaignStatus.COMPLETED


async def run_campaign(db: Session, data: CampaignCreate, settings: Settings) -> Campaign:
    """Create a campaign, query providers, store consensus, and return the campaign.

    Provider failures are recorded rather than raised: a campaign only fails
    when every enabled provider fails.
    """
    campaign = repo.create_campaign(db, data)

    outcomes = await run_providers(campaign, settings)
    repo.save_provider_results(db, campaign.id, outcomes)

    successful = [o for o in outcomes if o.success]
    failed = [o for o in outcomes if not o.success]

    if successful:
        entries = build_consensus(outcomes)
        repo.save_recommendations(db, campaign.id, entries)

    status = resolve_status(len(successful), len(failed))
    error_message = None
    if status == CampaignStatus.FAILED:
        error_message = "All providers failed: " + "; ".join(
            f"{o.provider_name}: {o.error_message}" for o in failed
        )
    repo.update_status(db, campaign.id, status, error_message)

    refreshed = repo.get_campaign(db, campaign.id)
    assert refreshed is not None
    return refreshed


def build_csv(db: Session, campaign_id: int) -> str:
    recommendations = repo.get_ranked_recommendations(db, campaign_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Rank",
            "Website name",
            "Domain",
            "Category",
            "Final score",
            "Model count",
            "Agreement",
            "Combined reason",
        ]
    )
    for rank, rec in enumerate(recommendations, start=1):
        writer.writerow(
            [
                rank,
                rec.website_name,
                rec.domain,
                rec.category or "",
                rec.final_score,
                rec.model_count,
                rec.agreement,
                rec.combined_reason or "",
            ]
        )
    return buffer.getvalue()
