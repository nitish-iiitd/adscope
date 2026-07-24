"""Pipeline orchestration for the two-service flow.

The service-1 and service-2 runners are launched as background tasks, so they
open their own DB session (the request's session is closed once the response is
sent) and never raise into the event loop - failures are recorded on the campaign.
"""

from __future__ import annotations

import csv
import io
import logging

from sqlalchemy.orm import Session

from app.config import Settings
from app.database import SessionLocal
from app.entities.models import CampaignPhase, CampaignStatus
from app.repositories import campaign_repository as repo
from app.services.llm_service import NoProvidersConfiguredError
from app.services.query_service import generate_queries
from app.services.site_discovery_service import discover_sites

logger = logging.getLogger(__name__)

NO_PROVIDERS_MESSAGE = (
    "No AI providers are configured. Add a provider API key or enable demo mode."
)


def resolve_status(successful: int, failed: int) -> str:
    if successful == 0:
        return CampaignStatus.FAILED
    if failed > 0:
        return CampaignStatus.COMPLETED_WITH_WARNINGS
    return CampaignStatus.COMPLETED


async def run_query_generation(campaign_id: int, settings: Settings) -> None:
    """Service-1 background runner: brief -> raw queries -> awaiting review."""
    db: Session = SessionLocal()
    try:
        campaign = repo.get_campaign(db, campaign_id)
        if campaign is None:
            return
        try:
            output = await generate_queries(campaign, settings)
        except NoProvidersConfiguredError:
            repo.set_phase(
                db,
                campaign_id,
                CampaignPhase.FAILED,
                status=CampaignStatus.FAILED,
                error_message=NO_PROVIDERS_MESSAGE,
                mark_completed=True,
            )
            return

        repo.save_stage_results(db, campaign_id, output.provider_results, stage="queries")

        if not output.drafts:
            repo.set_phase(
                db,
                campaign_id,
                CampaignPhase.FAILED,
                status=CampaignStatus.FAILED,
                error_message="No queries could be generated from the brief. Please try again.",
                mark_completed=True,
            )
            return

        repo.save_generated_queries(db, campaign_id, output.drafts)
        repo.set_phase(db, campaign_id, CampaignPhase.AWAITING_REVIEW)
        logger.info("Campaign %s: %d queries generated, awaiting review", campaign_id, len(output.drafts))
    except Exception:
        logger.exception("Query generation failed for campaign %s", campaign_id)
        _safe_fail(db, campaign_id, "Query generation failed unexpectedly.")
    finally:
        db.close()


async def run_site_discovery(campaign_id: int, settings: Settings) -> None:
    """Service-2 background runner: refined queries -> final ranked websites."""
    db: Session = SessionLocal()
    try:
        queries = repo.get_selected_queries(db, campaign_id)
        if not queries:
            repo.set_phase(
                db,
                campaign_id,
                CampaignPhase.FAILED,
                status=CampaignStatus.FAILED,
                error_message="No queries were selected for analysis.",
                mark_completed=True,
            )
            return

        try:
            output = await discover_sites(queries, settings)
        except NoProvidersConfiguredError:
            repo.set_phase(
                db,
                campaign_id,
                CampaignPhase.FAILED,
                status=CampaignStatus.FAILED,
                error_message=NO_PROVIDERS_MESSAGE,
                mark_completed=True,
            )
            return

        repo.save_query_results(db, campaign_id, output.query_results)

        if not output.final_entries:
            repo.set_phase(
                db,
                campaign_id,
                CampaignPhase.FAILED,
                status=CampaignStatus.FAILED,
                error_message="No websites could be discovered for the selected queries.",
                mark_completed=True,
            )
            return

        repo.save_recommendations(db, campaign_id, output.final_entries)
        failed_calls = output.total_calls - output.successful_calls
        status = resolve_status(output.successful_calls, failed_calls)
        repo.set_phase(
            db,
            campaign_id,
            CampaignPhase.COMPLETED,
            status=status,
            error_message=None,
            mark_completed=True,
        )
        logger.info(
            "Campaign %s completed: %d sites from %d/%d successful calls",
            campaign_id,
            len(output.final_entries),
            output.successful_calls,
            output.total_calls,
        )
    except Exception:
        logger.exception("Site discovery failed for campaign %s", campaign_id)
        _safe_fail(db, campaign_id, "Website discovery failed unexpectedly.")
    finally:
        db.close()


def _safe_fail(db: Session, campaign_id: int, message: str) -> None:
    try:
        db.rollback()
        repo.set_phase(
            db,
            campaign_id,
            CampaignPhase.FAILED,
            status=CampaignStatus.FAILED,
            error_message=message,
            mark_completed=True,
        )
    except Exception:
        logger.exception("Could not mark campaign %s as failed", campaign_id)


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
            "Query count",
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
                rec.query_count,
                rec.model_count,
                rec.agreement,
                rec.combined_reason or "",
            ]
        )
    return buffer.getvalue()
