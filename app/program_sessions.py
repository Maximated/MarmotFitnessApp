import calendar
import math
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.block_exercises import group_by_superset
from app.database import get_db
from app.dependencies import require_user
from app.exercise_ratings import get_user_ratings_map
from app.workout_substitutions import apply_substitutions, get_substitution_map
from app.models import Block, BlockExercise, DayTemplate, Exercise, User, Workout, WorkoutSet
from app.programs import get_own_program
from app.templates import templates
from app.workouts import SCHEDULE_INTERVAL_DAYS, get_or_create_workout, recompute_schedule

router = APIRouter()


RING_RADIUS = 38


def ring_data(pct: float | None) -> dict | None:
    if pct is None:
        return None
    circumference = 2 * math.pi * RING_RADIUS
    clamped = max(0, min(pct, 100))
    offset = circumference * (1 - clamped / 100)
    return {
        "pct": round(pct),
        "circumference": round(circumference, 1),
        "offset": round(offset, 1),
        "hue": round(clamped * 1.2),
    }


def compute_session_stats(db: Session, workout: Workout, day_template_id: int) -> dict:
    blocks = db.query(Block).filter(Block.day_template_id == day_template_id).all()
    block_by_id = {block.id: block for block in blocks}
    block_exercises = (
        db.query(BlockExercise)
        .filter(BlockExercise.block_id.in_(block_by_id.keys()))
        .all()
    )

    all_sets = db.query(WorkoutSet).filter(WorkoutSet.workout_id == workout.id).all()
    sets_by_exercise: dict[int, list[WorkoutSet]] = {}
    sets_by_block_exercise: dict[int, list[WorkoutSet]] = {}
    for workout_set in all_sets:
        if workout_set.exercise_id is not None:
            sets_by_exercise.setdefault(workout_set.exercise_id, []).append(workout_set)
        elif workout_set.block_exercise_id is not None:
            sets_by_block_exercise.setdefault(workout_set.block_exercise_id, []).append(workout_set)

    weight_pcts = []
    reps_pcts = []
    warmup_planned = 0
    warmup_actual = 0
    # Progreso de la rutina: cada BlockExercise de la jornada cuenta como una
    # unidad igual (series o tiempo, con o sin catálogo), sin ponderación por tipo.
    exercises_total = len(block_exercises)
    exercises_completed = 0

    for block_exercise in block_exercises:
        if block_exercise.exercise_id is not None:
            exercise_sets = sets_by_exercise.get(block_exercise.exercise_id, [])
        else:
            exercise_sets = sets_by_block_exercise.get(block_exercise.id, [])
        block = block_by_id[block_exercise.block_id]

        if block_exercise.target_weight:
            weights = [s.weight for s in exercise_sets if s.weight is not None]
            avg_weight = sum(weights) / len(weights) if weights else 0
            weight_pcts.append(avg_weight / block_exercise.target_weight * 100)

        if block_exercise.modo_registro == "tiempo":
            durations = [s.duration_seconds for s in exercise_sets if s.duration_seconds is not None]
            if block_exercise.duracion_segundos:
                if block.type == "Calentamiento":
                    warmup_planned += block_exercise.duracion_segundos
                    warmup_actual += sum(durations)
                if durations and max(durations) >= block_exercise.duracion_segundos:
                    exercises_completed += 1
            elif durations:
                exercises_completed += 1
        else:
            if block_exercise.reps_max:
                reps = [s.reps for s in exercise_sets if s.reps is not None]
                avg_reps = sum(reps) / len(reps) if reps else 0
                reps_pcts.append(avg_reps / block_exercise.reps_max * 100)
            if len(exercise_sets) >= (block.num_sets or 1):
                exercises_completed += 1

    volume_kg = sum(
        (s.weight or 0) * (s.reps or 0) for s in all_sets if s.weight is not None and s.reps is not None
    )

    session_minutes = None
    times = [s.time for s in all_sets]
    if len(times) >= 2:
        earliest, latest = min(times), max(times)
        delta = datetime.combine(date.today(), latest) - datetime.combine(date.today(), earliest)
        session_minutes = round(delta.total_seconds() / 60)

    weight_pct = sum(weight_pcts) / len(weight_pcts) if weight_pcts else None
    reps_pct = sum(reps_pcts) / len(reps_pcts) if reps_pcts else None
    warmup_pct = (warmup_actual / warmup_planned * 100) if warmup_planned else None
    exercises_pct = (exercises_completed / exercises_total * 100) if exercises_total else None

    return {
        "weight_ring": ring_data(weight_pct),
        "reps_ring": ring_data(reps_pct),
        "warmup_ring": ring_data(warmup_pct),
        "warmup_planned_seconds": warmup_planned,
        "warmup_actual_seconds": warmup_actual,
        "exercises_ring": ring_data(exercises_pct),
        "exercises_completed": exercises_completed,
        "exercises_total": exercises_total,
        "volume_kg": round(volume_kg) if volume_kg else None,
        "session_minutes": session_minutes,
    }


