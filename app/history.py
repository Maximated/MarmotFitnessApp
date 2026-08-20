from datetime import date as date_type
from datetime import datetime as datetime_type
from itertools import groupby
from math import ceil
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_user
from app.models import BlockExercise, Exercise, User, Workout, WorkoutSet
from app.templates import templates

router = APIRouter()

PER_PAGE_DAYS = 5


def format_duration(seconds: int) -> str:
    minutes, secs = divmod(max(0, int(seconds)), 60)
    return f"{minutes}:{secs:02d}"


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
        dates_query = (
            dates_query.join(WorkoutSet, WorkoutSet.workout_id == Workout.id)
            .outerjoin(Exercise, Exercise.id == WorkoutSet.exercise_id)
            .outerjoin(BlockExercise, BlockExercise.id == WorkoutSet.block_exercise_id)
            .filter(
                or_(
                    Exercise.name.ilike(f"%{q}%"),
                    BlockExercise.pending_name.ilike(f"%{q}%"),
                    WorkoutSet.pending_name.ilike(f"%{q}%"),
                )
            )
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
            db.query(WorkoutSet, Workout, Exercise, BlockExercise)
            .join(Workout, WorkoutSet.workout_id == Workout.id)
            .outerjoin(Exercise, Exercise.id == WorkoutSet.exercise_id)
            .outerjoin(BlockExercise, BlockExercise.id == WorkoutSet.block_exercise_id)
            .filter(Workout.user_id == user.id, Workout.date.in_(page_dates))
        )
        if q:
            sets_query = sets_query.filter(
                or_(
                    Exercise.name.ilike(f"%{q}%"),
                    BlockExercise.pending_name.ilike(f"%{q}%"),
                    WorkoutSet.pending_name.ilike(f"%{q}%"),
                )
            )
        rows = sets_query.order_by(Workout.date.desc(), WorkoutSet.order.asc()).all()

        history_next_params = {
            k: v
            for k, v in {
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
                "q": q,
                "page": page if page > 1 else None,
            }.items()
            if v
        }
        history_next_url = "/history" + (
            f"?{urlencode(history_next_params)}" if history_next_params else ""
        )
        next_qs = urlencode({"next": history_next_url})

        prev_time_by_workout: dict[int, object] = {}
        enriched_rows = []
        for workout_set, workout, exercise, block_exercise in rows:
            if workout_set.duration_seconds is not None:
                elapsed_display = format_duration(workout_set.duration_seconds)
            else:
                prev_time = prev_time_by_workout.get(workout.id)
                if prev_time is not None:
                    delta = datetime_type.combine(date_type.min, workout_set.time) - datetime_type.combine(
                        date_type.min, prev_time
                    )
                    elapsed_display = format_duration(delta.seconds) if delta.total_seconds() >= 0 else "-"
                else:
                    elapsed_display = "-"
            prev_time_by_workout[workout.id] = workout_set.time
            if exercise is not None:
                display_name = exercise.name
                link_url = f"/exercises/{exercise.id}/log?{next_qs}"
            elif block_exercise is not None:
                display_name = block_exercise.pending_name
                link_url = f"/block-exercises/{workout_set.block_exercise_id}/log?{next_qs}"
            else:
                # The program/block-exercise this was logged against no longer
                # exists (e.g. the program was deleted) -- the set itself must
                # still survive, using the name snapshotted at logging time.
                display_name = workout_set.pending_name or "Ejercicio eliminado"
                link_url = None
            enriched_rows.append(
                (workout_set, workout, display_name, link_url, elapsed_display)
            )

        days = [
            (day, list(items))
            for day, items in groupby(enriched_rows, key=lambda row: row[1].date)
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
