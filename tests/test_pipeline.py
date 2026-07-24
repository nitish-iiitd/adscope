import pytest

from app.config import Settings
from app.entities.models import Campaign, GeneratedQuery
from app.services.query_service import _parse_queries, generate_queries
from app.services.site_discovery_service import _parse_sites, discover_sites


def _campaign() -> Campaign:
    return Campaign(
        id=1,
        client_name="Verdant Skincare",
        campaign_name="Monsoon Awareness",
        briefing="A premium organic skincare company targeting women 25-40 in Indian metros.",
        target_country="India",
    )


class TestParseQueries:
    def test_parses_plain_string_list(self):
        assert _parse_queries('{"queries": ["a?", "b?"]}', limit=10) == ["a?", "b?"]

    def test_parses_object_list(self):
        text = '{"queries": [{"query": "a?"}, {"text": "b?"}]}'
        assert _parse_queries(text, limit=10) == ["a?", "b?"]

    def test_dedupes_case_insensitively(self):
        assert _parse_queries('{"queries": ["A?", "a?"]}', limit=10) == ["A?"]

    def test_respects_limit(self):
        assert _parse_queries('{"queries": ["a", "b", "c"]}', limit=2) == ["a", "b"]

    def test_bad_json_returns_empty(self):
        assert _parse_queries("not json", limit=10) == []


class TestParseSites:
    def test_parses_recommendations(self):
        text = '{"recommendations": [{"website_name": "A", "domain": "a.com", "score": 80}]}'
        recs = _parse_sites(text, limit=10)
        assert len(recs) == 1
        assert recs[0].domain == "a.com"

    def test_skips_bad_items_but_keeps_good_ones(self):
        text = (
            '{"recommendations": ['
            '{"website_name": "A", "domain": "a.com", "score": 80},'
            '{"website_name": "B", "domain": "b.com", "score": 500}]}'  # 500 is invalid
        )
        recs = _parse_sites(text, limit=10)
        assert [r.domain for r in recs] == ["a.com"]

    def test_respects_limit(self):
        items = ",".join(f'{{"website_name":"S","domain":"s{i}.com","score":50}}' for i in range(5))
        recs = _parse_sites(f'{{"recommendations": [{items}]}}', limit=2)
        assert len(recs) == 2

    def test_bad_json_returns_empty(self):
        assert _parse_sites("nope", limit=10) == []


@pytest.mark.anyio
async def test_generate_queries_combines_all_providers():
    settings = Settings(demo_mode=True, queries_per_provider=10)
    output = await generate_queries(_campaign(), settings)

    assert len(output.provider_results) == 3
    assert all(r.success for r in output.provider_results)
    # 3 providers x 10 distinct queries each.
    assert len(output.drafts) == 30
    assert {d.source_provider for d in output.drafts} == {"gemini", "groq", "openrouter"}


@pytest.mark.anyio
async def test_discover_sites_produces_final_ranking():
    settings = Settings(demo_mode=True)
    queries = [
        GeneratedQuery(id=1, text="best organic skincare in India?"),
        GeneratedQuery(id=2, text="clean beauty review sites?"),
    ]
    output = await discover_sites(queries, settings)

    assert output.total_calls == 2 * 3  # queries x providers
    assert output.successful_calls > 0
    assert output.final_entries
    assert all(e.query_count >= 1 for e in output.final_entries)
    # Vogue is in every demo provider set, so it should surface.
    assert any(e.domain == "vogue.in" for e in output.final_entries)
    # Intermediate per-query results are recorded for drill-down.
    assert len(output.query_results) == output.total_calls
