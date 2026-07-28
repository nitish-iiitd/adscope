"""Competitor exclusion for the discovery stage.

The output list is a media-buying list, and a competitor will not sell ad space
to this client - so a competitor-owned site, channel or app in the results is
not merely awkward, it is unbuyable. Two mechanisms work together:

1. the discovery prompt asks the models to leave competitors out
   (see ``competitor_exclusion_clause`` in ``prompts.py``), and
2. this module removes anything that still comes back, because models follow
   negative instructions unreliably.

Matching is deliberately name-based and slightly generous: a false negative
leaves an unusable row in a buying list, while a false positive only drops a
publisher the planner explicitly named as a competitor.
"""

from __future__ import annotations

import re

from app.entities.models import PublisherType
from app.schemas.campaign import Recommendation

_SEPARATORS = re.compile(r"[,\n;|]+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# Words that carry no identity on their own - matching on them alone would drop
# half the list ("The Beauty Company" must not match every publisher). Only
# articles, legal suffixes and URL noise belong here: words like "shop" or
# "store" are part of real brand names ("The Body Shop") and must be kept.
GENERIC_TOKENS = frozenset(
    {
        "the", "a", "an", "and", "of",
        "inc", "llc", "ltd", "limited", "plc", "corp", "corporation", "co",
        "pvt", "private", "gmbh", "sa", "ag", "bv", "nv",
        "company", "companies", "holdings", "official",
        "com", "net", "org", "www",
    }
)

# A one-word competitor shorter than this is too generic to match on.
MIN_TOKEN_LENGTH = 3
# Domains and handles run brand names together ("kamaayurveda.com",
# "@NykaaBeauty"), so the name is also matched as a substring. That is a looser
# test, so it needs a longer name before it is trusted.
MIN_SUBSTRING_LENGTH = 5


def parse_competitors(raw: str | None) -> list[str]:
    """Split the free-text competitor field into individual brand names."""
    if not raw:
        return []
    names: list[str] = []
    seen: set[str] = set()
    for chunk in _SEPARATORS.split(raw):
        name = chunk.strip()
        key = name.lower()
        if name and key not in seen:
            seen.add(key)
            names.append(name)
    return names


def _tokens(value: str) -> set[str]:
    return {t for t in _NON_ALNUM.split((value or "").lower()) if t}


def _identifying_tokens(name: str) -> list[str]:
    """The words of a brand name that actually identify it, in order."""
    tokens = [t for t in _NON_ALNUM.split((name or "").lower()) if t]
    significant = [t for t in tokens if t not in GENERIC_TOKENS]
    # A name made entirely of generic words (e.g. "The Company Ltd") keeps them
    # rather than becoming a match-everything empty list.
    return significant or tokens


def _domain_tokens(domain: str) -> set[str]:
    """Tokens from a bare domain, ignoring the public suffix.

    ``vogue.in`` -> ``{"vogue"}``. The suffix is dropped so a competitor called
    "IN" or "Co" cannot match every domain in the list.
    """
    host = (domain or "").strip().lower()
    for scheme in ("https://", "http://"):
        host = host.removeprefix(scheme)
    host = host.split("/")[0].split("?")[0].removeprefix("www.")
    labels = [label for label in host.split(".") if label]
    if len(labels) > 1:
        labels = labels[:-1]  # drop the TLD, keep any subdomains
    return {t for label in labels for t in _tokens(label)}


def _candidate_tokens(publisher_type: str, rec: Recommendation) -> set[str]:
    """Tokens describing a recommendation, per type.

    Apps deliberately contribute only their name: their ``domain`` holds a store
    URL, so including it would make every iOS listing look like it belongs to
    Apple.
    """
    tokens = _tokens(rec.website_name)
    if publisher_type == PublisherType.YOUTUBE:
        tokens |= _tokens(rec.handle)
    elif publisher_type != PublisherType.APP:
        tokens |= _domain_tokens(rec.domain)
    return tokens


def is_competitor(publisher_type: str, rec: Recommendation, competitors: list[str]) -> bool:
    """True when the recommendation looks like a property of a named competitor.

    Two tests, either of which is enough:

    * every identifying word of the competitor appears as a word in the
      publisher's name (plus its domain or handle) - so "Body Shop" matches
      *The Body Shop India* but not an unrelated *Body Positive* blog; and
    * the competitor's name, run together, appears inside one of those words -
      so "Kama Ayurveda" matches ``kamaayurveda.com`` and "Nykaa" matches
      ``@NykaaBeauty``.
    """
    candidate = _candidate_tokens(publisher_type, rec)
    if not candidate:
        return False

    for name in competitors:
        wanted = _identifying_tokens(name)
        if not wanted:
            continue
        if len(wanted) > 1 or len(wanted[0]) >= MIN_TOKEN_LENGTH:
            if set(wanted) <= candidate:
                return True
        compact = "".join(wanted)
        if len(compact) >= MIN_SUBSTRING_LENGTH and any(compact in t for t in candidate):
            return True
    return False


def filter_competitors(
    recs: list[Recommendation], publisher_type: str, competitors: list[str]
) -> tuple[list[Recommendation], int]:
    """Drop competitor-owned publishers. Returns the survivors and how many went."""
    if not competitors:
        return recs, 0
    kept = [r for r in recs if not is_competitor(publisher_type, r, competitors)]
    return kept, len(recs) - len(kept)
