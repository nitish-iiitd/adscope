"""Registry mapping a provider ``type`` to its implementation class.

To add a new LLM provider, implement a BaseProvider subclass and register it
here. Everything else (config, building, both services) is driven off this map.
"""

from __future__ import annotations

from app.providers.base import BaseProvider
from app.providers.gemini import GeminiProvider
from app.providers.groq import GroqProvider
from app.providers.openrouter import OpenRouterProvider

PROVIDER_REGISTRY: dict[str, type[BaseProvider]] = {
    "gemini": GeminiProvider,
    "groq": GroqProvider,
    "openrouter": OpenRouterProvider,
}
