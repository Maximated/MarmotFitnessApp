import mimetypes
from datetime import date

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.auth import router as auth_router
from app.block_exercises import router as block_exercises_router
from app.blocks import router as blocks_router
from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.exercises import router as exercises_router
from app.history import router as history_router
from app.models import DayTemplate, Program, User, Workout
from app.program_sessions import build_calendar_weeks, get_next_two_sessions
from app.program_sessions import router as program_sessions_router
from app.programs import router as programs_router
from app.templates import templates
from app.workouts import router as workouts_router

# El Debian slim de la imagen base no trae .woff2 en /etc/mime.types, así que
# StaticFiles lo serviría como application/octet-stream y el navegador
# rechazaría la fuente silenciosamente.
mimetypes.add_type("font/woff2", ".woff2")

app = FastAPI(title="Marmot Fitness App")
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret_key)
app.include_router(auth_router)
app.include_router(exercises_router)
app.include_router(workouts_router)
app.include_router(history_router)
app.include_router(programs_router)
app.include_router(blocks_router)
app.include_router(block_exercises_router)
app.include_router(program_sessions_router)
app.mount("/media", StaticFiles(directory="media"), name="media")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
async def home(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    context = {"user": user}

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

            next_sessions = []
            for day_number, due_date in get_next_two_sessions(active_program):
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


@app.get("/sw.js")
async def service_worker():
    return FileResponse("app/static/sw.js", media_type="application/javascript")
