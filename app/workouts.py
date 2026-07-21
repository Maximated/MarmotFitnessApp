from datetime import date as date_type
from datetime import datetime
from datetime import time as time_type

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.charts import polyline_points, scale_points
from app.database import get_db
from app.dependencies import require_user
from app.models import Exercise, User, Workout, WorkoutSet
from app.templates import templates

router = APIRouter()


def get_or_create_workout(db: Session, user_id: int, workout_date: date_type) -> Workout:
    workout = (
        db.query(Workout)
        .filter(Workout.user_id == user_id, Workout.date == workout_date)
        .first()
    )
    if workout is None:
        workout = Workout(user_id=user_id, date=workout_date)
        db.add(workout)
        db.flush()
    return workout


def get_own_workout_set(db: Session, set_id: int, user_id: int) -> WorkoutSet:
    workout_set = (
        db.query(WorkoutSet)
        .join(Workout, WorkoutSet.workout_id == Workout.id)
        .filter(WorkoutSet.id == set_id, Workout.user_id == user_id)
        .first()
    )
    if workout_set is None:
        raise HTTPException(status_code=404)
    return workout_set


@router.get("/exercises/{exercise_id}/log")
async def log_exercise_form(
    exercise_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    exercise = db.get(Exercise, exercise_id)

    sets = (
        db.query(WorkoutSet, Workout)
        .join(Workout, WorkoutSet.workout_id == Workout.id)
        .filter(Workout.user_id == user.id, WorkoutSet.exercise_id == exercise_id)
        .order_by(Workout.date.desc(), WorkoutSet.order.desc())
        .all()
    )

    chronological = list(reversed(sets))
    weights = [ws.weight for ws, _ in chronological]
    reps = [ws.reps for ws, _ in chronological]

    now = datetime.now()
    return templates.TemplateResponse(
        request=request,
        name="exercises/log.html",
        context={
            "exercise": exercise,
            "sets": sets,
            "today": now.date().isoformat(),
            "now_time": now.time().isoformat(timespec="minutes"),
            "has_progress": len(chronological) >= 2,
            "weight_points": scale_points(weights),
            "weight_line": polyline_points(scale_points(weights)),
            "weight_min": min(weights) if weights else None,
            "weight_max": max(weights) if weights else None,
            "reps_points": scale_points(reps),
            "reps_line": polyline_points(scale_points(reps)),
            "reps_min": min(reps) if reps else None,
            "reps_max": max(reps) if reps else None,
            "progress_from": chronological[0][1].date if chronological else None,
            "progress_to": chronological[-1][1].date if chronological else None,
        },
    )


@router.post("/exercises/{exercise_id}/log")
async def log_exercise_submit(
    exercise_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    weight: float = Form(...),
    reps: int = Form(...),
    workout_date: date_type = Form(..., alias="date"),
    set_time: time_type = Form(..., alias="time"),
    comment: str | None = Form(None),
):
    workout = get_or_create_workout(db, user.id, workout_date)

    next_order = (
        db.query(WorkoutSet).filter(WorkoutSet.workout_id == workout.id).count() + 1
    )

    db.add(
        WorkoutSet(
            workout_id=workout.id,
            exercise_id=exercise_id,
            weight=weight,
            reps=reps,
            time=set_time,
            comment=comment or None,
            order=next_order,
        )
    )
    db.commit()

    return RedirectResponse(url=f"/exercises/{exercise_id}/log", status_code=303)


@router.get("/workout-sets/{set_id}/edit")
async def edit_workout_set_form(
    set_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    workout_set = get_own_workout_set(db, set_id, user.id)
    workout = db.get(Workout, workout_set.workout_id)
    exercise = db.get(Exercise, workout_set.exercise_id)

    return templates.TemplateResponse(
        request=request,
        name="exercises/edit_set.html",
        context={
            "exercise": exercise,
            "workout_set": workout_set,
            "date": workout.date.isoformat(),
        },
    )


@router.post("/workout-sets/{set_id}/edit")
async def edit_workout_set_submit(
    set_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    weight: float = Form(...),
    reps: int = Form(...),
    workout_date: date_type = Form(..., alias="date"),
    set_time: time_type = Form(..., alias="time"),
    comment: str | None = Form(None),
):
    workout_set = get_own_workout_set(db, set_id, user.id)
    workout = db.get(Workout, workout_set.workout_id)

    if workout.date != workout_date:
        new_workout = get_or_create_workout(db, user.id, workout_date)
        workout_set.workout_id = new_workout.id
        workout_set.order = (
            db.query(WorkoutSet)
            .filter(WorkoutSet.workout_id == new_workout.id)
            .count()
            + 1
        )

    workout_set.weight = weight
    workout_set.reps = reps
    workout_set.time = set_time
    workout_set.comment = comment or None
    db.commit()

    return RedirectResponse(
        url=f"/exercises/{workout_set.exercise_id}/log", status_code=303
    )


@router.post("/workout-sets/{set_id}/delete")
async def delete_workout_set(
    set_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    workout_set = get_own_workout_set(db, set_id, user.id)
    exercise_id = workout_set.exercise_id
    workout_id = workout_set.workout_id

    db.delete(workout_set)
    db.flush()

    remaining = (
        db.query(WorkoutSet).filter(WorkoutSet.workout_id == workout_id).count()
    )
    if remaining == 0:
        db.query(Workout).filter(Workout.id == workout_id).delete()

    db.commit()

    return RedirectResponse(url=f"/exercises/{exercise_id}/log", status_code=303)
