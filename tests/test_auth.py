from app.security import COOKIE_NAME


def test_login_success_sets_session_cookie(client):
    response = client.post(
        "/login",
        data={"username": "admin", "password": "test-password"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert COOKIE_NAME in response.cookies

    set_cookie = response.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie


def test_login_failure_shows_error(client):
    response = client.post("/login", data={"username": "admin", "password": "wrong"})
    assert response.status_code == 401
    assert "Invalid username or password" in response.text
    assert COOKIE_NAME not in response.cookies


def test_protected_route_redirects_to_login(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_health_is_public(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_dashboard_accessible_after_login(auth_client):
    response = auth_client.get("/")
    assert response.status_code == 200
    assert "Dashboard" in response.text


def test_logout_clears_session(auth_client):
    response = auth_client.post("/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"

    after = auth_client.get("/", follow_redirects=False)
    assert after.status_code == 303
    assert after.headers["location"] == "/login"


def test_tampered_session_cookie_is_rejected(client):
    client.cookies.set(COOKIE_NAME, "not-a-valid-signed-token")
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
