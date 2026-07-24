import asyncio
import time

import httpx
import pytest

from app.config import Settings
from app.providers.base import BaseProvider, extract_json
from app.providers.registry import PROVIDER_REGISTRY
from app.services.llm_service import (
    NoProvidersConfiguredError,
    build_providers,
    gather_bounded,
    require_providers,
)


class TestExtractJson:
    def test_plain_json(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_markdown_fenced_json(self):
        assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_json_surrounded_by_prose(self):
        text = 'Here are the results:\n{"a": {"b": 2}}\nHope this helps!'
        assert extract_json(text) == {"a": {"b": 2}}

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError):
            extract_json("no json at all")

    def test_unbalanced_json_raises(self):
        with pytest.raises(ValueError):
            extract_json('{"a": 1')


class _StubProvider(BaseProvider):
    """Returns a canned response or raises a canned error, without real HTTP."""

    name = "stub"

    def __init__(self, response: str | None = None, error: Exception | None = None):
        super().__init__(api_key="k", model="m", timeout=5)
        self._response = response
        self._error = error

    async def _call_api(self, client, system_prompt, user_prompt):
        if self._error:
            raise self._error
        return self._response


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.com")
    response = httpx.Response(status, request=request, text="error body")
    return httpx.HTTPStatusError("error", request=request, response=response)


@pytest.mark.anyio
async def test_complete_success_returns_raw_text():
    result = await _StubProvider(response='{"ok": true}').complete("sys", "user")
    assert result.success is True
    assert result.text == '{"ok": true}'
    assert result.provider_name == "stub"


@pytest.mark.anyio
async def test_complete_timeout_is_a_failed_result():
    result = await _StubProvider(error=httpx.TimeoutException("timed out")).complete("s", "u")
    assert result.success is False
    assert "timed out" in result.error_message


@pytest.mark.anyio
async def test_slow_provider_is_cut_off_at_the_configured_timeout():
    class _SlowProvider(_StubProvider):
        async def _call_api(self, client, system_prompt, user_prompt):
            await asyncio.sleep(5)
            return "{}"

    provider = _SlowProvider(response="{}")
    provider.timeout = 1

    started = time.perf_counter()
    result = await provider.complete("s", "u")
    elapsed = time.perf_counter() - started

    assert result.success is False
    assert "timed out" in result.error_message
    assert elapsed < 3


@pytest.mark.anyio
async def test_complete_auth_failure_message():
    result = await _StubProvider(error=_http_error(401)).complete("s", "u")
    assert result.success is False
    assert "Authentication failed" in result.error_message


@pytest.mark.anyio
async def test_complete_rate_limit_message():
    result = await _StubProvider(error=_http_error(429)).complete("s", "u")
    assert result.success is False
    assert "Rate limit" in result.error_message


@pytest.mark.anyio
async def test_gather_bounded_preserves_order_and_bounds_concurrency():
    active = 0
    peak = 0

    async def job(value: int) -> int:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return value

    results = await gather_bounded((job(i) for i in range(10)), limit=3)
    assert results == list(range(10))
    assert peak <= 3


class TestBuildProviders:
    def test_registry_covers_the_configured_types(self):
        types = {c.type for c in Settings().provider_configs()}
        assert types <= set(PROVIDER_REGISTRY)

    def test_demo_mode_enables_all_configured(self):
        providers = build_providers(Settings(demo_mode=True))
        assert [p.name for p in providers] == ["gemini", "groq", "openrouter"]

    def test_only_configured_providers_are_enabled(self):
        settings = Settings(demo_mode=False, groq_api_key="key", gemini_api_key="", openrouter_api_key="")
        providers = build_providers(settings)
        assert [p.name for p in providers] == ["groq"]

    def test_no_keys_and_no_demo_mode_yields_nothing(self):
        settings = Settings(demo_mode=False, gemini_api_key="", groq_api_key="", openrouter_api_key="")
        assert build_providers(settings) == []


def test_require_providers_errors_when_none_configured():
    settings = Settings(demo_mode=False, gemini_api_key="", groq_api_key="", openrouter_api_key="")
    with pytest.raises(NoProvidersConfiguredError):
        require_providers(settings)
