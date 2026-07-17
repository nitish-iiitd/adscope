from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.config import get_settings

TEMPLATES_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Exposed to every template so the layout can render the app name and demo badge.
settings = get_settings()
templates.env.globals["app_name"] = settings.app_name
templates.env.globals["demo_mode"] = settings.demo_mode
