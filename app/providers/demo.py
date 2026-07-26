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
    TASK_DISCOVER_APP,
    TASK_DISCOVER_SITES,
    TASK_DISCOVER_YOUTUBE,
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

# --- Service-2 canned YouTube channel sets -----------------------------------
# tuple layout: channel_name, handle, category, score, audience, objective,
#               brand_safety, confidence, short_reason, concerns

_GEMINI_CHANNELS = [
    ("Beauty Within", "@BeautyWithin", "Skincare Education", 90, 92, 86, 90, "high",
     "Dermatology-informed skincare content matching an ingredient-curious audience.",
     "Global audience - India share must be confirmed."),
    ("Hyram", "@Hyram", "Skincare Reviews", 88, 90, 84, 88, "high",
     "Trusted clean-skincare voice with strong purchase influence.",
     "Skews younger than the stated age band."),
    ("Be Beautiful", "@BeBeautiful", "Indian Beauty", 84, 88, 82, 86, "high",
     "India-focused beauty channel aligned with the target market.",
     "Broad beauty remit dilutes organic-category precision."),
    ("Fit Tuber", "@FitTuber", "Wellness & Natural", 79, 78, 80, 85, "medium",
     "Natural-living Indian audience receptive to organic positioning.",
     "Wellness framing may not match a premium beauty tone."),
]

_GROQ_CHANNELS = [
    ("Hyram", "@Hyram", "Skincare", 87, 89, 83, 87, "high",
     "Ingredient-led reviews reach an engaged skincare audience.",
     "Sponsorship inventory must be confirmed."),
    ("Beauty Within", "@BeautyWithin", "Skincare Education", 89, 90, 85, 89, "high",
     "Editorial, research-led tone suits a premium organic brand.",
     "Production cadence is slower than daily-content channels."),
    ("Shreya Jain", "@ShreyaJain25", "Indian Beauty", 82, 85, 80, 84, "medium",
     "Established Indian beauty creator with metro reach.",
     "Audience composition should be verified with the creator."),
    ("Plush Affair", "@PlushAffair", "Beauty & Lifestyle", 74, 76, 72, 82, "medium",
     "Lifestyle beauty content for urban Indian women.",
     "Smaller reach than larger beauty channels."),
]

_OPENROUTER_CHANNELS = [
    ("Beauty Within", "@BeautyWithin", "Skincare Education", 91, 93, 87, 90, "high",
     "Strong alignment with a considered, ingredient-first audience.",
     "Verify India audience share before committing."),
    ("Hyram", "@Hyram", "Skincare", 85, 88, 82, 86, "high",
     "High trust and purchase influence in clean skincare.",
     "Younger skew relative to the target profile."),
    ("Be Beautiful", "@BeBeautiful", "Indian Beauty", 80, 83, 78, 85, "medium",
     "India-first beauty publisher channel with category fit.",
     "General beauty focus rather than organic-specific."),
    ("Miss Malini", "@MissMalini", "Lifestyle", 71, 72, 70, 83, "low",
     "Metro lifestyle audience useful for awareness.",
     "Limited skincare-specific depth."),
]

_DEMO_CHANNELS = {
    "gemini": _GEMINI_CHANNELS,
    "groq": _GROQ_CHANNELS,
    "openrouter": _OPENROUTER_CHANNELS,
}

# --- Service-2 canned app sets -----------------------------------------------
# tuple layout: app_name, platform, store_url, category, score, audience,
#               objective, brand_safety, confidence, short_reason, concerns

_PLAY = "https://play.google.com/store/apps/details?id="

_GEMINI_APPS = [
    ("Nykaa", "iOS/Android", f"{_PLAY}com.fsn.nykaa", "Beauty & Commerce", 90, 93, 86, 89, "high",
     "Category-leading beauty shopping app with high purchase intent.",
     "Retail environment favours conversion over awareness."),
    ("Myntra", "iOS/Android", f"{_PLAY}com.myntra.android", "Fashion & Beauty", 85, 87, 83, 87, "high",
     "Fashion-and-beauty audience overlaps strongly with the target.",
     "Beauty is one of many categories in-app."),
    ("Instagram", "iOS/Android", f"{_PLAY}com.instagram.android", "Social", 83, 88, 80, 78, "high",
     "Where the target audience discovers and follows beauty brands.",
     "Brand-safety adjacency needs monitoring."),
    ("Purplle", "iOS/Android", f"{_PLAY}com.manash.purplle", "Beauty & Commerce", 74, 78, 71, 83, "medium",
     "Value-focused beauty commerce with growing metro reach.",
     "Positioning skews value rather than premium."),
]

