from datetime import date as date_type
from datetime import datetime
from datetime import time as time_type

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

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

    now = datetime.now()
    return templates.TemplateResponse(
        request=request,
        name="exercises/log.html",
        context={
            "exercise": exercise,
            "sets": sets,
            "today": now.date().isoformat(),
            "now_time": now.time().isoformat(timespec="minutes"),
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
