from datetime import date as date_type
from itertools import groupby
from math import ceil
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_user
from app.models import Exercise, User, Workout, WorkoutSet
from app.templates import templates

router = APIRouter()

PER_PAGE_DAYS = 5


@router.get("/history")
async def history(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    date_from: date_type | None = None,
    date_to: date_type | None = None,
    q: str | None = None,
    page: int = 1,
):
    dates_query = db.query(Workout.date).filter(Workout.user_id == user.id)
    if date_from:
        dates_query = dates_query.filter(Workout.date >= date_from)
    if date_to:
        dates_query = dates_query.filter(Workout.date <= date_to)
    if q:
        dates_query = dates_query.join(
            WorkoutSet, WorkoutSet.workout_id == Workout.id
        ).join(Exercise, Exercise.id == WorkoutSet.exercise_id).filter(
            Exercise.name.ilike(f"%{q}%")
        )
    dates_query = dates_query.distinct().order_by(Workout.date.desc())

    total_days = dates_query.count()
    total_pages = max(1, ceil(total_days / PER_PAGE_DAYS))
    page = max(1, min(page, total_pages))
    page_dates = [
        row[0]
        for row in dates_query.offset((page - 1) * PER_PAGE_DAYS).limit(PER_PAGE_DAYS)
    ]

    days = []
    if page_dates:
        sets_query = (
            db.query(WorkoutSet, Workout, Exercise)
            .join(Workout, WorkoutSet.workout_id == Workout.id)
            .join(Exercise, Exercise.id == WorkoutSet.exercise_id)
            .filter(Workout.user_id == user.id, Workout.date.in_(page_dates))
        )
        if q:
            sets_query = sets_query.filter(Exercise.name.ilike(f"%{q}%"))
        rows = sets_query.order_by(Workout.date.desc(), WorkoutSet.order.asc()).all()

        days = [
            (day, list(items))
            for day, items in groupby(rows, key=lambda row: row[1].date)
        ]

    filters = {
        k: v
        for k, v in {
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "q": q,
        }.items()
        if v
    }

    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={
            "days": days,
            "date_from": date_from.isoformat() if date_from else "",
            "date_to": date_to.isoformat() if date_to else "",
            "q": q or "",
            "page": page,
            "total_pages": total_pages,
            "filters_qs": urlencode(filters),
        },
    )
