import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.handlers.campaign_handler import decode_provider_details
from app.repositories import campaign_repository as repo
from app.services.campaign_service import build_csv
from app.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/campaigns/{campaign_id}", response_class=HTMLResponse)
async def campaign_detail(request: Request, campaign_id: int, db: Session = Depends(get_db)):
    campaign = repo.get_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    recommendations = repo.get_ranked_recommendations(db, campaign_id)
    rows = [{"rec": rec, "details": decode_provider_details(rec.provider_details)} for rec in recommendations]
    successful = [r.provider_name for r in campaign.provider_results if r.status == "success"]
    failed = [
        {"provider_name": r.provider_name, "error_message": r.error_message}
        for r in campaign.provider_results
        if r.status != "success"
    ]

    return templates.TemplateResponse(
        request,
        "campaign_detail.html",
        {
            "campaign": campaign,
            "rows": rows,
            "successful_providers": sorted(successful),
            "failed_providers": failed,
            "unique_websites": len(recommendations),
        },
    )


def _safe_filename(campaign_name: str, campaign_id: int) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", campaign_name).strip("-").lower() or "campaign"
    return f"adscope-{slug[:50]}-{campaign_id}.csv"


@router.get("/campaigns/{campaign_id}/export.csv")
async def export_csv(campaign_id: int, db: Session = Depends(get_db)):
    campaign = repo.get_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    try:
        content = build_csv(db, campaign_id)
    except (SQLAlchemyError, OSError) as exc:
        logger.exception("CSV export failed for campaign %s: %s", campaign_id, exc)
        raise HTTPException(status_code=500, detail="Could not generate the CSV export") from exc

    filename = _safe_filename(campaign.campaign_name, campaign_id)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
