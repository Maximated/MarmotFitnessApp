import calendar
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_user
from app.models import Block, BlockExercise, DayTemplate, Exercise, User, Workout, WorkoutSet
from app.programs import get_own_program
from app.templates import templates
from app.workouts import SCHEDULE_INTERVAL_DAYS, get_or_create_workout, recompute_schedule

router = APIRouter()


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
            .join(Exercise, BlockExercise.exercise_id == Exercise.id)
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

        sets_completed_by_exercise = {
            row[0]: row[1]
            for row in db.query(WorkoutSet.exercise_id, func.count(WorkoutSet.id))
            .filter(WorkoutSet.workout_id == todays_workout.id)
            .group_by(WorkoutSet.exercise_id)
            .all()
        }

        return templates.TemplateResponse(
            request=request,
            name="programs/today.html",
            context={
                "program": program,
                "state": "started",
                "day_template": day_template,
                "blocks": blocks,
                "exercises_by_block": exercises_by_block,
                "sets_completed_by_exercise": sets_completed_by_exercise,
                "finished": todays_workout.finished_at is not None,
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


@router.post("/programs/{program_id}/today/start")
async def start_today_session(
    program_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    program = get_own_program(db, program_id, user.id)
    today = date.today()

    day_template = (
        db.query(DayTemplate)
        .filter(
            DayTemplate.program_id == program.id,
            DayTemplate.day_number == program.current_day_number,
        )
        .first()
    )

    workout = get_or_create_workout(db, user.id, today)
    workout.program_id = program.id
    workout.day_template_id = day_template.id

    program.current_day_number = (program.current_day_number % program.cycle_days) + 1
    program.next_due_date = today + timedelta(days=SCHEDULE_INTERVAL_DAYS)
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

    is_due_today = (
        program.next_due_date is not None
        and program.next_due_date <= today
        and today not in completed_dates
    )

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
            elif day == today and is_due_today:
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


@router.get("/programs/{program_id}/sessions/{session_date}")
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

    return templates.TemplateResponse(
        request=request,
        name="programs/session.html",
        context={
            "program": program,
            "session_date": session_date,
            "day_template": day_template,
            "blocks": blocks,
            "exercises_by_block": exercises_by_block,
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
