import csv
import io

import pytest

from app.entities.models import Campaign, CampaignPhase, CampaignStatus, GeneratedQuery
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


def _review_form(db, campaign_id, select=3, add_custom=None):
    """Build the review submission from the generated queries in the DB."""
    queries = (
        db.query(GeneratedQuery)
        .filter(GeneratedQuery.campaign_id == campaign_id)
        .order_by(GeneratedQuery.position)
        .all()
    )
    form: dict[str, str] = {}
    for i, q in enumerate(queries):
        form[f"text_{i}"] = q.text
        form[f"source_{i}"] = q.source_provider or ""
        form[f"custom_{i}"] = "0"
        if i < select:
            form[f"selected_{i}"] = "on"
    if add_custom:
        idx = len(queries)
        form[f"text_{idx}"] = add_custom
        form[f"selected_{idx}"] = "on"
        form[f"custom_{idx}"] = "1"
    return form


def _run_pipeline(client, db, select=3, **overrides):
    """Full flow: create -> service-1 -> review submit -> service-2. Returns campaign id."""
    review_redirect = _create_campaign(client, **overrides)
    assert review_redirect.status_code == 303
    campaign_id = int(review_redirect.headers["location"].split("/")[2])

    form = _review_form(db, campaign_id, select=select)
    submit = client.post(f"/campaigns/{campaign_id}/queries", data=form, follow_redirects=False)
    assert submit.status_code == 303
    assert submit.headers["location"] == f"/campaigns/{campaign_id}"
    return campaign_id


# --- Service-1: create + review ---------------------------------------------


def test_create_kicks_off_query_generation(auth_client, db):
    response = _create_campaign(auth_client)
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.endswith("/review")

    campaign = db.query(Campaign).one()
    assert campaign.phase == CampaignPhase.AWAITING_REVIEW
    # 3 demo providers x 10 queries.
    assert db.query(GeneratedQuery).filter_by(campaign_id=campaign.id).count() == 30


def test_review_page_lists_queries(auth_client, db):
    campaign_id = int(_create_campaign(auth_client).headers["location"].split("/")[2])
    response = auth_client.get(f"/campaigns/{campaign_id}/review")

    assert response.status_code == 200
    assert "Review audience queries" in response.text
    first_query = (
        db.query(GeneratedQuery).filter_by(campaign_id=campaign_id).order_by(GeneratedQuery.position).first()
    )
    assert first_query.text in response.text


def test_submit_with_no_selection_is_rejected(auth_client, db):
    campaign_id = int(_create_campaign(auth_client).headers["location"].split("/")[2])
    form = _review_form(db, campaign_id, select=0)
    response = auth_client.post(f"/campaigns/{campaign_id}/queries", data=form, follow_redirects=False)

    assert response.status_code == 400
    assert "Select at least one query" in response.text


# --- Full pipeline -----------------------------------------------------------


def test_full_pipeline_completes_in_demo_mode(auth_client, db):
    campaign_id = _run_pipeline(auth_client, db, select=3)

    campaign = db.query(Campaign).filter_by(id=campaign_id).one()
    assert campaign.phase == CampaignPhase.COMPLETED
    assert campaign.status == CampaignStatus.COMPLETED
    assert len(campaign.recommendations) > 0
    assert len(campaign.query_results) == 3 * 3  # selected queries x providers

    # Only the 3 selected queries are retained for analysis.
    assert db.query(GeneratedQuery).filter_by(campaign_id=campaign_id, is_selected=True).count() == 3

    top = max(campaign.recommendations, key=lambda r: (r.query_count, r.final_score))
    assert top.domain == "vogue.in"


def test_results_page_renders(auth_client, db):
    campaign_id = _run_pipeline(auth_client, db)
    response = auth_client.get(f"/campaigns/{campaign_id}")

    assert response.status_code == 200
    assert "Verdant Skincare" in response.text
    assert "vogue.in" in response.text
    assert "Queries analysed" in response.text
    assert "directional guidance for media planning" in response.text
    assert "Export CSV" in response.text


def test_custom_query_is_used_in_discovery(auth_client, db):
    review_redirect = _create_campaign(auth_client)
    campaign_id = int(review_redirect.headers["location"].split("/")[2])
    form = _review_form(db, campaign_id, select=2, add_custom="Which sites review vegan skincare?")
    auth_client.post(f"/campaigns/{campaign_id}/queries", data=form, follow_redirects=False)

    texts = [
        q.text
        for q in db.query(GeneratedQuery).filter_by(campaign_id=campaign_id, is_selected=True).all()
    ]
    assert "Which sites review vegan skincare?" in texts
    # 2 originally selected + 1 custom = 3 selected queries.
    assert len(texts) == 3


def test_dashboard_lists_campaign(auth_client, db):
    _run_pipeline(auth_client, db)
    response = auth_client.get("/")
    assert response.status_code == 200
    assert "Monsoon Awareness" in response.text
    assert "Completed" in response.text


# --- CSV export --------------------------------------------------------------


def test_csv_export(auth_client, db):
    campaign_id = _run_pipeline(auth_client, db)
    response = auth_client.get(f"/campaigns/{campaign_id}/export.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "monsoon-awareness" in response.headers["content-disposition"]

    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0] == [
        "Rank",
        "Website name",
        "Domain",
        "Category",
        "Final score",
        "Query count",
        "Model count",
        "Agreement",
        "Combined reason",
    ]
    assert len(rows) > 1
    assert rows[1][0] == "1"


# --- Validation & errors -----------------------------------------------------


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


def test_campaign_not_found(auth_client):
    response = auth_client.get("/campaigns/9999")
    assert response.status_code == 404
    assert "Not found" in response.text


def test_campaign_routes_require_login(client):
    for path in ("/campaigns/new", "/campaigns/1", "/campaigns/1/review", "/campaigns/1/export.csv"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"


def test_site_discovery_failure_marks_campaign_failed(auth_client, db, monkeypatch):
    from app.services import campaign_service
    from app.services.site_discovery_service import DiscoveryOutput

    async def empty_discovery(queries, settings):
        return DiscoveryOutput(query_results=[], final_entries=[], total_calls=3, successful_calls=0)

    monkeypatch.setattr(campaign_service, "discover_sites", empty_discovery)

    review_redirect = _create_campaign(auth_client)
    campaign_id = int(review_redirect.headers["location"].split("/")[2])
    form = _review_form(db, campaign_id, select=2)
    auth_client.post(f"/campaigns/{campaign_id}/queries", data=form, follow_redirects=False)

    campaign = db.query(Campaign).filter_by(id=campaign_id).one()
    assert campaign.phase == CampaignPhase.FAILED
    assert campaign.status == CampaignStatus.FAILED

    page = auth_client.get(f"/campaigns/{campaign_id}")
    assert "Analysis failed" in page.text


class TestStatusResolution:
    def test_all_succeed(self):
        assert resolve_status(successful=3, failed=0) == CampaignStatus.COMPLETED

    def test_partial_failure(self):
        assert resolve_status(successful=2, failed=1) == CampaignStatus.COMPLETED_WITH_WARNINGS

    def test_all_fail(self):
        assert resolve_status(successful=0, failed=3) == CampaignStatus.FAILED
