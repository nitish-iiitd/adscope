import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.entities.models import (
    PUBLISHER_TYPE_LABELS,
    PUBLISHER_TYPE_NOUN,
    Campaign,
    CampaignPhase,
)
from app.handlers.campaign_handler import decode_provider_details
from app.repositories import campaign_repository as repo
from app.services.campaign_service import build_csv
from app.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()


def _provider_status(campaign: Campaign) -> tuple[list[str], list[dict]]:
    """Derive per-provider success/failure for service-2 from the query results."""
    success: dict[str, int] = {}
    errors: dict[str, str | None] = {}
    for qr in campaign.query_results:
        if qr.status == "success":
            success[qr.provider_name] = success.get(qr.provider_name, 0) + 1
        else:
            success.setdefault(qr.provider_name, 0)
            errors[qr.provider_name] = qr.error_message or "Provider failed"

    successful = sorted(name for name, count in success.items() if count > 0)
    failed = [
        {"provider_name": name, "error_message": errors.get(name)}
        for name, count in sorted(success.items())
        if count == 0
    ]
    return successful, failed


@router.get("/campaigns/{campaign_id}", response_class=HTMLResponse)
async def campaign_detail(request: Request, campaign_id: int, db: Session = Depends(get_db)):
    campaign = repo.get_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Before the human review step, send the user to the review page instead.
    if campaign.phase in (CampaignPhase.GENERATING_QUERIES, CampaignPhase.AWAITING_REVIEW):
        return RedirectResponse(url=f"/campaigns/{campaign_id}/review", status_code=303)

    processing = campaign.phase == CampaignPhase.DISCOVERING_SITES
    recommendations = repo.get_ranked_recommendations(db, campaign_id)
    rows = [
        {"rec": rec, "details": decode_provider_details(rec.provider_details)}
        for rec in recommendations
    ]
    tabs = _group_by_type(rows, campaign.publisher_type_list)
    successful, failed = _provider_status(campaign)
    selected_queries = [q for q in campaign.queries if q.is_selected]

    return templates.TemplateResponse(
        request,
        "campaign_detail.html",
        {
            "campaign": campaign,
            "processing": processing,
            "rows": rows,
            "tabs": tabs,
            "successful_providers": successful,
            "failed_providers": failed,
            "unique_publishers": len(recommendations),
            "selected_query_count": len(selected_queries),
            "selected_queries": selected_queries,
        },
    )


def _group_by_type(rows: list[dict], type_order: list[str]) -> list[dict]:
    """Split result rows into one tab per publisher type, in the campaign's order.

    Types the campaign selected but that produced no rows are dropped; any
    unexpected type still shows up (appended) rather than being silently lost.
    """
    by_type: dict[str, list[dict]] = {}
    for row in rows:
        by_type.setdefault(row["rec"].publisher_type, []).append(row)

    ordered = list(type_order) + [t for t in by_type if t not in type_order]
    tabs: list[dict] = []
    for ptype in ordered:
        type_rows = by_type.get(ptype)
        if not type_rows:
            continue
        tabs.append(
            {
                "type": ptype,
                "label": PUBLISHER_TYPE_LABELS.get(ptype, ptype.title()),
                "noun": PUBLISHER_TYPE_NOUN.get(ptype, "Publisher"),
                "rows": type_rows,
            }
        )
    return tabs


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
