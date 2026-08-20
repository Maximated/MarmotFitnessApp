import asyncio
import logging
import mimetypes
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.auth import router as auth_router
from app.block_exercises import router as block_exercises_router
from app.blocks import router as blocks_router
from app.config import settings
from app.database import SessionLocal, get_db
from app.dependencies import get_current_user
from app.exercise_ratings import router as exercise_ratings_router
from app.exercises import router as exercises_router
from app.history import router as history_router
from app.models import DayTemplate, Program, User, Workout
from app.program_import import router as program_import_router
from app.program_sessions import build_calendar_weeks, get_next_sessions
from app.program_sessions import router as program_sessions_router
from app.programs import router as programs_router
from app.push import router as push_router, send_push_for_workout
from app.templates import templates
from app.version import get_version_status
from app.workouts import router as workouts_router

# El Debian slim de la imagen base no trae .woff2 ni .webp en /etc/mime.types,
# así que StaticFiles los serviría como application/octet-stream.
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("image/webp", ".webp")

NEXT_SESSION_LOCK_HOURS = 24
PUSH_POLL_INTERVAL_SECONDS = 5


async def rest_push_poller() -> None:
    """Sends the Web Push for a rest period exactly once, as soon as it
    ends, whether or not anyone has a page open to see it happen -- a
    background countdown running on a page can't reach a locked phone or a
    fully backgrounded app, this can."""
    while True:
        await asyncio.sleep(PUSH_POLL_INTERVAL_SECONDS)
        db = SessionLocal()
        try:
            due = (
                db.query(Workout)
                .filter(
                    Workout.rest_until.isnot(None),
                    Workout.rest_until <= datetime.now(timezone.utc),
                    Workout.rest_push_sent_at.is_(None),
                )
                .all()
            )
            for workout in due:
                send_push_for_workout(db, workout)
                workout.rest_push_sent_at = datetime.now(timezone.utc)
            if due:
                db.commit()
        except Exception:
            logging.getLogger(__name__).exception("rest_push_poller iteration failed")
        finally:
            db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(rest_push_poller())
    yield
    task.cancel()


app = FastAPI(title="Marmot Fitness App", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    https_only=settings.session_cookie_secure,
)
app.include_router(auth_router)
app.include_router(exercises_router)
app.include_router(exercise_ratings_router)
app.include_router(workouts_router)
app.include_router(history_router)
app.include_router(program_import_router)
app.include_router(programs_router)
app.include_router(blocks_router)
app.include_router(block_exercises_router)
app.include_router(program_sessions_router)
app.include_router(push_router)
app.mount("/media", StaticFiles(directory="media"), name="media")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
async def home(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    context = {"user": user, "version_status": get_version_status()}

    if user is not None:
        active_program = (
            db.query(Program)
            .filter(Program.user_id == user.id, Program.is_active == True)  # noqa: E712
            .first()
        )
        context["active_program"] = active_program

        if active_program is not None:
            today = date.today()

            today_workout = (
                db.query(Workout)
                .filter(Workout.program_id == active_program.id, Workout.date == today)
                .first()
            )
            today_session = None
            if today_workout is not None:
                today_day_template = db.get(DayTemplate, today_workout.day_template_id)
                today_session = {
                    "day_template": today_day_template,
                    "finished": today_workout.finished_at is not None,
                }
            context["today_session"] = today_session

            last_workout = (
                db.query(Workout)
                .filter(Workout.program_id == active_program.id, Workout.date < today)
                .order_by(Workout.date.desc())
                .first()
            )
            last_session = None
            if last_workout is not None:
                last_day_template = db.get(DayTemplate, last_workout.day_template_id)
                last_session = {"date": last_workout.date, "day_template": last_day_template}
            context["last_session"] = last_session

            next_session_available_at = None
            if last_workout is not None:
                reference_time = last_workout.finished_at or last_workout.started_at
                if reference_time is not None:
                    next_session_available_at = reference_time + timedelta(
                        hours=NEXT_SESSION_LOCK_HOURS
                    )
            next_session_locked = (
                next_session_available_at is not None
                and datetime.now(timezone.utc) < next_session_available_at
            )
            context["next_session_available_at"] = next_session_available_at
            context["next_session_locked"] = next_session_locked

            next_sessions = []
            for day_number, due_date in get_next_sessions(active_program, count=3):
                day_template = (
                    db.query(DayTemplate)
                    .filter(
                        DayTemplate.program_id == active_program.id,
                        DayTemplate.day_number == day_number,
                    )
                    .first()
                )
                next_sessions.append({"date": due_date, "day_template": day_template})
            context["next_sessions"] = next_sessions

            weeks, _, _ = build_calendar_weeks(db, active_program, today.year, today.month)
            context["calendar_weeks"] = weeks
            context["calendar_month_name"] = today.strftime("%B %Y")

    return templates.TemplateResponse(request=request, name="home.html", context=context)


@app.get("/calendar")
async def general_calendar(
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    if user is None:
        return RedirectResponse(url="/")
    active_program = (
        db.query(Program)
        .filter(Program.user_id == user.id, Program.is_active == True)  # noqa: E712
        .first()
    )
    if active_program is None:
        return RedirectResponse(url="/programs")
    return RedirectResponse(url=f"/programs/{active_program.id}/calendar")


@app.get("/sw.js")
async def service_worker():
    return FileResponse("app/static/sw.js", media_type="application/javascript")
