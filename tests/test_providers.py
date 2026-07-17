import asyncio
import time

import httpx
import pytest

from app.config import Settings
from app.entities.models import Campaign
from app.providers.base import BaseProvider, extract_json
from app.services.llm_service import NoProvidersConfiguredError, build_providers, run_providers

VALID_PAYLOAD = '{"recommendations": [{"website_name": "A", "domain": "a.com", "score": 80}]}'


def _campaign() -> Campaign:
    return Campaign(
        id=1,
        client_name="Client",
        campaign_name="Campaign",
        briefing="A briefing that is long enough to be valid.",
        target_country="India",
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

    async def _call_api(self, client, prompt):
        if self._error:
            raise self._error
        return self._response


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.com")
    response = httpx.Response(status, request=request, text="error body")
    return httpx.HTTPStatusError("error", request=request, response=response)


@pytest.mark.anyio
async def test_provider_success():
    outcome = await _StubProvider(response=VALID_PAYLOAD).generate(_campaign())

    assert outcome.success is True
    assert len(outcome.recommendations) == 1
    assert outcome.recommendations[0].domain == "a.com"


@pytest.mark.anyio
async def test_provider_timeout_is_a_failed_outcome():
    outcome = await _StubProvider(error=httpx.TimeoutException("timed out")).generate(_campaign())

    assert outcome.success is False
    assert "timed out" in outcome.error_message


@pytest.mark.anyio
async def test_slow_provider_is_cut_off_at_the_configured_timeout():
    """A provider that streams slowly must still be bound by LLM_TIMEOUT_SECONDS."""

    class _SlowProvider(_StubProvider):
        async def _call_api(self, client, prompt):
            await asyncio.sleep(5)  # far longer than the 1s timeout below
            return VALID_PAYLOAD

    provider = _SlowProvider(response=VALID_PAYLOAD)
    provider.timeout = 1

    started = time.perf_counter()
    outcome = await provider.generate(_campaign())
    elapsed = time.perf_counter() - started

    assert outcome.success is False
    assert "timed out" in outcome.error_message
    assert elapsed < 3  # cut off at ~1s, not after the full 5s sleep


@pytest.mark.anyio
async def test_provider_auth_failure_message():
    outcome = await _StubProvider(error=_http_error(401)).generate(_campaign())

    assert outcome.success is False
    assert "Authentication failed" in outcome.error_message


@pytest.mark.anyio
async def test_provider_rate_limit_message():
    outcome = await _StubProvider(error=_http_error(429)).generate(_campaign())

    assert outcome.success is False
    assert "Rate limit" in outcome.error_message


@pytest.mark.anyio
async def test_provider_invalid_json_is_a_failed_outcome_not_a_crash():
    outcome = await _StubProvider(response="I cannot help with that.").generate(_campaign())

    assert outcome.success is False
    assert "invalid" in outcome.error_message.lower()
    assert outcome.raw_response == "I cannot help with that."


@pytest.mark.anyio
async def test_provider_schema_violation_is_a_failed_outcome():
    # score above 100 violates the schema
    outcome = await _StubProvider(
        response='{"recommendations": [{"website_name": "A", "domain": "a.com", "score": 500}]}'
    ).generate(_campaign())

    assert outcome.success is False


@pytest.mark.anyio
async def test_json_wrapped_in_prose_still_succeeds():
    outcome = await _StubProvider(response=f"Sure!\n```json\n{VALID_PAYLOAD}\n```").generate(_campaign())

    assert outcome.success is True


class TestBuildProviders:
    def test_demo_mode_enables_all_three(self):
        providers = build_providers(Settings(demo_mode=True))
        assert [p.name for p in providers] == ["gemini", "groq", "openrouter"]

    def test_only_configured_providers_are_enabled(self):
        settings = Settings(demo_mode=False, groq_api_key="key", gemini_api_key="", openrouter_api_key="")
        providers = build_providers(settings)
        assert [p.name for p in providers] == ["groq"]

    def test_no_keys_and_no_demo_mode_yields_nothing(self):
        settings = Settings(demo_mode=False, gemini_api_key="", groq_api_key="", openrouter_api_key="")
        assert build_providers(settings) == []


@pytest.mark.anyio
async def test_run_providers_errors_when_none_configured():
    settings = Settings(demo_mode=False, gemini_api_key="", groq_api_key="", openrouter_api_key="")
    with pytest.raises(NoProvidersConfiguredError):
        await run_providers(_campaign(), settings)


@pytest.mark.anyio
async def test_single_provider_is_enough():
    settings = Settings(demo_mode=False, groq_api_key="key", gemini_api_key="", openrouter_api_key="")
    providers = build_providers(settings)
    assert len(providers) == 1
