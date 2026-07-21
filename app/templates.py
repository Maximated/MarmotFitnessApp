from pathlib import Path

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")

_CSS_PATH = Path("app/static/css/style.css")
templates.env.globals["css_version"] = int(_CSS_PATH.stat().st_mtime)
