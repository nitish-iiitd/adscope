"""The How it works page renders its facts from the running code, not prose."""


def test_requires_login(client):
    response = client.get("/how-it-works", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_page_renders_the_live_prompts_and_defaults(auth_client):
    response = auth_client.get("/how-it-works")
    assert response.status_code == 200

    # The real system prompts, not a description of them.
    assert "Return valid JSON only" in response.text
    assert "websites or digital publishers you would consult" in response.text
    assert "YouTube channels" in response.text
    assert "Important exclusion rule" in response.text  # the competitor clause

    # Thresholds and defaults quoted from configuration.
    assert "66%" in response.text
    assert "33%" in response.text

    # The honest limits of objective/budget are stated, not glossed over.
    assert "Objective and budget influence the questions, not the ranking" in response.text


def test_navigation_links_to_the_page(auth_client):
    assert 'href="/how-it-works"' in auth_client.get("/").text
