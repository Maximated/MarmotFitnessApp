from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pillow_heif
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
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

AVATAR_DIR = Path("media/avatars")
AVATAR_SIZE = 480
MAX_AVATAR_BYTES = 8 * 1024 * 1024

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
        if settings.allowed_email is not None and userinfo["email"] != settings.allowed_email:
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


@router.get("/profile")
async def profile_page(request: Request, user: User | None = Depends(get_current_user)):
    return templates.TemplateResponse(
        request=request,
        name="profile.html",
        context={"user": user},
    )


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

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    image.save(AVATAR_DIR / f"{user.id}.webp", format="WEBP", quality=85)

    user.avatar_updated_at = datetime.now(timezone.utc)
    db.commit()

    return RedirectResponse(url="/profile", status_code=303)