def get_day_content(db: Session, day_template_id: int):
    blocks = (
        db.query(Block)
        .filter(Block.day_template_id == day_template_id)
        .order_by(Block.position)
        .all()
    )
    exercises_by_block = {}
    for block in blocks:
        exercises_by_block[block.id] = (
            db.query(BlockExercise, Exercise)
            .outerjoin(Exercise, BlockExercise.exercise_id == Exercise.id)
            .filter(BlockExercise.block_id == block.id)
            .order_by(BlockExercise.position)
            .all()
        )
    return blocks, exercises_by_block


@router.get("/programs/{program_id}/today")
async def program_today(
    program_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    program = get_own_program(db, program_id, user.id)
    today = date.today()

    if program.current_day_number is None:
        return templates.TemplateResponse(
            request=request,
            name="programs/today.html",
            context={"program": program, "state": "not_started"},
        )

    todays_workout = (
        db.query(Workout)
        .filter(
            Workout.user_id == user.id,
            Workout.date == today,
            Workout.program_id == program.id,
        )
        .first()
    )

    if todays_workout is not None:
        day_template = db.get(DayTemplate, todays_workout.day_template_id)
        blocks, exercises_by_block = get_day_content(db, day_template.id)
        exercises_by_block = apply_substitutions(
            db, exercises_by_block, get_substitution_map(db, todays_workout.id)
        )

        sets_completed_by_exercise = {
            row[0]: row[1]
            for row in db.query(WorkoutSet.exercise_id, func.count(WorkoutSet.id))
            .filter(WorkoutSet.workout_id == todays_workout.id, WorkoutSet.exercise_id.isnot(None))
            .group_by(WorkoutSet.exercise_id)
            .all()
        }
        sets_completed_by_block_exercise = {
            row[0]: row[1]
            for row in db.query(WorkoutSet.block_exercise_id, func.count(WorkoutSet.id))
            .filter(WorkoutSet.workout_id == todays_workout.id, WorkoutSet.block_exercise_id.isnot(None))
            .group_by(WorkoutSet.block_exercise_id)
            .all()
        }

        avg_weight_by_exercise = {
            row[0]: row[1]
            for row in db.query(WorkoutSet.exercise_id, func.avg(WorkoutSet.weight))
            .filter(
                WorkoutSet.workout_id == todays_workout.id,
                WorkoutSet.weight.isnot(None),
                WorkoutSet.exercise_id.isnot(None),
            )
            .group_by(WorkoutSet.exercise_id)
            .all()
        }
        avg_weight_by_block_exercise = {
            row[0]: row[1]
            for row in db.query(WorkoutSet.block_exercise_id, func.avg(WorkoutSet.weight))
            .filter(
                WorkoutSet.workout_id == todays_workout.id,
                WorkoutSet.weight.isnot(None),
                WorkoutSet.block_exercise_id.isnot(None),
            )
            .group_by(WorkoutSet.block_exercise_id)
            .all()
        }

        avg_duration_by_exercise = {
            row[0]: row[1]
            for row in db.query(WorkoutSet.exercise_id, func.avg(WorkoutSet.duration_seconds))
            .filter(
                WorkoutSet.workout_id == todays_workout.id,
                WorkoutSet.duration_seconds.isnot(None),
                WorkoutSet.exercise_id.isnot(None),
            )
            .group_by(WorkoutSet.exercise_id)
            .all()
        }
        avg_duration_by_block_exercise = {
            row[0]: row[1]
            for row in db.query(WorkoutSet.block_exercise_id, func.avg(WorkoutSet.duration_seconds))
            .filter(
                WorkoutSet.workout_id == todays_workout.id,
                WorkoutSet.duration_seconds.isnot(None),
                WorkoutSet.block_exercise_id.isnot(None),
            )
            .group_by(WorkoutSet.block_exercise_id)
            .all()
        }

        exercise_groups_by_block = {
            block_id: group_by_superset(attached)
            for block_id, attached in exercises_by_block.items()
        }

        exercise_ids = [
            exercise.id
            for attached in exercises_by_block.values()
            for _, exercise in attached
            if exercise is not None
        ]

        finished = todays_workout.finished_at is not None
        stats = compute_session_stats(db, todays_workout, day_template.id) if finished else None

        return templates.TemplateResponse(
            request=request,
            name="programs/today.html",
            context={
                "program": program,
                "state": "started",
                "day_template": day_template,
                "blocks": blocks,
                "exercise_groups_by_block": exercise_groups_by_block,
                "sets_completed_by_exercise": sets_completed_by_exercise,
                "sets_completed_by_block_exercise": sets_completed_by_block_exercise,
                "avg_weight_by_exercise": avg_weight_by_exercise,
                "avg_weight_by_block_exercise": avg_weight_by_block_exercise,
                "avg_duration_by_exercise": avg_duration_by_exercise,
                "avg_duration_by_block_exercise": avg_duration_by_block_exercise,
                "ratings": get_user_ratings_map(db, user.id, exercise_ids),
                "current_page_url": f"/programs/{program.id}/today",
                "finished": finished,
                "stats": stats,
            },
        )

    day_template = (
        db.query(DayTemplate)
        .filter(
            DayTemplate.program_id == program.id,
            DayTemplate.day_number == program.current_day_number,
        )
        .first()
    )

    return templates.TemplateResponse(
        request=request,
        name="programs/today.html",
        context={
            "program": program,
            "state": "ready",
            "day_template": day_template,
            "is_due": program.next_due_date is not None and program.next_due_date <= today,
            "next_due_date": program.next_due_date,
        },
    )


@router.post("/programs/{program_id}/start")
async def start_program(
    program_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    program = get_own_program(db, program_id, user.id)
    if program.current_day_number is None:
        program.current_day_number = 1
        program.next_due_date = date.today()
        db.commit()

    return RedirectResponse(url=f"/programs/{program.id}/today", status_code=303)


def begin_today_session(db: Session, program, user_id: int) -> None:
    today = date.today()

    day_template = (
        db.query(DayTemplate)
        .filter(
            DayTemplate.program_id == program.id,
            DayTemplate.day_number == program.current_day_number,
        )
        .first()
    )

    workout = get_or_create_workout(db, user_id, today)
    workout.program_id = program.id
    workout.day_template_id = day_template.id

    program.current_day_number = (program.current_day_number % program.cycle_days) + 1
    program.next_due_date = today + timedelta(days=SCHEDULE_INTERVAL_DAYS)


@router.post("/programs/{program_id}/today/start")
async def start_today_session(
    program_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    program = get_own_program(db, program_id, user.id)
    begin_today_session(db, program, user.id)
    db.commit()

    return RedirectResponse(url=f"/programs/{program.id}/today", status_code=303)


@router.post("/programs/{program_id}/today/mark-started")
async def mark_today_started(
    program_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    program = get_own_program(db, program_id, user.id)
    today = date.today()

    workout = (
        db.query(Workout)
        .filter(Workout.user_id == user.id, Workout.date == today, Workout.program_id == program.id)
        .first()
    )
    if workout is not None and workout.started_at is None:
        workout.started_at = datetime.now()
        db.commit()

    return Response(status_code=204)


@router.post("/programs/{program_id}/today/start-rest")
async def start_rest_timer(
    program_id: int,
    seconds: int,
    block_exercise_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    program = get_own_program(db, program_id, user.id)
    today = date.today()

    workout = (
        db.query(Workout)
        .filter(Workout.user_id == user.id, Workout.date == today, Workout.program_id == program.id)
        .first()
    )
    if workout is not None:
        workout.rest_until = datetime.now() + timedelta(seconds=seconds)
        workout.rest_total_seconds = seconds
        workout.active_block_exercise_id = block_exercise_id
        db.commit()

    return Response(status_code=204)


@router.post("/programs/{program_id}/begin")
async def begin_program_now(
    program_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    program = get_own_program(db, program_id, user.id)
    if program.current_day_number is None:
        program.current_day_number = 1
        program.next_due_date = date.today()
        db.flush()

    begin_today_session(db, program, user.id)
    db.commit()

    return RedirectResponse(url=f"/programs/{program.id}/today", status_code=303)


@router.post("/programs/{program_id}/today/finish")
async def finish_today_session(
    program_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    program = get_own_program(db, program_id, user.id)
    today = date.today()

    todays_workout = (
        db.query(Workout)
        .filter(
            Workout.user_id == user.id,
            Workout.date == today,
            Workout.program_id == program.id,
        )
        .first()
    )
    if todays_workout is not None and todays_workout.finished_at is None:
        todays_workout.finished_at = datetime.now()
        db.commit()

    return RedirectResponse(url=f"/programs/{program.id}/today", status_code=303)


def build_calendar_weeks(db: Session, program, year: int, month: int):
    today = date.today()
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    completed_dates = {
        row[0]
        for row in db.query(Workout.date)
        .filter(
            Workout.program_id == program.id,
            Workout.date >= first_day,
            Workout.date <= last_day,
        )
        .all()
    }

    due_dates = set()
    if program.next_due_date is not None:
        is_overdue = program.next_due_date <= today and today not in completed_dates
        anchor = today if is_overdue else program.next_due_date
        candidate = anchor
        while candidate <= last_day:
            if candidate >= first_day and candidate not in completed_dates:
                due_dates.add(candidate)
            candidate += timedelta(days=SCHEDULE_INTERVAL_DAYS)

    weeks = []
    cal = calendar.Calendar(firstweekday=0)
    week = []
    for day in cal.itermonthdates(year, month):
        if day.month != month:
            week.append(None)
        else:
            status = None
            if day in completed_dates:
                status = "done"
            elif day in due_dates:
                status = "due"
            week.append({"date": day, "status": status})
        if len(week) == 7:
            weeks.append(week)
            week = []

    return weeks, first_day, last_day


def get_next_two_sessions(program):
    if program.current_day_number is None or program.next_due_date is None:
        return []
    day_number_2 = (program.current_day_number % program.cycle_days) + 1
    return [
        (program.current_day_number, program.next_due_date),
        (day_number_2, program.next_due_date + timedelta(days=SCHEDULE_INTERVAL_DAYS)),
    ]


@router.get("/programs/{program_id}/calendar")
async def program_calendar(
    program_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    year: int | None = None,
    month: int | None = None,
):
    program = get_own_program(db, program_id, user.id)
    today = date.today()
    year = year or today.year
    month = month or today.month

    weeks, first_day, last_day = build_calendar_weeks(db, program, year, month)

    prev_month = (first_day - timedelta(days=1)).replace(day=1)
    next_month = last_day + timedelta(days=1)

    return templates.TemplateResponse(
        request=request,
        name="programs/calendar.html",
        context={
            "program": program,
            "year": year,
            "month": month,
            "month_name": first_day.strftime("%B %Y"),
            "weeks": weeks,
            "prev_year": prev_month.year,
            "prev_month": prev_month.month,
            "next_year": next_month.year,
            "next_month": next_month.month,
        },
    )


@router.get("/programs/{program_id}/sessions/{session_date}/detail")
async def view_session(
    program_id: int,
    session_date: date,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    program = get_own_program(db, program_id, user.id)

    workout = (
        db.query(Workout)
        .filter(
            Workout.user_id == user.id,
            Workout.date == session_date,
            Workout.program_id == program.id,
        )
        .first()
    )
    if workout is None:
        raise HTTPException(status_code=404)

    day_template = db.get(DayTemplate, workout.day_template_id)
    blocks, exercises_by_block = get_day_content(db, day_template.id) if day_template else ([], {})
    exercises_by_block = apply_substitutions(
        db, exercises_by_block, get_substitution_map(db, workout.id)
    )

    exercise_ids = [
        exercise.id
        for attached in exercises_by_block.values()
        for _, exercise in attached
        if exercise is not None
    ]

    return templates.TemplateResponse(
        request=request,
        name="programs/session.html",
        context={
            "program": program,
            "session_date": session_date,
            "day_template": day_template,
            "blocks": blocks,
            "exercises_by_block": exercises_by_block,
            "ratings": get_user_ratings_map(db, user.id, exercise_ids),
            "current_page_url": f"/programs/{program.id}/sessions/{session_date.isoformat()}/detail",
            "finished": workout.finished_at is not None,
        },
    )


@router.post("/programs/{program_id}/sessions/{session_date}/delete")
async def delete_session(
    program_id: int,
    session_date: date,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    program = get_own_program(db, program_id, user.id)

    workout = (
        db.query(Workout)
        .filter(
            Workout.user_id == user.id,
            Workout.date == session_date,
            Workout.program_id == program.id,
        )
        .first()
    )
    if workout is not None:
        db.delete(workout)
        db.flush()
        recompute_schedule(db, program)
        db.commit()

    return RedirectResponse(url=f"/programs/{program.id}/calendar", status_code=303)
