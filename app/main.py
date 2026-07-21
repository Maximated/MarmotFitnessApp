from fastapi import Depends, FastAPI, Request
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth import router as auth_router
from app.config import settings
from app.dependencies import get_current_user
from app.models import User

app = FastAPI(title="Marmot Fitness App")
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret_key)
app.include_router(auth_router)

templates = Jinja2Templates(directory="app/templates")


@app.get("/")
async def home(request: Request, user: User | None = Depends(get_current_user)):
    return templates.TemplateResponse(
        request=request, name="home.html", context={"user": user}
    )
