from math import ceil
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_user
from app.models import Exercise, User
from app.templates import templates

router = APIRouter()

PER_PAGE = 24


@router.get("/exercises")
async def list_exercises(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    q: str | None = None,
    category: str | None = None,
    equipment: str | None = None,
    page: int = 1,
):
    query = db.query(Exercise)
    if q:
        query = query.filter(Exercise.name.ilike(f"%{q}%"))
    if category:
        query = query.filter(Exercise.category == category)
    if equipment:
        query = query.filter(Exercise.equipment == equipment)

    total = query.count()
    total_pages = max(1, ceil(total / PER_PAGE))
    page = max(1, min(page, total_pages))

    exercises = (
        query.order_by(Exercise.name)
        .offset((page - 1) * PER_PAGE)
        .limit(PER_PAGE)
        .all()
    )

    categories = [
        row[0]
        for row in db.query(Exercise.category).distinct().order_by(Exercise.category)
    ]
    equipments = [
        row[0]
        for row in db.query(Exercise.equipment)
        .distinct()
        .order_by(Exercise.equipment)
    ]

    filters = {
        k: v
        for k, v in {"q": q, "category": category, "equipment": equipment}.items()
        if v
    }

    return templates.TemplateResponse(
        request=request,
        name="exercises/list.html",
        context={
            "exercises": exercises,
            "categories": categories,
            "equipments": equipments,
            "q": q or "",
            "category": category or "",
            "equipment": equipment or "",
            "page": page,
            "total_pages": total_pages,
            "filters_qs": urlencode(filters),
        },
    )
