from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import get_settings
from app.security import (
    clear_session_cookie,
    create_session_token,
    set_session_cookie,
    verify_credentials,
)
from app.templating import templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
async def login(request: Request, username: str = Form(""), password: str = Form("")):
    settings = get_settings()
    if not verify_credentials(username, password, settings):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid username or password."},
            status_code=401,
        )

    response = RedirectResponse(url="/", status_code=303)
    set_session_cookie(response, create_session_token(username, settings), settings)
    return response


@router.post("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    clear_session_cookie(response)
    return response
