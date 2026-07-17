from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.campaign import ProviderOutcome, Recommendation

AGREEMENT_HIGH = "High"
AGREEMENT_MEDIUM = "Medium"
AGREEMENT_LOW = "Low"
AGREEMENT_SINGLE = "Single model"


def normalize_domain(domain: str) -> str:
    """Reduce a domain to a comparable key: no scheme, no www., no path, lowercase."""
    d = (domain or "").strip().lower()
    for scheme in ("https://", "http://"):
        if d.startswith(scheme):
            d = d.removeprefix(scheme)
    d = d.split("/")[0]  # drop path
    d = d.split("?")[0].split("#")[0]
    d = d.removeprefix("www.")
    return d.strip().strip(".")


@dataclass
class ConsensusEntry:
    domain: str
    website_name: str
    category: str | None
    final_score: float
    model_count: int
    agreement: str
    combined_reason: str
    provider_details: list[dict] = field(default_factory=list)


def _pick_website_name(recs: list[tuple[str, Recommendation]]) -> str:
    """Use the name from the highest-scoring provider for this domain."""
    return max(recs, key=lambda pair: pair[1].score)[1].website_name


def _pick_category(recs: list[tuple[str, Recommendation]]) -> str | None:
    for _, rec in sorted(recs, key=lambda pair: pair[1].score, reverse=True):
        if rec.category:
            return rec.category
    return None


def _combined_reason(recs: list[tuple[str, Recommendation]]) -> str:
    """Surface the reason given by the provider that scored the site highest."""
    best = max(recs, key=lambda pair: pair[1].score)[1]
    return best.short_reason or ""


def _agreement_level(model_count: int, successful_count: int) -> str:
    if successful_count == 1:
        return AGREEMENT_SINGLE
    if model_count == successful_count:
        return AGREEMENT_HIGH
    if model_count >= 2:
        return AGREEMENT_MEDIUM
    return AGREEMENT_LOW


def build_consensus(outcomes: list[ProviderOutcome]) -> list[ConsensusEntry]:
    """Merge per-provider recommendations into a single ranked list.

    Matching is by normalized domain. Scores are averaged across the providers
    that recommended the site; provider-specific assessments are preserved.
    """
    successful = [o for o in outcomes if o.success]
    successful_count = len(successful)
    if successful_count == 0:
        return []

    grouped: dict[str, list[tuple[str, Recommendation]]] = {}
    for outcome in successful:
        seen_in_this_provider: set[str] = set()
        for rec in outcome.recommendations:
            key = normalize_domain(rec.domain)
            if not key or key in seen_in_this_provider:
                continue  # ignore blanks and duplicate domains from one provider
            seen_in_this_provider.add(key)
            grouped.setdefault(key, []).append((outcome.provider_name, rec))

    entries: list[ConsensusEntry] = []
    for domain, recs in grouped.items():
        model_count = len(recs)
        final_score = round(sum(rec.score for _, rec in recs) / model_count, 1)
        entries.append(
            ConsensusEntry(
                domain=domain,
                website_name=_pick_website_name(recs),
                category=_pick_category(recs),
                final_score=final_score,
                model_count=model_count,
                agreement=_agreement_level(model_count, successful_count),
                combined_reason=_combined_reason(recs),
                provider_details=[
                    {
                        "provider_name": provider_name,
                        "website_name": rec.website_name,
                        "domain": rec.domain,
                        "category": rec.category,
                        "score": rec.score,
                        "audience_match_score": rec.audience_match_score,
                        "objective_fit_score": rec.objective_fit_score,
                        "brand_safety_score": rec.brand_safety_score,
                        "short_reason": rec.short_reason,
                        "concerns": rec.concerns,
                        "confidence": rec.confidence,
                    }
                    for provider_name, rec in sorted(recs, key=lambda pair: pair[0])
                ],
            )
        )

    entries.sort(key=lambda e: (-e.model_count, -e.final_score, e.domain))
    return entries
