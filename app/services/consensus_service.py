from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.entities.models import PublisherType
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


def normalize_youtube(handle_or_url: str) -> str:
    """Reduce a YouTube channel reference to a normalized, usable locator.

    The same channel expressed as ``@handle``, ``youtube.com/@handle`` or a full
    URL collapses to one value of the form ``youtube.com/@handle`` (or a
    ``youtube.com/channel/UC...`` id), which doubles as the dedup key and a
    working link target.
    """
    d = (handle_or_url or "").strip().lower()
    for scheme in ("https://", "http://"):
        d = d.removeprefix(scheme)
    d = d.removeprefix("www.").removeprefix("m.")
    d = d.split("?")[0].split("#")[0]
    d = d.removeprefix("youtube.com/")
    parts = [p for p in d.split("/") if p]
    if not parts:
        return ""
    # A canonical channel id path keeps its id; c//user/ and bare handles collapse
    # to @handle, dropping any trailing path segments like /videos.
    if parts[0] == "channel" and len(parts) >= 2:
        return f"youtube.com/channel/{parts[1]}"
    slug = parts[1] if parts[0] in ("c", "user") and len(parts) >= 2 else parts[0]
    slug = slug.lstrip("@")
    return f"youtube.com/@{slug}" if slug else ""


def normalize_app(name: str) -> str:
    """Reduce an app name to a comparable slug (e.g. 'Google Maps' -> 'google-maps').

    Apps are deduped by name rather than store URL: providers describe the same
    app with different store listings (iOS vs Android, regional URLs), so the
    name is the stable cross-provider key. Platform is kept as a display detail.
    """
    return re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")


def identity_key(publisher_type: str, rec: Recommendation) -> str:
    """The normalized dedup/group key for a recommendation, per publisher type."""
    if publisher_type == PublisherType.YOUTUBE:
        return normalize_youtube(rec.handle or rec.domain)
    if publisher_type == PublisherType.APP:
        return normalize_app(rec.website_name)
    return normalize_domain(rec.domain)


def _with_scheme(url: str) -> str:
    url = (url or "").strip()
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def entry_url(publisher_type: str, key: str, best: Recommendation) -> str:
    """A clickable link for the consensus entry.

    Websites/YouTube reconstruct it from the normalized key; apps use the store
    URL the provider gave (the key is only a name slug, not a URL).
    """
    if publisher_type == PublisherType.APP:
        return _with_scheme(best.domain)
    return f"https://{key}" if key else ""


@dataclass
class ConsensusEntry:
    domain: str
    website_name: str
    category: str | None
    final_score: float
    model_count: int
    agreement: str
    combined_reason: str
    publisher_type: str = PublisherType.WEBSITE
    handle: str = ""
    url: str = ""
    query_count: int = 0
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


def build_consensus(
    outcomes: list[ProviderOutcome],
    publisher_type: str = PublisherType.WEBSITE,
) -> list[ConsensusEntry]:
    """Merge per-provider recommendations into a single ranked list.

    Matching is by the publisher's normalized identity (domain for websites,
    channel handle for YouTube). Scores are averaged across the providers that
    recommended the publisher; provider-specific assessments are preserved.
    """
    successful = [o for o in outcomes if o.success]
    successful_count = len(successful)
    if successful_count == 0:
        return []

    grouped: dict[str, list[tuple[str, Recommendation]]] = {}
    for outcome in successful:
        seen_in_this_provider: set[str] = set()
        for rec in outcome.recommendations:
            key = identity_key(publisher_type, rec)
            if not key or key in seen_in_this_provider:
                continue  # ignore blanks and duplicates from one provider
            seen_in_this_provider.add(key)
            grouped.setdefault(key, []).append((outcome.provider_name, rec))

    entries: list[ConsensusEntry] = []
    for key, recs in grouped.items():
        model_count = len(recs)
        final_score = round(sum(rec.score for _, rec in recs) / model_count, 1)
        best = max(recs, key=lambda pair: pair[1].score)[1]
        entries.append(
            ConsensusEntry(
                domain=key,  # normalized locator (also the group key)
                website_name=_pick_website_name(recs),
                category=_pick_category(recs),
                final_score=final_score,
                model_count=model_count,
                agreement=_agreement_level(model_count, successful_count),
                combined_reason=_combined_reason(recs),
                publisher_type=publisher_type,
                handle=best.handle,
                url=entry_url(publisher_type, key, best),
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


def _breadth_agreement(query_count: int, total_queries: int) -> str:
    """How broadly a site was surfaced across the refined query set."""
    if total_queries <= 1 or query_count <= 1:
        return AGREEMENT_SINGLE
    ratio = query_count / total_queries
    if ratio >= 0.66:
        return AGREEMENT_HIGH
    if ratio >= 0.33:
        return AGREEMENT_MEDIUM
    return AGREEMENT_LOW


def aggregate_across_queries(
    per_query: list[tuple[str, list[ConsensusEntry]]],
    max_results: int,
    publisher_type: str = PublisherType.WEBSITE,
) -> list[ConsensusEntry]:
    """Merge the per-query ranked lists (service-2 level 2) into one final list.

    Each input is ``(query_text, entries)`` where ``entries`` is the level-1
    consensus for that query. Sites are grouped by normalized domain; a site
    surfaced by more queries ranks higher (breadth), with mean score as the
    tie-breaker. ``provider_details`` carries a per-query breakdown for drill-down.
    """
    total_queries = len(per_query)
    grouped: dict[str, list[tuple[str, ConsensusEntry]]] = {}
    for query_text, entries in per_query:
        for entry in entries:
            grouped.setdefault(entry.domain, []).append((query_text, entry))

    results: list[ConsensusEntry] = []
    for domain, items in grouped.items():
        query_count = len(items)
        scores = [e.final_score for _, e in items]
        final_score = round(sum(scores) / len(scores), 1)
        best = max(items, key=lambda pair: pair[1].final_score)[1]
        model_count = max(e.model_count for _, e in items)
        results.append(
            ConsensusEntry(
                domain=domain,
                website_name=best.website_name,
                category=best.category,
                final_score=final_score,
                model_count=model_count,
                query_count=query_count,
                agreement=_breadth_agreement(query_count, total_queries),
                combined_reason=best.combined_reason,
                publisher_type=publisher_type,
                handle=best.handle,
                url=best.url,
                provider_details=[
                    {
                        "query_text": query_text,
                        "score": entry.final_score,
                        "model_count": entry.model_count,
                        "providers": [d["provider_name"] for d in entry.provider_details],
                    }
                    for query_text, entry in sorted(
                        items, key=lambda pair: -pair[1].final_score
                    )
                ],
            )
        )

    results.sort(key=lambda e: (-e.query_count, -e.final_score, e.domain))
    return results[:max_results]
