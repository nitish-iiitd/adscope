import secrets

from fastapi import Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import Settings, get_settings

COOKIE_NAME = "adscope_session"
SESSION_MAX_AGE = 60 * 60 * 8  # 8 hours


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt="adscope-session")


def verify_credentials(username: str, password: str, settings: Settings) -> bool:
    # compare_digest on both fields keeps the check constant-time.
    user_ok = secrets.compare_digest(username.encode(), settings.app_username.encode())
    pass_ok = secrets.compare_digest(password.encode(), settings.app_password.encode())
    return user_ok and pass_ok


def create_session_token(username: str, settings: Settings) -> str:
    return _serializer(settings).dumps({"username": username})


def get_session_user(request: Request) -> str | None:
    settings = get_settings()
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        data = _serializer(settings).loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("username")


def set_session_cookie(response, token: str, settings: Settings) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")
