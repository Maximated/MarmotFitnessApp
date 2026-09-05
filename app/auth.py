import logging
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import bcrypt
import pillow_heif
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.templates import templates

pillow_heif.register_heif_opener()

router = APIRouter()
logger = logging.getLogger(__name__)

AVATAR_DIR = Path("media/avatars")
AVATAR_SIZE = 480
MAX_AVATAR_BYTES = 8 * 1024 * 1024

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_BYTES = 72  # bcrypt's own hard limit
LOGIN_ERROR = "Email o contraseña incorrectos."
LOGIN_RATE_LIMIT = 10
LOGIN_RATE_WINDOW_SECONDS = 15 * 60

# Hashed once at import so a login attempt for an email that doesn't exist
# still runs a real bcrypt comparison against *something* -- otherwise
# "no such user" returns near-instantly while "wrong password" takes the
# usual ~100ms, and that timing gap is enough to enumerate which emails
# have accounts.
_DUMMY_PASSWORD_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt()).decode("utf-8")

_login_attempts: dict[str, list[float]] = {}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def is_rate_limited(key: str) -> bool:
    now = time.monotonic()
    attempts = _login_attempts.setdefault(key, [])
    attempts[:] = [t for t in attempts if now - t < LOGIN_RATE_WINDOW_SECONDS]
    if len(attempts) >= LOGIN_RATE_LIMIT:
        return True
    attempts.append(now)
    return False


def email_is_allowed(email: str) -> bool:
    return settings.allowed_email is None or email.lower() == settings.allowed_email.lower()

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


@router.get("/login")
async def login(request: Request):
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth/callback")
async def auth_callback(request: Request, db: Session = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token["userinfo"]

    user = db.query(User).filter(User.google_id == userinfo["sub"]).first()
    if user is None:
        # An existing password-only account with this email links its
        # Google identity instead of erroring or creating a duplicate --
        # same person, second login method.
        user = db.query(User).filter(User.email == userinfo["email"]).first()
        if user is not None:
            user.google_id = userinfo["sub"]
        else:
            if not email_is_allowed(userinfo["email"]):
                raise HTTPException(status_code=403, detail="Cuenta no autorizada")
            user = User(
                google_id=userinfo["sub"],
                email=userinfo["email"],
                name=userinfo["name"],
            )
            db.add(user)
        db.commit()
        db.refresh(user)

    request.session["user_id"] = user.id
    return RedirectResponse(url="/")


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")


@router.get("/register")
async def register_page(request: Request, user: User | None = Depends(get_current_user)):
    if user is not None:
        return RedirectResponse(url="/")
    return templates.TemplateResponse(request=request, name="auth/register.html", context={"error": None})


@router.post("/register")
async def register_submit(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(...),
    name: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
):
    email_normalized = email.strip().lower()
    name = name.strip()
    error = None

    if "@" not in email_normalized or len(email_normalized) < 3:
        error = "Introduce un email válido."
    elif not name:
        error = "Introduce un nombre."
    elif not email_is_allowed(email_normalized):
        error = "No se pueden crear cuentas nuevas."
    elif len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        error = "La contraseña es demasiado larga."
    elif len(password) < MIN_PASSWORD_LENGTH:
        error = f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres."
    elif password != password_confirm:
        error = "Las contraseñas no coinciden."
    elif db.query(User).filter(User.email == email_normalized).first() is not None:
        error = "Ya existe una cuenta con ese email."

    if error is not None:
        return templates.TemplateResponse(
            request=request,
            name="auth/register.html",
            context={"error": error, "email": email, "name": name},
            status_code=400,
        )

    user = User(email=email_normalized, name=name, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)

    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)


@router.post("/login/password")
async def login_password(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(...),
    password: str = Form(...),
):
    client_ip = request.client.host if request.client else "unknown"
    if is_rate_limited(client_ip):
        return RedirectResponse(url="/?login_error=1", status_code=303)

    email_normalized = email.strip().lower()
    user = db.query(User).filter(User.email == email_normalized).first()

    # Always run a real bcrypt check, even for a nonexistent user or one
    # with no password set -- see _DUMMY_PASSWORD_HASH.
    password_hash = user.password_hash if user is not None and user.password_hash else _DUMMY_PASSWORD_HASH
    valid = verify_password(password, password_hash)

    if user is None or not user.password_hash or not valid:
        return RedirectResponse(url="/?login_error=1", status_code=303)

    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)


@router.get("/profile")
async def profile_page(request: Request, user: User | None = Depends(get_current_user)):
    return templates.TemplateResponse(
        request=request,
        name="profile.html",
        context={"user": user, "password_updated": request.query_params.get("password_updated")},
    )


@router.post("/profile/password")
async def update_password(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
    current_password: str = Form(""),
    new_password: str = Form(...),
    new_password_confirm: str = Form(...),
):
    if user is None:
        raise HTTPException(status_code=401)

    error = None
    if user.password_hash and not verify_password(current_password, user.password_hash):
        error = "La contraseña actual no es correcta."
    elif len(new_password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        error = "La contraseña es demasiado larga."
    elif len(new_password) < MIN_PASSWORD_LENGTH:
        error = f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres."
    elif new_password != new_password_confirm:
        error = "Las contraseñas no coinciden."

    if error is not None:
        return templates.TemplateResponse(
            request=request,
            name="profile.html",
            context={"user": user, "password_error": error},
            status_code=400,
        )

    user.password_hash = hash_password(new_password)
    db.commit()
    return RedirectResponse(url="/profile?password_updated=1", status_code=303)


@router.post("/profile/theme")
async def update_theme(
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
    light: bool = Form(False),
):
    if user is None:
        raise HTTPException(status_code=401)
    # `light` is the only explicit override the switch offers -- unchecking
    # it clears the preference back to None (follow the OS), rather than
    # writing an explicit "dark", so a user who never touches this keeps
    # getting the system-driven behavior exactly as before.
    user.theme = "light" if light else None
    db.commit()
    return RedirectResponse(url="/profile", status_code=303)


@router.post("/profile/avatar")
async def upload_avatar(
    photo: UploadFile,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user is None:
        raise HTTPException(status_code=401)
    if not photo.content_type or not photo.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="El archivo debe ser una imagen")

    raw = await photo.read(MAX_AVATAR_BYTES + 1)
    if len(raw) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="La imagen no puede superar los 8 MB")

    try:
        image = Image.open(BytesIO(raw))
        image = ImageOps.exif_transpose(image)
        image = ImageOps.fit(image.convert("RGB"), (AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)
    except Exception:
        raise HTTPException(status_code=400, detail="No se pudo procesar la imagen")

    try:
        AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        image.save(AVATAR_DIR / f"{user.id}.webp", format="WEBP", quality=85)
    except OSError:
        logger.exception("Failed to save avatar for user %s", user.id)
        raise HTTPException(
            status_code=500, detail="No se pudo guardar la foto. Inténtalo más tarde."
        )

    user.avatar_updated_at = datetime.now(timezone.utc)
    db.commit()

    return RedirectResponse(url="/profile", status_code=303)