_GROQ_APPS = [
    ("Nykaa", "Android", f"{_PLAY}com.fsn.nykaa", "Beauty", 88, 91, 84, 88, "high",
     "Primary destination app for skincare buyers in India.",
     "Inventory and targeting options must be confirmed."),
    ("Instagram", "iOS/Android", f"{_PLAY}com.instagram.android", "Social", 84, 89, 81, 79, "high",
     "High time-spent app ideal for awareness and influencer tie-ins.",
     "Feed adjacency varies - verify brand safety."),
    ("Pinterest", "iOS/Android", f"{_PLAY}com.pinterest", "Discovery", 78, 82, 76, 85, "medium",
     "Skincare and routine inspiration drives high intent.",
     "Smaller India scale than the leading social apps."),
    ("Tira", "iOS/Android", f"{_PLAY}com.tira.beauty", "Beauty & Commerce", 72, 75, 70, 84, "medium",
     "Premium beauty retail app aligned with the brand tier.",
     "Newer app with a still-growing user base."),
]

_OPENROUTER_APPS = [
    ("Nykaa", "iOS/Android", f"{_PLAY}com.fsn.nykaa", "Beauty & Commerce", 89, 92, 85, 89, "high",
     "Strong skincare purchase intent within a beauty-first audience.",
     "Commerce context suits performance goals."),
    ("Myntra", "iOS/Android", f"{_PLAY}com.myntra.android", "Fashion & Beauty", 82, 85, 80, 86, "high",
     "Large fashion-beauty audience concentrated in metros.",
     "Category breadth dilutes skincare precision."),
    ("YouTube", "iOS/Android", f"{_PLAY}com.google.android.youtube", "Video", 76, 80, 74, 82, "medium",
     "Long-form skincare and review content reaches the audience.",
     "Broad audience requires careful targeting."),
    ("Amazon", "iOS/Android", f"{_PLAY}com.amazon.mShop.android.shopping", "Commerce", 70, 72, 72, 84, "low",
     "Wide reach for beauty purchases across price tiers.",
     "General marketplace, low category focus."),
]

_DEMO_APPS = {
    "gemini": _GEMINI_APPS,
    "groq": _GROQ_APPS,
    "openrouter": _OPENROUTER_APPS,
}


def _queries_payload(name: str) -> str:
    return json.dumps({"queries": _DEMO_QUERIES.get(name, _GEMINI_QUERIES)})


def _rotate(rows: list, user_prompt: str) -> list:
    # Vary which items surface per query so aggregation across queries is not
    # flat: rotate the list deterministically by the query text.
    offset = abs(hash(user_prompt)) % len(rows)
    rotated = rows[offset:] + rows[:offset]
    return rotated[: max(3, len(rows) - (offset % 2))]


def _sites_payload(name: str, user_prompt: str) -> str:
    picked = _rotate(_DEMO_SITES.get(name, _GEMINI_SITES), user_prompt)
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


def _youtube_payload(name: str, user_prompt: str) -> str:
    picked = _rotate(_DEMO_CHANNELS.get(name, _GEMINI_CHANNELS), user_prompt)
    return json.dumps(
        {
            "recommendations": [
                {
                    "channel_name": r[0],
                    "handle": r[1],
                    "channel_url": f"https://www.youtube.com/{r[1]}",
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


def _apps_payload(name: str, user_prompt: str) -> str:
    picked = _rotate(_DEMO_APPS.get(name, _GEMINI_APPS), user_prompt)
    return json.dumps(
        {
            "recommendations": [
                {
                    "app_name": r[0],
                    "platform": r[1],
                    "store_url": r[2],
                    "category": r[3],
                    "score": r[4],
                    "audience_match_score": r[5],
                    "objective_fit_score": r[6],
                    "brand_safety_score": r[7],
                    "confidence": r[8],
                    "short_reason": r[9],
                    "concerns": r[10],
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
        elif task == TASK_DISCOVER_YOUTUBE:
            text = _youtube_payload(self.name, user_prompt)
        elif task == TASK_DISCOVER_APP:
            text = _apps_payload(self.name, user_prompt)
        else:
            text = "{}"
        return ProviderCallResult(provider_name=self.name, success=True, text=text)
