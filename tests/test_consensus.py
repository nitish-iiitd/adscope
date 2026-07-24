import pytest

from app.schemas.campaign import ProviderOutcome, Recommendation
from app.services.consensus_service import (
    ConsensusEntry,
    aggregate_across_queries,
    build_consensus,
    normalize_domain,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://www.Example.com/path?a=1", "example.com"),
        ("http://example.com", "example.com"),
        ("www.example.com", "example.com"),
        ("EXAMPLE.COM", "example.com"),
        ("example.com/section/page", "example.com"),
        ("lifestyle.livemint.com", "lifestyle.livemint.com"),
        ("  vogue.in  ", "vogue.in"),
    ],
)
def test_normalize_domain(raw, expected):
    assert normalize_domain(raw) == expected


def _rec(domain: str, score: float, name: str = "Site") -> Recommendation:
    return Recommendation(
        website_name=name,
        domain=domain,
        category="Lifestyle",
        score=score,
        short_reason=f"reason from score {score}",
    )


def _outcome(name: str, recs: list[Recommendation], success: bool = True) -> ProviderOutcome:
    return ProviderOutcome(provider_name=name, success=success, recommendations=recs)


def test_final_score_is_average_and_agreement_is_high_when_all_agree():
    outcomes = [
        _outcome("gemini", [_rec("example.com", 80)]),
        _outcome("groq", [_rec("www.example.com", 90)]),
        _outcome("openrouter", [_rec("https://example.com/page", 70)]),
    ]
    entries = build_consensus(outcomes)

    assert len(entries) == 1
    entry = entries[0]
    assert entry.domain == "example.com"
    assert entry.final_score == 80.0
    assert entry.model_count == 3
    assert entry.agreement == "High"
    assert len(entry.provider_details) == 3


def test_agreement_levels_across_mixed_recommendations():
    outcomes = [
        _outcome("gemini", [_rec("all.com", 90), _rec("two.com", 80), _rec("one.com", 70)]),
        _outcome("groq", [_rec("all.com", 90), _rec("two.com", 80)]),
        _outcome("openrouter", [_rec("all.com", 90)]),
    ]
    by_domain = {e.domain: e for e in build_consensus(outcomes)}

    assert by_domain["all.com"].agreement == "High"
    assert by_domain["two.com"].agreement == "Medium"
    assert by_domain["one.com"].agreement == "Low"


def test_single_successful_provider_reports_single_model():
    outcomes = [
        _outcome("gemini", [_rec("example.com", 88)]),
        _outcome("groq", [], success=False),
    ]
    entries = build_consensus(outcomes)

    assert len(entries) == 1
    assert entries[0].agreement == "Single model"
    assert entries[0].model_count == 1


def test_sorted_by_model_count_then_score():
    outcomes = [
        _outcome("gemini", [_rec("shared.com", 60), _rec("solo.com", 99)]),
        _outcome("groq", [_rec("shared.com", 60)]),
    ]
    entries = build_consensus(outcomes)

    # Two models beat a higher single-model score.
    assert [e.domain for e in entries] == ["shared.com", "solo.com"]


def test_failed_providers_are_excluded_from_consensus():
    outcomes = [
        _outcome("gemini", [_rec("example.com", 80)]),
        _outcome("groq", [_rec("example.com", 20)], success=False),
    ]
    entries = build_consensus(outcomes)

    assert entries[0].final_score == 80.0
    assert entries[0].model_count == 1


def test_all_providers_failed_yields_no_entries():
    outcomes = [
        _outcome("gemini", [], success=False),
        _outcome("groq", [], success=False),
    ]
    assert build_consensus(outcomes) == []


def test_duplicate_domain_from_one_provider_counts_once():
    outcomes = [_outcome("gemini", [_rec("example.com", 80), _rec("www.example.com", 40)])]
    entries = build_consensus(outcomes)

    assert len(entries) == 1
    assert entries[0].model_count == 1
    assert entries[0].final_score == 80.0


def test_provider_details_preserve_individual_assessments():
    outcomes = [
        _outcome("gemini", [_rec("example.com", 80, name="Example A")]),
        _outcome("groq", [_rec("example.com", 90, name="Example B")]),
    ]
    entry = build_consensus(outcomes)[0]

    scores = {d["provider_name"]: d["score"] for d in entry.provider_details}
    assert scores == {"gemini": 80.0, "groq": 90.0}
    # Name comes from the highest-scoring provider.
    assert entry.website_name == "Example B"


def _entry(domain: str, score: float, model_count: int = 2, name: str = "Site") -> ConsensusEntry:
    return ConsensusEntry(
        domain=domain,
        website_name=name,
        category="Lifestyle",
        final_score=score,
        model_count=model_count,
        agreement="High",
        combined_reason=f"reason {score}",
        provider_details=[{"provider_name": "gemini"}],
    )


class TestAggregateAcrossQueries:
    def test_breadth_beats_a_higher_single_query_score(self):
        per_query = [
            ("q1", [_entry("broad.com", 60), _entry("narrow.com", 99)]),
            ("q2", [_entry("broad.com", 62)]),
            ("q3", [_entry("broad.com", 58)]),
        ]
        results = aggregate_across_queries(per_query, max_results=50)

        top = results[0]
        assert top.domain == "broad.com"
        assert top.query_count == 3
        assert results[1].domain == "narrow.com"
        assert results[1].query_count == 1

    def test_final_score_is_mean_across_queries(self):
        per_query = [("q1", [_entry("a.com", 80)]), ("q2", [_entry("a.com", 60)])]
        results = aggregate_across_queries(per_query, max_results=50)
        assert results[0].final_score == 70.0

    def test_breadth_agreement_reflects_query_coverage(self):
        per_query = [
            ("q1", [_entry("a.com", 80), _entry("b.com", 80), _entry("c.com", 80)]),
            ("q2", [_entry("a.com", 80), _entry("b.com", 80)]),
            ("q3", [_entry("a.com", 80)]),
        ]
        by_domain = {e.domain: e for e in aggregate_across_queries(per_query, max_results=50)}
        assert by_domain["a.com"].agreement == "High"
        assert by_domain["c.com"].agreement == "Single model"

    def test_max_results_caps_the_final_list(self):
        per_query = [("q1", [_entry(f"site{i}.com", 90 - i) for i in range(10)])]
        results = aggregate_across_queries(per_query, max_results=3)
        assert len(results) == 3

    def test_provider_details_carry_per_query_breakdown(self):
        per_query = [("what is x?", [_entry("a.com", 80)])]
        entry = aggregate_across_queries(per_query, max_results=50)[0]
        assert entry.provider_details[0]["query_text"] == "what is x?"
        assert entry.provider_details[0]["providers"] == ["gemini"]

    def test_empty_input_yields_no_entries(self):
        assert aggregate_across_queries([], max_results=50) == []
