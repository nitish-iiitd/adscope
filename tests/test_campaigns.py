import csv
import io

import pytest

from app.entities.models import Campaign, CampaignStatus
from app.schemas.campaign import ProviderOutcome
from app.services.campaign_service import resolve_status

VALID_FORM = {
    "client_name": "Verdant Skincare",
    "campaign_name": "Monsoon Awareness",
    "briefing": (
        "A premium organic skincare company wants to target women aged 25-40 in major Indian "
        "cities. The campaign objective is brand awareness."
    ),
    "target_country": "India",
    "objective": "Brand awareness",
    "budget": "INR 20,00,000",
}


def _create_campaign(client, **overrides):
    data = {**VALID_FORM, **overrides}
    return client.post("/campaigns", data=data, follow_redirects=False)


def test_create_campaign_in_demo_mode(auth_client, db):
    response = _create_campaign(auth_client)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/campaigns/")

    campaign = db.query(Campaign).one()
    assert campaign.status == CampaignStatus.COMPLETED
    assert campaign.client_name == "Verdant Skincare"
    assert len(campaign.provider_results) == 3
    assert len(campaign.recommendations) > 0

    # All three demo providers recommend Vogue India, so it should rank first.
    top = max(campaign.recommendations, key=lambda r: (r.model_count, r.final_score))
    assert top.domain == "vogue.in"
    assert top.agreement == "High"


def test_campaign_results_page_renders(auth_client):
    location = _create_campaign(auth_client).headers["location"]
    response = auth_client.get(location)

    assert response.status_code == 200
    assert "Verdant Skincare" in response.text
    assert "vogue.in" in response.text
    assert "AI-generated recommendations are advisory" in response.text
    assert "Export CSV" in response.text


def test_dashboard_lists_campaign_and_counts_it(auth_client):
    _create_campaign(auth_client)
    response = auth_client.get("/")

    assert response.status_code == 200
    assert "Monsoon Awareness" in response.text
    assert "Completed" in response.text


@pytest.mark.parametrize("missing_field", ["client_name", "campaign_name", "briefing", "target_country"])
def test_missing_required_field_is_rejected(auth_client, db, missing_field):
    response = _create_campaign(auth_client, **{missing_field: ""})

    assert response.status_code == 400
    assert "is required" in response.text
    assert db.query(Campaign).count() == 0


def test_short_briefing_is_rejected(auth_client):
    response = _create_campaign(auth_client, briefing="too short")
    assert response.status_code == 400
    assert "at least 20 characters" in response.text


def test_oversized_briefing_is_rejected(auth_client):
    response = _create_campaign(auth_client, briefing="x" * 5001)
    assert response.status_code == 400
    assert "5000 characters or fewer" in response.text


def test_csv_export(auth_client):
    location = _create_campaign(auth_client).headers["location"]
    response = auth_client.get(f"{location}/export.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert "monsoon-awareness" in response.headers["content-disposition"]

    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0] == [
        "Rank",
        "Website name",
        "Domain",
        "Category",
        "Final score",
        "Model count",
        "Agreement",
        "Combined reason",
    ]
    assert len(rows) > 1
    assert rows[1][0] == "1"
    assert rows[1][2] == "vogue.in"


def test_campaign_not_found(auth_client):
    response = auth_client.get("/campaigns/9999")
    assert response.status_code == 404
    assert "Not found" in response.text


def test_csv_export_for_missing_campaign(auth_client):
    response = auth_client.get("/campaigns/9999/export.csv")
    assert response.status_code == 404


def test_campaign_routes_require_login(client):
    for path in ("/campaigns/new", "/campaigns/1", "/campaigns/1/export.csv"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"


class TestStatusResolution:
    def test_all_succeed(self):
        assert resolve_status(successful=3, failed=0) == CampaignStatus.COMPLETED

    def test_partial_failure(self):
        assert resolve_status(successful=2, failed=1) == CampaignStatus.COMPLETED_WITH_WARNINGS

    def test_all_fail(self):
        assert resolve_status(successful=0, failed=3) == CampaignStatus.FAILED


def test_campaign_fails_when_all_providers_fail(auth_client, db, monkeypatch):
    async def all_fail(campaign, settings):
        return [
            ProviderOutcome(
                provider_name=name,
                success=False,
                error_message="Provider timed out after 60s",
            )
            for name in ("gemini", "groq", "openrouter")
        ]

    monkeypatch.setattr("app.services.campaign_service.run_providers", all_fail)

    response = _create_campaign(auth_client)
    assert response.status_code == 303  # campaign is still created, not a crash

    campaign = db.query(Campaign).one()
    assert campaign.status == CampaignStatus.FAILED
    assert campaign.completed_at is not None
    assert "timed out" in campaign.error_message
    assert campaign.recommendations == []

    page = auth_client.get(response.headers["location"])
    assert page.status_code == 200
    assert "Analysis failed" in page.text
    assert "No recommendations available" in page.text


def test_campaign_completes_with_warnings_when_one_provider_fails(auth_client, db, monkeypatch):
    from app.providers.demo import DemoProvider

    real_generate = DemoProvider.generate

    async def flaky_generate(self, campaign):
        if self.name == "groq":
            return ProviderOutcome(
                provider_name="groq",
                success=False,
                error_message="Authentication failed - check the API key",
            )
        return await real_generate(self, campaign)

    monkeypatch.setattr(DemoProvider, "generate", flaky_generate)

    response = _create_campaign(auth_client)
    campaign = db.query(Campaign).one()

    assert campaign.status == CampaignStatus.COMPLETED_WITH_WARNINGS
    assert len(campaign.recommendations) > 0

    page = auth_client.get(response.headers["location"])
    assert "Completed with warnings" in page.text
    # The failure reason is shown, but never a raw provider payload.
    assert "Authentication failed" in page.text
