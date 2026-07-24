"""Turns raw form input into validated data and shapes view data.

Keeps routers thin: routers deal with HTTP and background scheduling, this
module owns form parsing, validation and error messaging.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.entities.models import Campaign
from app.repositories import campaign_repository as repo
from app.schemas.campaign import CampaignCreate

logger = logging.getLogger(__name__)

FIELD_LABELS = {
    "client_name": "Client name",
    "campaign_name": "Campaign name",
    "briefing": "Client briefing",
    "target_country": "Target country",
    "objective": "Campaign objective",
    "budget": "Budget",
    "queries_per_provider": "Queries per model",
    "max_websites_per_query": "Websites per query",
    "max_final_websites": "Final website list size",
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
    if kind == "int_parsing":
        return f"{label} must be a whole number."
    if kind in ("greater_than_equal", "less_than_equal"):
        return f"{label} is outside the allowed range."
    return f"{label} is invalid."


def create_campaign(db: Session, form: dict[str, str]) -> Campaign:
    """Validate the brief and create the campaign row (service-1 runs after)."""
    data = parse_form(form)
    try:
        return repo.create_campaign(db, data)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Database error while creating campaign: %s", exc)
        raise CampaignRunError("Could not save the campaign. Please try again.") from exc


def parse_review_form(form: Mapping[str, str]) -> list[dict]:
    """Parse the dynamic review form into query items for persistence.

    Rows use indexed field names (text_{i}, selected_{i}, source_{i}, custom_{i})
    so rows can be freely added or removed client-side. Empty text is dropped;
    at least one selected, non-empty query is required.
    """
    indices: set[int] = set()
    for key in form:
        if key.startswith("text_"):
            suffix = key.removeprefix("text_")
            if suffix.isdigit():
                indices.add(int(suffix))

    items: list[dict] = []
    for i in sorted(indices):
        text = (form.get(f"text_{i}") or "").strip()
        if not text:
            continue
        items.append(
            {
                "text": text,
                "source_provider": form.get(f"source_{i}") or None,
                "is_custom": form.get(f"custom_{i}") == "1",
                "is_selected": f"selected_{i}" in form,
            }
        )

    if not any(item["is_selected"] for item in items):
        raise CampaignInputError("Select at least one query to analyse.")
    return items


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
