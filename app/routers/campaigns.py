import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.handlers.campaign_handler import (
    CampaignInputError,
    CampaignRunError,
    handle_create_campaign,
)
from app.repositories import campaign_repository as repo
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
    db: Session = Depends(get_db),
    client_name: str = Form(""),
    campaign_name: str = Form(""),
    briefing: str = Form(""),
    target_country: str = Form(""),
    objective: str = Form(""),
    budget: str = Form(""),
):
    form = {
        "client_name": client_name,
        "campaign_name": campaign_name,
        "briefing": briefing,
        "target_country": target_country,
        "objective": objective,
        "budget": budget,
    }
    try:
        campaign = await handle_create_campaign(db, form, get_settings())
    except (CampaignInputError, CampaignRunError) as exc:
        return templates.TemplateResponse(
            request,
            "new_campaign.html",
            {"error": str(exc), "form": form},
            status_code=400,
        )

    return RedirectResponse(url=f"/campaigns/{campaign.id}", status_code=303)
