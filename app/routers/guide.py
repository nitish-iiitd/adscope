"""The 'How it works' page.

Everything the page states about the pipeline is pulled from the code that
actually runs it - the prompts, the defaults, the badge thresholds. A page that
explains the system by describing it in prose goes stale the first time someone
edits a prompt; this one cannot.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.config import Settings, get_settings
from app.entities.models import (
    ALL_PUBLISHER_TYPES,
    PER_TYPE_LIMIT_FIELDS,
    PUBLISHER_TYPE_LABELS,
    Campaign,
)
from app.services.consensus_service import BREADTH_HIGH_RATIO, BREADTH_MEDIUM_RATIO
from app.services.prompts import (
    build_brief_context,
    build_site_user_prompt,
    competitor_exclusion_clause,
    discovery_system_prompt,
    query_system_prompt,
)
from app.templating import templates

router = APIRouter()

# A worked example, used both as running prose and as the real input to the
# prompt builders below - so the page shows exactly what a model would receive.
EXAMPLE_CLIENT = "Verdant Skincare"
EXAMPLE_COMPETITORS = ["Forest Essentials", "Kama Ayurveda"]
EXAMPLE_QUERY = "Which face serums actually work in humid monsoon weather?"


def _example_campaign() -> Campaign:
    """An unsaved campaign, only ever used to render the example brief."""
    return Campaign(
        client_name=EXAMPLE_CLIENT,
        campaign_name="Monsoon Skincare Launch",
        target_country="India",
        objective="Awareness & consideration",
        budget="INR 45,00,000",
        briefing=(
            "A premium organic skincare brand targeting women aged 25-40 in major Indian "
            "cities. Positioning is clean, dermatologist-backed and cruelty-free. Key "
            "message for the monsoon season is lightweight hydration."
        ),
    )


@router.get("/how-it-works", response_class=HTMLResponse)
async def how_it_works(request: Request, settings: Settings = Depends(get_settings)):
    discovery_prompts = [
        {
            "type": ptype,
            "label": PUBLISHER_TYPE_LABELS[ptype],
            "text": discovery_system_prompt(
                ptype, getattr(settings, PER_TYPE_LIMIT_FIELDS[ptype])
            ),
        }
        for ptype in ALL_PUBLISHER_TYPES
    ]

    return templates.TemplateResponse(
        request,
        "how_it_works.html",
        {
            "example_client": EXAMPLE_CLIENT,
            "example_query": EXAMPLE_QUERY,
            "example_competitors": ", ".join(EXAMPLE_COMPETITORS),
            "query_prompt": query_system_prompt(settings.queries_per_provider),
            "brief_context": build_brief_context(_example_campaign()),
            "discovery_prompts": discovery_prompts,
            "discovery_user_prompt": build_site_user_prompt(EXAMPLE_QUERY),
            "competitor_clause": competitor_exclusion_clause(EXAMPLE_CLIENT, EXAMPLE_COMPETITORS),
            "breadth_high_pct": round(BREADTH_HIGH_RATIO * 100),
            "breadth_medium_pct": round(BREADTH_MEDIUM_RATIO * 100),
            "provider_count": len(settings.provider_configs()),
        },
    )
