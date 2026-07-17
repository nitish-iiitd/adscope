import asyncio
import logging

from app.config import Settings
from app.entities.models import Campaign
from app.providers.base import BaseProvider
from app.providers.demo import DemoProvider
from app.providers.gemini import GeminiProvider
from app.providers.groq import GroqProvider
from app.providers.openrouter import OpenRouterProvider
from app.schemas.campaign import ProviderOutcome

logger = logging.getLogger(__name__)

PROVIDER_NAMES = ("gemini", "groq", "openrouter")


class NoProvidersConfiguredError(RuntimeError):
    """Raised when demo mode is off and no provider has an API key."""


def build_providers(settings: Settings) -> list[BaseProvider]:
    """Return the enabled providers. Demo mode always enables all three."""
    if settings.demo_mode:
        return [DemoProvider(name, settings.llm_timeout_seconds) for name in PROVIDER_NAMES]

    providers: list[BaseProvider] = []
    if settings.gemini_api_key:
        providers.append(
            GeminiProvider(settings.gemini_api_key, settings.gemini_model, settings.llm_timeout_seconds)
        )
    if settings.groq_api_key:
        providers.append(
            GroqProvider(settings.groq_api_key, settings.groq_model, settings.llm_timeout_seconds)
        )
    if settings.openrouter_api_key:
        providers.append(
            OpenRouterProvider(
                settings.openrouter_api_key, settings.openrouter_model, settings.llm_timeout_seconds
            )
        )
    return providers


async def run_providers(campaign: Campaign, settings: Settings) -> list[ProviderOutcome]:
    """Query every enabled provider concurrently and return one outcome each."""
    providers = build_providers(settings)
    if not providers:
        raise NoProvidersConfiguredError(
            "No LLM providers are configured. Add an API key or enable DEMO_MODE."
        )

    logger.info("Running %d provider(s) for campaign %s", len(providers), campaign.id)
    outcomes = await asyncio.gather(*(p.generate(campaign) for p in providers))
    return list(outcomes)
