from datetime import date as date_type
from datetime import datetime
from datetime import time as time_type
from datetime import timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_user
from app.exercise_history import build_exercise_history
from app.models import Block, BlockExercise, DayTemplate, Exercise, Program, User, Workout, WorkoutSet
from app.templates import templates

router = APIRouter()

SCHEDULE_INTERVAL_DAYS = 2


def recompute_schedule(db: Session, program: Program) -> None:
    last_workout = (
        db.query(Workout)
        .filter(Workout.program_id == program.id)
        .order_by(Workout.date.desc())
        .first()
    )
    if last_workout is None:
        program.current_day_number = None
        program.next_due_date = None
        return

    last_day_template = db.get(DayTemplate, last_workout.day_template_id)
    last_day_number = last_day_template.day_number if last_day_template else 0
    program.current_day_number = (last_day_number % program.cycle_days) + 1
    program.next_due_date = last_workout.date + timedelta(days=SCHEDULE_INTERVAL_DAYS)


def delete_workout_if_empty(db: Session, workout_id: int) -> None:
    workout = db.get(Workout, workout_id)
    if workout is None:
        return
    remaining = db.query(WorkoutSet).filter(WorkoutSet.workout_id == workout_id).count()
    if remaining > 0:
        return
    program_id = workout.program_id
    db.delete(workout)
    db.flush()
    if program_id is not None:
        program = db.get(Program, program_id)
        if program is not None:
            recompute_schedule(db, program)


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


def parse_optional_weight(raw: str) -> float | None:
    return float(raw) if raw.strip() else None


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
    block_exercise_id: int | None = None,
    next: str | None = None,
    logged: bool = False,
):
    exercise = db.get(Exercise, exercise_id)
    history = build_exercise_history(db, user.id, exercise_id)

    training = None
    prev_url = None
    next_exercise_url = None
    if block_exercise_id is not None:
        block_exercise = (
            db.query(BlockExercise)
            .join(Block, BlockExercise.block_id == Block.id)
            .join(DayTemplate, Block.day_template_id == DayTemplate.id)
            .join(Program, DayTemplate.program_id == Program.id)
            .filter(BlockExercise.id == block_exercise_id, Program.user_id == user.id)
            .first()
        )
        if block_exercise is not None:
            block = db.get(Block, block_exercise.block_id)
            today = date_type.today()
            todays_workout = (
                db.query(Workout)
                .filter(Workout.user_id == user.id, Workout.date == today)
                .first()
            )
            sets_completed_today = 0
            if todays_workout is not None:
                sets_completed_today = (
                    db.query(WorkoutSet)
                    .filter(
                        WorkoutSet.workout_id == todays_workout.id,
                        WorkoutSet.exercise_id == exercise_id,
                    )
                    .count()
                )
            training = {
                "reps_target": block_exercise.reps,
                "rest_seconds": block.rest_seconds,
                "no_rest": block_exercise.is_superset_with_next,
                "sets_completed": sets_completed_today,
                "sets_target": block.num_sets,
            }

            day_exercises = (
                db.query(BlockExercise)
                .join(Block, BlockExercise.block_id == Block.id)
                .filter(Block.day_template_id == block.day_template_id)
                .order_by(Block.position, BlockExercise.position)
                .all()
            )
            index = None
            for i, day_exercise in enumerate(day_exercises):
                if day_exercise.id == block_exercise.id:
                    index = i
                    break
            if index is not None:
                def build_nav_url(neighbor: BlockExercise) -> str:
                    nav_params = {"block_exercise_id": neighbor.id}
                    if next is not None:
                        nav_params["next"] = next
                    return f"/exercises/{neighbor.exercise_id}/log?{urlencode(nav_params)}"

                if index > 0:
                    prev_url = build_nav_url(day_exercises[index - 1])
                if index < len(day_exercises) - 1:
                    next_exercise_url = build_nav_url(day_exercises[index + 1])

    self_params = {}
    if block_exercise_id is not None:
        self_params["block_exercise_id"] = block_exercise_id
    if next is not None:
        self_params["next"] = next
    self_url = f"/exercises/{exercise_id}/log"
    if self_params:
        self_url += f"?{urlencode(self_params)}"

    now = datetime.now()
    context = {
        "exercise": exercise,
        "self_url": self_url,
        "today": now.date().isoformat(),
        "now_time": now.time().isoformat(timespec="minutes"),
        "training": training,
        "next": next,
        "block_exercise_id": block_exercise_id,
        "prev_url": prev_url,
        "next_exercise_url": next_exercise_url,
        "logged": logged,
    }
    context.update(history)
    return templates.TemplateResponse(
        request=request,
        name="exercises/log.html",
        context=context,
    )


@router.post("/exercises/{exercise_id}/log")
async def log_exercise_submit(
    exercise_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    weight: str = Form(""),
    reps: int = Form(...),
    workout_date: date_type | None = Form(None, alias="date"),
    set_time: time_type | None = Form(None, alias="time"),
    comment: str | None = Form(None),
    block_exercise_id: int | None = Form(None),
    next: str | None = Form(None),
):
    now = datetime.now()
    workout = get_or_create_workout(db, user.id, workout_date or now.date())
    set_time = set_time or now.time().replace(microsecond=0)

    next_order = (
        db.query(WorkoutSet).filter(WorkoutSet.workout_id == workout.id).count() + 1
    )

    db.add(
        WorkoutSet(
            workout_id=workout.id,
            exercise_id=exercise_id,
            weight=parse_optional_weight(weight),
            reps=reps,
            time=set_time,
            comment=comment or None,
            order=next_order,
        )
    )
    db.commit()

    redirect_url = f"/exercises/{exercise_id}/log"
    params = {"logged": "1"}
    if block_exercise_id is not None:
        params["block_exercise_id"] = block_exercise_id
    if next is not None:
        params["next"] = next
    redirect_url += f"?{urlencode(params)}"

    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/workout-sets/{set_id}/edit")
async def edit_workout_set_form(
    set_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    next: str | None = None,
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
            "next": next or f"/exercises/{exercise.id}/log",
        },
    )


@router.post("/workout-sets/{set_id}/edit")
async def edit_workout_set_submit(
    set_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    weight: str = Form(""),
    reps: int = Form(...),
    workout_date: date_type = Form(..., alias="date"),
    set_time: time_type = Form(..., alias="time"),
    comment: str | None = Form(None),
    next: str = Form(...),
):
    workout_set = get_own_workout_set(db, set_id, user.id)
    workout = db.get(Workout, workout_set.workout_id)

    old_workout_id = workout.id

    if workout.date != workout_date:
        new_workout = get_or_create_workout(db, user.id, workout_date)
        workout_set.workout_id = new_workout.id
        workout_set.order = (
            db.query(WorkoutSet)
            .filter(WorkoutSet.workout_id == new_workout.id)
            .count()
            + 1
        )

    workout_set.weight = parse_optional_weight(weight)
    workout_set.reps = reps
    workout_set.time = set_time
    workout_set.comment = comment or None
    db.flush()

    if workout.date != workout_date:
        delete_workout_if_empty(db, old_workout_id)

    db.commit()

    return RedirectResponse(url=next, status_code=303)


@router.post("/workout-sets/{set_id}/delete")
async def delete_workout_set(
    set_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    next: str = Form(...),
):
    workout_set = get_own_workout_set(db, set_id, user.id)
    workout_id = workout_set.workout_id

    db.delete(workout_set)
    db.flush()

    delete_workout_if_empty(db, workout_id)

    db.commit()

    return RedirectResponse(url=next, status_code=303)
