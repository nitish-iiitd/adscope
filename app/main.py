import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.database import init_db
from app.routers import auth, campaigns, recommendations
from app.security import get_session_user
from app.templating import templates

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()

PUBLIC_PATHS = {"/login", "/health"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("AdScope started (demo_mode=%s)", settings.demo_mode)
    yield


app = FastAPI(title=settings.app_name, docs_url=None, redoc_url=None, lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith("/static"):
        return await call_next(request)

    if get_session_user(request) is None:
        return RedirectResponse(url="/login", status_code=303)

    return await call_next(request)


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(campaigns.router)
app.include_router(recommendations.router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 404:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"title": "Not found", "message": str(exc.detail) or "That page does not exist."},
            status_code=404,
        )
    if request.url.path.endswith(".csv"):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return templates.TemplateResponse(
        request,
        "error.html",
        {"title": "Something went wrong", "message": str(exc.detail)},
        status_code=exc.status_code,
    )


@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(request: Request, exc: SQLAlchemyError):
    # Log the technical detail, show the user a generic message.
    logger.exception("Database error on %s: %s", request.url.path, exc)
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "title": "Service problem",
            "message": "A database error occurred. Please try again in a moment.",
        },
        status_code=500,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> HTMLResponse:
    logger.exception("Unhandled error on %s: %s", request.url.path, exc)
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "title": "Something went wrong",
            "message": "An unexpected error occurred. Please try again.",
        },
        status_code=500,
    )
