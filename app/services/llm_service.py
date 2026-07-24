from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Iterable
from typing import TypeVar

from app.config import Settings
from app.providers.base import BaseProvider
from app.providers.demo import DemoProvider
from app.providers.registry import PROVIDER_REGISTRY

logger = logging.getLogger(__name__)

T = TypeVar("T")


class NoProvidersConfiguredError(RuntimeError):
    """Raised when demo mode is off and no provider has an API key."""


def build_providers(settings: Settings) -> list[BaseProvider]:
    """Instantiate the enabled providers from the config-driven registry.

    Demo mode returns a DemoProvider for every configured entry so the whole
    pipeline runs offline.
    """
    configs = settings.provider_configs()

    if settings.demo_mode:
        return [DemoProvider(c.label, settings.llm_timeout_seconds) for c in configs]

    providers: list[BaseProvider] = []
    for c in configs:
        if not c.enabled or not c.api_key:
            continue
        provider_cls = PROVIDER_REGISTRY.get(c.type)
        if provider_cls is None:
            logger.warning("Unknown provider type %r - skipping", c.type)
            continue
        providers.append(
            provider_cls(c.api_key, c.model, settings.llm_timeout_seconds, name=c.label)
        )
    return providers


def require_providers(settings: Settings) -> list[BaseProvider]:
    providers = build_providers(settings)
    if not providers:
        raise NoProvidersConfiguredError(
            "No LLM providers are configured. Add an API key or enable DEMO_MODE."
        )
    return providers


async def gather_bounded(coros: Iterable[Awaitable[T]], limit: int) -> list[T]:
    """Run awaitables concurrently, but never more than ``limit`` at once.

    Service-2 fans out to (queries x providers) calls, so an unbounded gather
    would hammer provider rate limits. Order of results matches input order.
    """
    semaphore = asyncio.Semaphore(max(1, limit))

    async def _run(coro: Awaitable[T]) -> T:
        async with semaphore:
            return await coro

    return list(await asyncio.gather(*(_run(c) for c in coros)))
