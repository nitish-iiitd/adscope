"""Mocked providers used when DEMO_MODE is enabled.

Each demo provider returns plausible but fixed data for both pipeline stages:
a set of audience-style queries (service-1) and, for any query, a set of
publishers (service-2). The sets overlap only partially across providers, so
the consensus and aggregation logic produce a realistic mix of agreement.
"""

import asyncio
import json
import random

import httpx

from app.providers.base import (
    TASK_DISCOVER_SITES,
    TASK_GENERATE_QUERIES,
    BaseProvider,
)
from app.schemas.campaign import ProviderCallResult

DEMO_DELAY_SECONDS = (0.3, 0.9)

# --- Service-1 canned queries ------------------------------------------------

_GEMINI_QUERIES = [
    "What are the best premium organic skincare brands available in India right now?",
    "Which face serums work well for humid monsoon weather?",
    "Where can I read trustworthy reviews of natural beauty products?",
    "What ingredients should I look for in an organic moisturiser?",
    "Which Indian beauty publications cover sustainable skincare?",
    "How do I build a minimal clean-beauty routine for sensitive skin?",
    "What are affordable alternatives to luxury organic skincare?",
    "Which skincare brands are cruelty-free and certified organic in India?",
    "What is the best sunscreen for daily use in Indian cities?",
    "Where do beauty editors recommend shopping for skincare online?",
]

_GROQ_QUERIES = [
    "Best organic skincare products for women in their 30s in India?",
    "Which websites review clean beauty and skincare brands?",
    "How to choose a chemical-free face wash for city pollution?",
    "What are the top-rated Indian D2C skincare startups?",
    "Which magazines cover beauty trends for urban Indian women?",
    "Are there dermatologist-approved organic skincare lines?",
    "What skincare should I use during the monsoon season?",
    "Where can I compare prices of premium skincare in India?",
    "Which beauty influencers focus on sustainable products?",
    "What is a good gifting skincare set under a premium budget?",
]

_OPENROUTER_QUERIES = [
    "Recommend trustworthy sources for organic skincare reviews in India.",
    "What are the leading beauty and lifestyle sites for Indian women?",
    "How do I find brand-safe publishers for a skincare campaign?",
    "Which platforms have strong skincare shopping content?",
    "What content sites discuss sustainability in beauty?",
    "Where do millennials in Indian metros read about skincare?",
    "Which e-commerce sites specialise in beauty in India?",
    "What are respected editorial voices on clean beauty?",
    "Which lifestyle magazines reach affluent metro readers?",
    "Where can I find seasonal skincare advice for monsoon?",
]

_DEMO_QUERIES = {
    "gemini": _GEMINI_QUERIES,
    "groq": _GROQ_QUERIES,
    "openrouter": _OPENROUTER_QUERIES,
}

# --- Service-2 canned publisher sets -----------------------------------------
# tuple layout: name, domain, category, score, audience, objective, brand_safety,
#               confidence, short_reason, concerns

_GEMINI_SITES = [
    ("Vogue India", "vogue.in", "Fashion & Lifestyle", 91, 94, 88, 90, "high",
     "Premium fashion and beauty audience closely matching the target demographic.",
     "Premium inventory is likely to carry a high CPM."),
    ("Nykaa", "nykaa.com", "Beauty & Commerce", 89, 93, 86, 89, "high",
     "Beauty-intent audience with strong overlap in metro cities.",
     "Retail media placements may favour performance over awareness."),
    ("Femina", "femina.in", "Women's Lifestyle", 84, 88, 82, 85, "high",
     "Long-standing women's title with broad reach in the target age band.",
     "Audience skews slightly older than the stated range."),
    ("The Better India", "thebetterindia.com", "Sustainability", 78, 76, 80, 88, "medium",
     "Sustainability-minded readership aligns with organic positioning.",
     "General-interest content reduces category precision."),
    ("Cosmopolitan India", "cosmopolitan.in", "Lifestyle", 76, 80, 74, 82, "medium",
     "Urban female readership suited to awareness campaigns.",
     "Editorial adjacency should be reviewed for brand safety."),
]

