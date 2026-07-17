"""Turns raw form input into validated data, runs the service, and shapes view data.

Keeps routers thin: routers only deal with HTTP, this module owns the
request-to-service translation and error messaging.
"""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings
from app.entities.models import Campaign
from app.schemas.campaign import CampaignCreate
from app.services.campaign_service import run_campaign
from app.services.llm_service import NoProvidersConfiguredError

logger = logging.getLogger(__name__)

FIELD_LABELS = {
    "client_name": "Client name",
    "campaign_name": "Campaign name",
    "briefing": "Client briefing",
    "target_country": "Target country",
    "objective": "Campaign objective",
    "budget": "Budget",
}


class CampaignInputError(Exception):
    """Form validation failed - message is safe to show the user."""


class CampaignRunError(Exception):
    """Campaign could not be run - message is safe to show the user."""


def parse_form(form: dict[str, str]) -> CampaignCreate:
    try:
        return CampaignCreate(**form)
    except ValidationError as exc:
        raise CampaignInputError(_first_error_message(exc)) from exc


def _first_error_message(exc: ValidationError) -> str:
    error = exc.errors()[0]
    field = str(error["loc"][0]) if error["loc"] else "input"
    label = FIELD_LABELS.get(field, field)
    kind = error["type"]
    if kind in ("missing", "string_too_short"):
        if field == "briefing":
            return "Client briefing is required and must be at least 20 characters."
        return f"{label} is required."
    if kind == "string_too_long":
        limit = error.get("ctx", {}).get("max_length", "the allowed")
        return f"{label} must be {limit} characters or fewer."
    return f"{label} is invalid."


async def handle_create_campaign(db: Session, form: dict[str, str], settings: Settings) -> Campaign:
    data = parse_form(form)
    try:
        return await run_campaign(db, data, settings)
    except NoProvidersConfiguredError as exc:
        logger.error("Campaign rejected: %s", exc)
        raise CampaignRunError(
            "No AI providers are configured. Add a provider API key or enable demo mode, then try again."
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Database error while running campaign: %s", exc)
        raise CampaignRunError("Could not save the campaign. Please try again.") from exc


def decode_provider_details(raw: str | None) -> list[dict]:
    """Provider details are stored as JSON text; return [] rather than break the page."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Could not decode stored provider_details")
        return []
    return data if isinstance(data, list) else []
