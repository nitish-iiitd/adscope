from app.entities.models import PublisherType
from app.schemas.campaign import Recommendation
from app.services.competitor_service import (
    filter_competitors,
    is_competitor,
    parse_competitors,
)


def _site(name: str, domain: str) -> Recommendation:
    return Recommendation(website_name=name, domain=domain, score=80)


def _channel(name: str, handle: str) -> Recommendation:
    return Recommendation(
        publisher_type=PublisherType.YOUTUBE,
        website_name=name,
        domain=f"youtube.com/{handle}",
        handle=handle,
        score=80,
    )


def _app(name: str, store_url: str) -> Recommendation:
    return Recommendation(
        publisher_type=PublisherType.APP, website_name=name, domain=store_url, score=80
    )


class TestParseCompetitors:
    def test_splits_on_commas_and_newlines(self):
        assert parse_competitors("Nykaa, Purplle\nBiotique") == ["Nykaa", "Purplle", "Biotique"]

    def test_dedupes_case_insensitively_and_drops_blanks(self):
        assert parse_competitors("Nykaa, ,nykaa,, Purplle") == ["Nykaa", "Purplle"]

    def test_empty_input(self):
        assert parse_competitors(None) == []
        assert parse_competitors("   ") == []


class TestIsCompetitor:
    def test_matches_on_name(self):
        assert is_competitor(PublisherType.WEBSITE, _site("Nykaa", "nykaa.com"), ["Nykaa"])

    def test_matches_on_domain_when_name_differs(self):
        rec = _site("Beauty Store", "kamaayurveda.com")
        assert is_competitor(PublisherType.WEBSITE, rec, ["Kama Ayurveda"])

    def test_matches_a_longer_variant_of_the_brand(self):
        rec = _site("The Body Shop India", "thebodyshop.in")
        assert is_competitor(PublisherType.WEBSITE, rec, ["Body Shop"])

    def test_does_not_match_an_unrelated_publisher(self):
        rec = _site("Body Positive Blog", "bodypositive.com")
        assert not is_competitor(PublisherType.WEBSITE, rec, ["Body Shop"])

    def test_requires_every_identifying_word(self):
        # "Forest" alone is not "Forest Essentials".
        rec = _site("Forest Trails", "foresttrails.com")
        assert not is_competitor(PublisherType.WEBSITE, rec, ["Forest Essentials"])

    def test_tld_is_not_matchable(self):
        # A competitor called "IN" must not match every .in domain.
        assert not is_competitor(PublisherType.WEBSITE, _site("Vogue India", "vogue.in"), ["IN"])

    def test_generic_words_alone_do_not_match(self):
        rec = _site("Femina", "femina.in")
        assert not is_competitor(PublisherType.WEBSITE, rec, ["The Company Ltd"])

    def test_youtube_matches_on_handle(self):
        rec = _channel("Skincare Daily", "@NykaaBeauty")
        assert is_competitor(PublisherType.YOUTUBE, rec, ["Nykaa"])

    def test_app_store_url_is_never_matched(self):
        # The store host would otherwise make every Play listing a "Google" property.
        rec = _app("Nykaa", "https://play.google.com/store/apps/details?id=com.fsn.nykaa")
        assert not is_competitor(PublisherType.APP, rec, ["Google"])
        assert is_competitor(PublisherType.APP, rec, ["Nykaa"])


class TestFilterCompetitors:
    def test_removes_matches_and_reports_the_count(self):
        recs = [_site("Nykaa", "nykaa.com"), _site("Vogue India", "vogue.in")]
        kept, dropped = filter_competitors(recs, PublisherType.WEBSITE, ["Nykaa"])

        assert [r.website_name for r in kept] == ["Vogue India"]
        assert dropped == 1

    def test_no_competitors_is_a_passthrough(self):
        recs = [_site("Nykaa", "nykaa.com")]
        kept, dropped = filter_competitors(recs, PublisherType.WEBSITE, [])

        assert kept == recs
        assert dropped == 0
