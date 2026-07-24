from __future__ import annotations

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod

import httpx
from pydantic import ValidationError  # noqa: F401  (re-exported for services that parse)

from app.schemas.campaign import ProviderCallResult

logger = logging.getLogger(__name__)

# Task hints passed to complete(). Real providers ignore them; the demo provider
# uses them to decide which canned payload to return.
TASK_GENERATE_QUERIES = "generate_queries"
TASK_DISCOVER_SITES = "discover_sites"


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
    """Shared provider contract: a task-agnostic completion primitive.

    Subclasses only implement the HTTP call (``_call_api``) and return raw text.
    Timeout handling and error shaping live here so every provider fails the
    same way. Services own their prompts and their response parsing.
    """

    name: str = "base"

    def __init__(self, api_key: str, model: str, timeout: int, name: str | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        if name is not None:
            self.name = name

    @abstractmethod
    async def _call_api(self, client: httpx.AsyncClient, system_prompt: str, user_prompt: str) -> str:
        """Send the prompts and return the model's raw text output."""

    async def complete(
        self, system_prompt: str, user_prompt: str, *, task: str | None = None
    ) -> ProviderCallResult:
        """Run one completion, returning raw text or a shaped error - never raises.

        ``task`` is an optional hint (see the TASK_* constants) that real
        providers ignore; it lets the demo provider pick canned output.
        """
        raw: str | None = None
        try:
            # httpx's timeout applies per socket read, so a model that trickles tokens
            # back can run far past it. asyncio.timeout bounds the whole call instead,
            # which is what LLM_TIMEOUT_SECONDS is meant to promise.
            async with asyncio.timeout(self.timeout):
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    raw = await self._call_api(client, system_prompt, user_prompt)
            return ProviderCallResult(provider_name=self.name, success=True, text=raw)
        except (httpx.TimeoutException, TimeoutError):
            logger.warning("%s timed out after %ss", self.name, self.timeout)
            return self._failure(f"Provider timed out after {self.timeout}s")
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (401, 403):
                message = "Authentication failed - check the API key"
            elif status == 429:
                message = "Rate limit exceeded"
            else:
                message = f"Provider returned HTTP {status}"
            logger.warning("%s HTTP error %s: %s", self.name, status, exc.response.text[:500])
            return self._failure(message)
        except httpx.HTTPError as exc:
            logger.warning("%s network error: %s", self.name, exc)
            return self._failure("Could not reach the provider")
        except Exception as exc:  # last resort: one provider must never fail the run
            logger.exception("%s failed unexpectedly: %s", self.name, exc)
            return self._failure("Unexpected provider error")

    def _failure(self, message: str) -> ProviderCallResult:
        return ProviderCallResult(provider_name=self.name, success=False, error_message=message)
