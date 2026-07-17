from __future__ import annotations

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod

import httpx
from pydantic import ValidationError

from app.entities.models import Campaign
from app.schemas.campaign import ProviderOutcome, ProviderResponse

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are assisting a media planning team.

Analyse the supplied campaign briefing and recommend up to 10 websites or digital publishers \
where the client could consider placing advertisements.

Focus on the target audience, campaign objective, geography, product category, brand positioning, \
budget suitability, and brand safety.

Do not invent traffic numbers, pricing, partnerships, or audience statistics.

For every recommendation return:

- website_name
- domain
- category
- score from 0 to 100
- audience_match_score from 0 to 100
- objective_fit_score from 0 to 100
- brand_safety_score from 0 to 100
- short_reason
- concerns
- confidence: high, medium, or low

Return valid JSON only, shaped as {"recommendations": [...]}."""


def build_campaign_prompt(campaign: Campaign) -> str:
    lines = [
        f"Client name: {campaign.client_name}",
        f"Campaign name: {campaign.campaign_name}",
        f"Target country: {campaign.target_country}",
    ]
    if campaign.objective:
        lines.append(f"Campaign objective: {campaign.objective}")
    if campaign.budget:
        lines.append(f"Budget: {campaign.budget}")
    lines.append(f"\nClient briefing:\n{campaign.briefing}")
    return "\n".join(lines)


def extract_json(text: str) -> dict:
    """Parse a JSON object from raw model output.

    Models routinely wrap JSON in prose or markdown fences, so fall back to
    scanning for the outermost balanced object before giving up.
    """
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)

    raise ValueError("No valid JSON object found in provider response")


class BaseProvider(ABC):
    """Shared provider contract: every provider turns a campaign into a ProviderOutcome.

    Subclasses only implement the HTTP call and return raw text; parsing,
    validation and error shaping are handled here so all providers behave alike.
    """

    name: str = "base"

    def __init__(self, api_key: str, model: str, timeout: int) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @abstractmethod
    async def _call_api(self, client: httpx.AsyncClient, prompt: str) -> str:
        """Send the prompt and return the model's raw text output."""

    async def generate(self, campaign: Campaign) -> ProviderOutcome:
        prompt = build_campaign_prompt(campaign)
        raw: str | None = None
        try:
            # httpx's timeout applies per socket read, so a model that trickles tokens
            # back can run far past it. asyncio.timeout bounds the whole call instead,
            # which is what LLM_TIMEOUT_SECONDS is meant to promise.
            async with asyncio.timeout(self.timeout):
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    raw = await self._call_api(client, prompt)
            parsed = ProviderResponse.model_validate(extract_json(raw))
            return ProviderOutcome(
                provider_name=self.name,
                success=True,
                recommendations=parsed.recommendations,
                raw_response=raw,
            )
        except (httpx.TimeoutException, TimeoutError):
            logger.warning("%s timed out after %ss", self.name, self.timeout)
            return self._failure(f"Provider timed out after {self.timeout}s", raw)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (401, 403):
                message = "Authentication failed - check the API key"
            elif status == 429:
                message = "Rate limit exceeded"
            else:
                message = f"Provider returned HTTP {status}"
            logger.warning("%s HTTP error %s: %s", self.name, status, exc.response.text[:500])
            return self._failure(message, raw)
        except httpx.HTTPError as exc:
            logger.warning("%s network error: %s", self.name, exc)
            return self._failure("Could not reach the provider", raw)
        except (ValueError, ValidationError) as exc:
            logger.warning("%s returned unusable output: %s", self.name, exc)
            return self._failure("Provider returned an invalid or unexpected response", raw)
        except Exception as exc:  # last resort: one provider must never fail the campaign
            logger.exception("%s failed unexpectedly: %s", self.name, exc)
            return self._failure("Unexpected provider error", raw)

    def _failure(self, message: str, raw: str | None) -> ProviderOutcome:
        return ProviderOutcome(
            provider_name=self.name,
            success=False,
            raw_response=raw,
            error_message=message,
        )
