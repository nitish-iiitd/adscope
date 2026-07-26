import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.entities.models import CampaignPhase, CampaignStatus
from app.handlers.campaign_handler import (
    CampaignInputError,
    CampaignRunError,
    parse_review_form,
)
from app.handlers.campaign_handler import (
    create_campaign as create_campaign_row,
)
from app.repositories import campaign_repository as repo
from app.services.campaign_service import run_query_generation, run_site_discovery
from app.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "stats": repo.get_stats(db),
            "campaigns": repo.list_recent_campaigns(db),
        },
    )


@router.get("/campaigns/new", response_class=HTMLResponse)
async def new_campaign_form(request: Request):
    return templates.TemplateResponse(request, "new_campaign.html", {"error": None, "form": {}})


@router.post("/campaigns")
async def create_campaign(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    client_name: str = Form(""),
    campaign_name: str = Form(""),
    briefing: str = Form(""),
    target_country: str = Form(""),
    objective: str = Form(""),
    budget: str = Form(""),
    publisher_types: list[str] = Form(default=[]),
    queries_per_provider: str = Form(""),
    max_websites_per_query: str = Form(""),
    max_final_websites: str = Form(""),
):
    form = {
        "client_name": client_name,
        "campaign_name": campaign_name,
        "briefing": briefing,
        "target_country": target_country,
        "objective": objective,
        "budget": budget,
        "publisher_types": publisher_types,
        "queries_per_provider": queries_per_provider,
        "max_websites_per_query": max_websites_per_query,
        "max_final_websites": max_final_websites,
    }
    try:
        campaign = create_campaign_row(db, form)
    except (CampaignInputError, CampaignRunError) as exc:
        return templates.TemplateResponse(
            request,
            "new_campaign.html",
            {"error": str(exc), "form": form},
            status_code=400,
        )

    # Service-1 runs in the background; the user lands on the review page which
    # polls until the queries are ready.
    background_tasks.add_task(run_query_generation, campaign.id, get_settings())
    return RedirectResponse(url=f"/campaigns/{campaign.id}/review", status_code=303)


@router.get("/campaigns/{campaign_id}/review", response_class=HTMLResponse)
async def review_queries(request: Request, campaign_id: int, db: Session = Depends(get_db)):
    campaign = repo.get_campaign(db, campaign_id)
    if campaign is None:
        return _not_found(request)

    # Once the brief has moved past review, the queries page has nothing to add.
    if campaign.phase in (CampaignPhase.DISCOVERING_SITES, CampaignPhase.COMPLETED, CampaignPhase.FAILED):
        return RedirectResponse(url=f"/campaigns/{campaign_id}", status_code=303)

    generating = campaign.phase == CampaignPhase.GENERATING_QUERIES
    return templates.TemplateResponse(
        request,
        "review.html",
        {
            "campaign": campaign,
            "generating": generating,
            "queries": repo.get_queries(db, campaign_id),
            "error": None,
        },
    )


@router.post("/campaigns/{campaign_id}/queries")
async def submit_queries(
    request: Request,
    campaign_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    campaign = repo.get_campaign(db, campaign_id)
    if campaign is None:
        return _not_found(request)
    if campaign.phase != CampaignPhase.AWAITING_REVIEW:
        return RedirectResponse(url=f"/campaigns/{campaign_id}", status_code=303)

    form = await request.form()
    try:
        items = parse_review_form(form)
    except CampaignInputError as exc:
        return templates.TemplateResponse(
            request,
            "review.html",
            {
                "campaign": campaign,
                "generating": False,
                "queries": repo.get_queries(db, campaign_id),
                "error": str(exc),
            },
            status_code=400,
        )

    repo.replace_queries(db, campaign_id, items)
    repo.set_phase(
        db, campaign_id, CampaignPhase.DISCOVERING_SITES, status=CampaignStatus.PROCESSING
    )
    background_tasks.add_task(run_site_discovery, campaign_id, get_settings())
    return RedirectResponse(url=f"/campaigns/{campaign_id}", status_code=303)


def _not_found(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "error.html",
        {"title": "Not found", "message": "That campaign does not exist."},
        status_code=404,
    )
