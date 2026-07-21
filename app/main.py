from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import router as auth_router
from app.config import settings
from app.dependencies import get_current_user
from app.exercises import router as exercises_router
from app.history import router as history_router
from app.models import User
from app.templates import templates
from app.workouts import router as workouts_router

app = FastAPI(title="Marmot Fitness App")
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret_key)
app.include_router(auth_router)
app.include_router(exercises_router)
app.include_router(workouts_router)
app.include_router(history_router)
app.mount("/media", StaticFiles(directory="media"), name="media")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
async def home(request: Request, user: User | None = Depends(get_current_user)):
    return templates.TemplateResponse(
        request=request, name="home.html", context={"user": user}
    )


@app.get("/sw.js")
async def service_worker():
    return FileResponse("app/static/sw.js", media_type="application/javascript")