_GROQ_SITES = [
    ("Nykaa", "www.nykaa.com", "Beauty", 87, 90, 84, 88, "high",
     "Category-relevant destination for skincare buyers in India.",
     "Inventory availability must be confirmed with the publisher."),
    ("Vogue India", "https://vogue.in/", "Fashion", 88, 90, 86, 87, "high",
     "Aspirational positioning fits a premium organic brand.",
     "Cost may exceed smaller awareness budgets."),
    ("Hindustan Times Lifestyle", "hindustantimes.com", "News & Lifestyle", 74, 70, 78, 80, "medium",
     "Wide metro reach useful for top-of-funnel awareness.",
     "Broad news audience dilutes targeting precision."),
    ("Elle India", "elle.in", "Fashion & Beauty", 82, 85, 80, 84, "medium",
     "Beauty editorial reaches the intended age group.",
     "Smaller reach than larger lifestyle titles."),
    ("Purplle", "purplle.com", "Beauty & Commerce", 72, 76, 70, 82, "medium",
     "Beauty commerce audience, though skewing value-conscious.",
     "Positioning may not match a premium brand."),
]

_OPENROUTER_SITES = [
    ("Vogue India", "vogue.in", "Fashion & Lifestyle", 90, 92, 88, 89, "high",
     "Strong alignment with premium beauty and the intended audience.",
     "Advertising cost and inventory must be verified."),
    ("Nykaa", "nykaa.com", "Beauty", 85, 88, 83, 87, "high",
     "High purchase intent within the skincare category.",
     "Commerce environment is more suited to conversion goals."),
    ("Femina", "femina.in", "Women's Lifestyle", 81, 84, 79, 86, "medium",
     "Established women's publication with metro concentration.",
     "Verify current audience composition with the publisher."),
    ("Homegrown", "homegrown.co.in", "Culture & Lifestyle", 73, 75, 72, 80, "low",
     "Urban millennial culture audience open to new brands.",
     "Limited scale for a broad awareness campaign."),
    ("Mint Lounge", "lifestyle.livemint.com", "Lifestyle", 70, 68, 74, 88, "low",
     "Affluent metro readership with brand-safe editorial.",
     "Audience skews male relative to the target profile."),
]

_DEMO_SITES = {
    "gemini": _GEMINI_SITES,
    "groq": _GROQ_SITES,
    "openrouter": _OPENROUTER_SITES,
}


def _queries_payload(name: str) -> str:
    return json.dumps({"queries": _DEMO_QUERIES.get(name, _GEMINI_QUERIES)})


def _sites_payload(name: str, user_prompt: str) -> str:
    rows = _DEMO_SITES.get(name, _GEMINI_SITES)
    # Vary which sites surface per query so aggregation across queries is not flat:
    # rotate the list deterministically by the query text.
    offset = abs(hash(user_prompt)) % len(rows)
    rotated = rows[offset:] + rows[:offset]
    picked = rotated[: max(3, len(rows) - (offset % 2))]
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
                for r in picked
            ]
        },
        indent=2,
    )


class DemoProvider(BaseProvider):
    """Returns canned responses after a short delay instead of calling an API."""

    def __init__(self, name: str, timeout: int) -> None:
        super().__init__(api_key="demo", model=f"{name}-demo", timeout=timeout, name=name)

    async def _call_api(self, client: httpx.AsyncClient, system_prompt: str, user_prompt: str) -> str:
        # Not used: complete() is overridden to bypass HTTP entirely.
        raise NotImplementedError

    async def complete(
        self, system_prompt: str, user_prompt: str, *, task: str | None = None
    ) -> ProviderCallResult:
        await asyncio.sleep(random.uniform(*DEMO_DELAY_SECONDS))
        if task == TASK_GENERATE_QUERIES:
            text = _queries_payload(self.name)
        elif task == TASK_DISCOVER_SITES:
            text = _sites_payload(self.name, user_prompt)
        else:
            text = "{}"
        return ProviderCallResult(provider_name=self.name, success=True, text=text)
