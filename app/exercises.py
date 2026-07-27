from math import ceil
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_user
from app.exercise_history import build_exercise_history
from app.exercise_ratings import get_similar_exercises, get_user_ban, get_user_rating, get_user_ratings_map
from app.models import Exercise, User
from app.templates import templates

router = APIRouter()

PER_PAGE = 24
PER_PAGE_LARGE = 10


@router.get("/exercises")
async def exercise_banners(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    counts = dict(
        db.query(Exercise.target_muscle, func.count(Exercise.id))
        .group_by(Exercise.target_muscle)
        .all()
    )
    muscles = sorted(counts.keys())

    return templates.TemplateResponse(
        request=request,
        name="exercises/banners.html",
        context={"muscles": muscles, "counts": counts},
    )


@router.get("/exercises/search")
async def exercise_search(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    q: str | None = None,
    page: int = 1,
):
    exercises = []
    total_pages = 1
    if q:
        query = db.query(Exercise).filter(Exercise.name.ilike(f"%{q}%"))
        total = query.count()
        total_pages = max(1, ceil(total / PER_PAGE_LARGE))
        page = max(1, min(page, total_pages))
        exercises = (
            query.order_by(Exercise.name)
            .offset((page - 1) * PER_PAGE_LARGE)
            .limit(PER_PAGE_LARGE)
            .all()
        )

    current_url = f"/exercises/search?{urlencode({'q': q or ''})}&page={page}"

    return templates.TemplateResponse(
        request=request,
        name="exercises/search.html",
        context={
            "exercises": exercises,
            "ratings": get_user_ratings_map(db, user.id, [e.id for e in exercises]),
            "current_url": current_url,
            "q": q or "",
            "page": page,
            "total_pages": total_pages,
        },
    )


@router.get("/exercises/muscle/{target_muscle}")
async def exercise_muscle_list(
    target_muscle: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    equipment: str | None = None,
    page: int = 1,
):
    query = db.query(Exercise).filter(Exercise.target_muscle == target_muscle)
    if equipment:
        query = query.filter(Exercise.equipment == equipment)

    total = query.count()
    total_pages = max(1, ceil(total / PER_PAGE_LARGE))
    page = max(1, min(page, total_pages))

    exercises = (
        query.order_by(Exercise.name)
        .offset((page - 1) * PER_PAGE_LARGE)
        .limit(PER_PAGE_LARGE)
        .all()
    )

    equipments = [
        row[0]
        for row in db.query(Exercise.equipment)
        .filter(Exercise.target_muscle == target_muscle)
        .distinct()
        .order_by(Exercise.equipment)
    ]

    filters = {k: v for k, v in {"equipment": equipment}.items() if v}
    filters_qs = urlencode(filters)
    base_path = f"/exercises/muscle/{quote(target_muscle)}"
    current_url = f"{base_path}?{filters_qs}{'&' if filters_qs else ''}page={page}"

    return templates.TemplateResponse(
        request=request,
        name="exercises/muscle_list.html",
        context={
            "target_muscle": target_muscle,
            "base_path": base_path,
            "exercises": exercises,
            "ratings": get_user_ratings_map(db, user.id, [e.id for e in exercises]),
            "current_url": current_url,
            "equipments": equipments,
            "equipment": equipment or "",
            "page": page,
            "total_pages": total_pages,
            "filters_qs": filters_qs,
        },
    )


@router.get("/exercises/{exercise_id}/view")
async def view_exercise_gif(
    exercise_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    next: str | None = None,
):
    exercise = db.get(Exercise, exercise_id)
    history = build_exercise_history(db, user.id, exercise_id)

    self_url = f"/exercises/{exercise_id}/view"
    if next:
        self_url += f"?{urlencode({'next': next})}"

    context = {
        "exercise": exercise,
        "next": next or "/exercises",
        "self_url": self_url,
        "user_rating": get_user_rating(db, user.id, exercise_id),
        "user_banned": get_user_ban(db, user.id, exercise_id),
        "similar_exercises": get_similar_exercises(db, user.id, exercise_id),
    }
    context.update(history)

    return templates.TemplateResponse(
        request=request,
        name="exercises/view.html",
        context=context,
    )
