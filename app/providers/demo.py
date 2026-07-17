"""Mocked providers used when DEMO_MODE is enabled.

Each demo provider returns a plausible but fixed set of publishers. The sets
overlap only partially, so the consensus logic produces a realistic mix of
high, medium and low agreement.
"""

import asyncio
import json
import random

import httpx

from app.entities.models import Campaign
from app.providers.base import BaseProvider, extract_json
from app.schemas.campaign import ProviderOutcome, ProviderResponse

DEMO_DELAY_SECONDS = (0.6, 1.4)

_GEMINI_SITES = [
    (
        "Vogue India",
        "vogue.in",
        "Fashion & Lifestyle",
        91,
        94,
        88,
        90,
        "high",
        "Premium fashion and beauty audience closely matching the target demographic.",
        "Premium inventory is likely to carry a high CPM.",
    ),
    (
        "Nykaa",
        "nykaa.com",
        "Beauty & Commerce",
        89,
        93,
        86,
        89,
        "high",
        "Beauty-intent audience with strong overlap in metro cities.",
        "Retail media placements may favour performance over awareness.",
    ),
    (
        "Femina",
        "femina.in",
        "Women's Lifestyle",
        84,
        88,
        82,
        85,
        "high",
        "Long-standing women's title with broad reach in the target age band.",
        "Audience skews slightly older than the stated range.",
    ),
    (
        "The Better India",
        "thebetterindia.com",
        "Sustainability",
        78,
        76,
        80,
        88,
        "medium",
        "Sustainability-minded readership aligns with organic positioning.",
        "General-interest content reduces category precision.",
    ),
    (
        "Cosmopolitan India",
        "cosmopolitan.in",
        "Lifestyle",
        76,
        80,
        74,
        82,
        "medium",
        "Urban female readership suited to awareness campaigns.",
        "Editorial adjacency should be reviewed for brand safety.",
    ),
]

_GROQ_SITES = [
    (
        "Nykaa",
        "www.nykaa.com",
        "Beauty",
        87,
        90,
        84,
        88,
        "high",
        "Category-relevant destination for skincare buyers in India.",
        "Inventory availability must be confirmed with the publisher.",
    ),
    (
        "Vogue India",
        "https://vogue.in/",
        "Fashion",
        88,
        90,
        86,
        87,
        "high",
        "Aspirational positioning fits a premium organic brand.",
        "Cost may exceed smaller awareness budgets.",
    ),
    (
        "Hindustan Times Lifestyle",
        "hindustantimes.com",
        "News & Lifestyle",
        74,
        70,
        78,
        80,
        "medium",
        "Wide metro reach useful for top-of-funnel awareness.",
        "Broad news audience dilutes targeting precision.",
    ),
    (
        "Elle India",
        "elle.in",
        "Fashion & Beauty",
        82,
        85,
        80,
        84,
        "medium",
        "Beauty editorial reaches the intended age group.",
        "Smaller reach than larger lifestyle titles.",
    ),
    (
        "Purplle",
        "purplle.com",
        "Beauty & Commerce",
        72,
        76,
        70,
        82,
        "medium",
        "Beauty commerce audience, though skewing value-conscious.",
        "Positioning may not match a premium brand.",
    ),
]

_OPENROUTER_SITES = [
    (
        "Vogue India",
        "vogue.in",
        "Fashion & Lifestyle",
        90,
        92,
        88,
        89,
        "high",
        "Strong alignment with premium beauty and the intended audience.",
        "Advertising cost and inventory must be verified.",
    ),
    (
        "Nykaa",
        "nykaa.com",
        "Beauty",
        85,
        88,
        83,
        87,
        "high",
        "High purchase intent within the skincare category.",
        "Commerce environment is more suited to conversion goals.",
    ),
    (
        "Femina",
        "femina.in",
        "Women's Lifestyle",
        81,
        84,
        79,
        86,
        "medium",
        "Established women's publication with metro concentration.",
        "Verify current audience composition with the publisher.",
    ),
    (
        "Homegrown",
        "homegrown.co.in",
        "Culture & Lifestyle",
        73,
        75,
        72,
        80,
        "low",
        "Urban millennial culture audience open to new brands.",
        "Limited scale for a broad awareness campaign.",
    ),
    (
        "Mint Lounge",
        "lifestyle.livemint.com",
        "Lifestyle",
        70,
        68,
        74,
        88,
        "low",
        "Affluent metro readership with brand-safe editorial.",
        "Audience skews male relative to the target profile.",
    ),
]

_DEMO_DATA = {
    "gemini": _GEMINI_SITES,
    "groq": _GROQ_SITES,
    "openrouter": _OPENROUTER_SITES,
}


def _to_payload(rows: list[tuple]) -> str:
    return json.dumps(
        {
            "recommendations": [
                {
                    "website_name": r[0],
                    "domain": r[1],
                    "category": r[2],
                    "score": r[3],
                    "audience_match_score": r[4],
                    "objective_fit_score": r[5],
                    "brand_safety_score": r[6],
                    "confidence": r[7],
                    "short_reason": r[8],
                    "concerns": r[9],
                }
                for r in rows
            ]
        },
        indent=2,
    )


class DemoProvider(BaseProvider):
    """Returns a canned response after a short delay instead of calling an API."""

    def __init__(self, name: str, timeout: int) -> None:
        super().__init__(api_key="demo", model=f"{name}-demo", timeout=timeout)
        self.name = name

    async def _call_api(self, client: httpx.AsyncClient, prompt: str) -> str:
        return _to_payload(_DEMO_DATA[self.name])

    async def generate(self, campaign: Campaign) -> ProviderOutcome:
        # Demo mode makes no network calls, so bypass the parent's HTTP handling
        # and simulate the latency of a real provider instead.
        await asyncio.sleep(random.uniform(*DEMO_DELAY_SECONDS))
        raw = _to_payload(_DEMO_DATA[self.name])
        parsed = ProviderResponse.model_validate(extract_json(raw))
        return ProviderOutcome(
            provider_name=self.name,
            success=True,
            recommendations=parsed.recommendations,
            raw_response=raw,
        )
