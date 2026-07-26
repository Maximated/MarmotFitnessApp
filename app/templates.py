from pathlib import Path

from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.database import SessionLocal
from app.models import User, Workout


def session_timer_processor(request: Request) -> dict:
    empty = {
        "active_session_started_at": None,
        "active_session_rest_until": None,
        "active_session_rest_total_seconds": None,
        "header_user": None,
    }
    user_id = request.session.get("user_id")
    if user_id is None:
        return empty

    db = SessionLocal()
    try:
        header_user = db.get(User, user_id)
        workout = (
            db.query(Workout)
            .filter(
                Workout.user_id == user_id,
                Workout.started_at.isnot(None),
                Workout.finished_at.is_(None),
            )
            .order_by(Workout.started_at.desc())
            .first()
        )
        if workout is None:
            return {**empty, "header_user": header_user}
        return {
            "active_session_started_at": workout.started_at.isoformat(),
            "active_session_rest_until": workout.rest_until.isoformat() if workout.rest_until else None,
            "active_session_rest_total_seconds": workout.rest_total_seconds,
            "header_user": header_user,
        }
    finally:
        db.close()


templates = Jinja2Templates(
    directory="app/templates", context_processors=[session_timer_processor]
)

_CSS_PATH = Path("app/static/css/style.css")
templates.env.globals["css_version"] = int(_CSS_PATH.stat().st_mtime)
