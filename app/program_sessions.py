import calendar
import math
from urllib.parse import urlencode
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.block_exercises import group_by_superset
from app.database import get_db
from app.dependencies import require_user
from app.exercise_ratings import (
    get_next_similar_exercise,
    get_previous_similar_exercise,
    get_user_ban,
    get_user_rating,
    get_user_ratings_map,
)
from app.workout_substitutions import (
    apply_substitutions,
    get_day_template_substitution_map,
    get_substitution_map,
    promote_day_template_substitutions_to_workout,
    set_day_template_substitution,
)
from app.models import Block, BlockExercise, DayTemplate, Exercise, ExerciseUserProgress, Program, User, Workout, WorkoutSet
from app.programs import get_own_day_template, get_own_program
from app.templates import templates
from app.workouts import (
    SCHEDULE_INTERVAL_DAYS,
    count_sets,
    get_or_create_workout,
    recompute_schedule,
    resolve_rest_step,
    touch_workout_activity,
)

router = APIRouter()


RING_RADIUS = 38
# Default bump applied to ExerciseUserProgress.current_weight once every set
# of an exercise hit reps_max in a finished session. Not yet configurable
# per-user/per-exercise -- flat for everyone until that's asked for.
WEIGHT_INCREMENT_KG = 2.5


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
    substitution_map = get_substitution_map(db, workout.id)

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
        effective_exercise_id = substitution_map.get(block_exercise.id, block_exercise.exercise_id)
        if effective_exercise_id is not None:
            exercise_sets = sets_by_exercise.get(effective_exercise_id, [])
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


def apply_weight_progression(db: Session, workout: Workout, day_template_id: int) -> None:
    """Bumps ExerciseUserProgress.current_weight for every "series"-mode
    exercise of the day where every logged set reached reps_max -- only for
    exercises that already have a progress row (creating the first one, by
    asking the user what weight to start from, is a separate feature not
    built yet). Falling short on reps never lowers the weight, that's left
    for later if it turns out to be needed."""
    blocks = db.query(Block).filter(Block.day_template_id == day_template_id).all()
    block_by_id = {block.id: block for block in blocks}
    block_exercises = (
        db.query(BlockExercise)
        .filter(BlockExercise.block_id.in_(block_by_id.keys()))
        .all()
    )
    substitution_map = get_substitution_map(db, workout.id)

    all_sets = db.query(WorkoutSet).filter(WorkoutSet.workout_id == workout.id).all()
    sets_by_exercise: dict[int, list[WorkoutSet]] = {}
    for workout_set in all_sets:
        if workout_set.exercise_id is not None:
            sets_by_exercise.setdefault(workout_set.exercise_id, []).append(workout_set)

    for block_exercise in block_exercises:
        if block_exercise.modo_registro != "series" or not block_exercise.reps_max:
            continue
        effective_exercise_id = substitution_map.get(block_exercise.id, block_exercise.exercise_id)
        if effective_exercise_id is None:
            continue

        progress = (
            db.query(ExerciseUserProgress)
            .filter(
                ExerciseUserProgress.user_id == workout.user_id,
                ExerciseUserProgress.exercise_id == effective_exercise_id,
            )
            .first()
        )
        if progress is None:
            continue

        block = block_by_id[block_exercise.block_id]
        exercise_sets = sets_by_exercise.get(effective_exercise_id, [])
        if len(exercise_sets) < (block.num_sets or 1):
            continue
        all_hit_reps_max = all(
            s.reps is not None and s.reps >= block_exercise.reps_max for s in exercise_sets
        )
        if all_hit_reps_max:
            progress.current_weight += WEIGHT_INCREMENT_KG


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
    """Always shows the full, clickable exercise list for today's due day
    -- whether or not anyone has actually started it yet. There is
    deliberately no separate "ready" gate/button here: viewing and editing
    (rating, swapping exercises) a day must never itself count as starting
    it, exactly like a future day's /preview. The only two things that
    really start it are logging a set (submit_workout_set) or starting the
    warmup timer (mark_today_started) -- both create the Workout lazily at
    that point, not before."""
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
        substitution_map = get_substitution_map(db, todays_workout.id)
    else:
        day_template = (
            db.query(DayTemplate)
            .filter(
                DayTemplate.program_id == program.id,
                DayTemplate.day_number == program.current_day_number,
            )
            .first()
        )
        # Whatever was prepared from this day's /preview screen shows here
        # too, before it's ever "really" started.
        substitution_map = get_day_template_substitution_map(db, day_template.id)

    blocks, exercises_by_block = get_day_content(db, day_template.id)
    exercises_by_block = apply_substitutions(db, exercises_by_block, substitution_map)

    if todays_workout is not None:
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
    else:
        sets_completed_by_exercise = {}
        sets_completed_by_block_exercise = {}
        avg_weight_by_exercise = {}
        avg_weight_by_block_exercise = {}
        avg_duration_by_exercise = {}
        avg_duration_by_block_exercise = {}

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

    finished = todays_workout is not None and todays_workout.finished_at is not None
    stats = compute_session_stats(db, todays_workout, day_template.id) if finished else None

    return templates.TemplateResponse(
        request=request,
        name="programs/today.html",
        context={
            "program": program,
            "state": "started",
            "workout_started": todays_workout is not None and todays_workout.started_at is not None,
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
            "today": today.isoformat(),
        },
    )


@router.get("/days/{day_template_id}/preview")
async def preview_day_template(
    day_template_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Look at a not-yet-startable day: same exercise-in-order layout as
    /today, but there's no start/finish form and nothing here ever creates
    or touches a Workout -- see the 24h-lock/same-date-collision reasoning
    in program_sessions history for why /today/start must stay the only
    way to actually begin a day. Rows ARE links now, into
    preview_block_exercise below: rating and swapping exercises ahead of
    time is safe (it never counts the day as done), it just wasn't wired
    up before."""
    day_template = get_own_day_template(db, day_template_id, user.id)
    program = db.get(Program, day_template.program_id)
    blocks, exercises_by_block = get_day_content(db, day_template.id)
    substitution_map = get_day_template_substitution_map(db, day_template.id)
    exercises_by_block = apply_substitutions(db, exercises_by_block, substitution_map)
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
    weight_targets = {
        row[0]: row[1]
        for row in db.query(ExerciseUserProgress.exercise_id, ExerciseUserProgress.current_weight)
        .filter(
            ExerciseUserProgress.user_id == user.id,
            ExerciseUserProgress.exercise_id.in_(exercise_ids),
        )
        .all()
    }

    return templates.TemplateResponse(
        request=request,
        name="programs/day_preview.html",
        context={
            "program": program,
            "day_template": day_template,
            "blocks": blocks,
            "exercise_groups_by_block": exercise_groups_by_block,
            "weight_targets": weight_targets,
            "ratings": get_user_ratings_map(db, user.id, exercise_ids),
            "self_url": f"/days/{day_template_id}/preview",
        },
    )


def _day_preview_exercise_url(
    day_template_id: int, block_exercise_id: int, exercise_id: int | None = None, substitute: bool = False
) -> str:
    params = {}
    if exercise_id is not None:
        params["exercise_id"] = exercise_id
    if substitute:
        params["substitute"] = "1"
    url = f"/days/{day_template_id}/preview/{block_exercise_id}"
    return f"{url}?{urlencode(params)}" if params else url


@router.get("/days/{day_template_id}/preview/{block_exercise_id}")
async def preview_block_exercise(
    day_template_id: int,
    block_exercise_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    exercise_id: int | None = None,
    substitute: bool = False,
):
    """Rate or swap a single exercise on a day that hasn't started yet --
    the "prep" counterpart to the real training screen. Deliberately
    minimal: no sets, no timers, no weight targets, nothing that implies a
    session is in progress. Substitutions made here are day-template-scoped
    (see app/workout_substitutions.py) until the day is actually started,
    at which point mark_today_started/start_rest_timer/submit_workout_set
    promote them onto the real Workout."""
    day_template = get_own_day_template(db, day_template_id, user.id)
    block_exercise = (
        db.query(BlockExercise)
        .join(Block, BlockExercise.block_id == Block.id)
        .filter(BlockExercise.id == block_exercise_id, Block.day_template_id == day_template.id)
        .first()
    )
    if block_exercise is None:
        raise HTTPException(status_code=404)
    block = db.get(Block, block_exercise.block_id)

    if substitute and exercise_id is not None:
        set_day_template_substitution(db, day_template.id, block_exercise.id, exercise_id)
        db.commit()
        return RedirectResponse(
            url=_day_preview_exercise_url(day_template_id, block_exercise_id, exercise_id),
            status_code=303,
        )

    substitution_map = get_day_template_substitution_map(db, day_template.id)
    effective_exercise_id = substitution_map.get(block_exercise.id, block_exercise.exercise_id)
    if exercise_id is None:
        exercise_id = effective_exercise_id
    elif exercise_id != effective_exercise_id:
        return RedirectResponse(
            url=_day_preview_exercise_url(day_template_id, block_exercise_id, effective_exercise_id),
            status_code=303,
        )

    exercise = db.get(Exercise, exercise_id) if exercise_id is not None else None

    day_exercises = (
        db.query(BlockExercise)
        .join(Block, BlockExercise.block_id == Block.id)
        .filter(Block.day_template_id == day_template.id)
        .order_by(Block.position, BlockExercise.position)
        .all()
    )
    day_exercise_ids = {
        substitution_map.get(be.id, be.exercise_id)
        for be in day_exercises
        if be.id != block_exercise.id
    } - {None}

    recycle_url = None
    recycle_back_url = None
    revert_url = None
    user_rating = None
    user_banned = False
    if exercise_id is not None:
        next_similar = get_next_similar_exercise(db, user.id, exercise_id, exclude_ids=day_exercise_ids)
        if next_similar is not None:
            recycle_url = _day_preview_exercise_url(
                day_template_id, block_exercise_id, next_similar.id, substitute=True
            )
        prev_similar = get_previous_similar_exercise(db, user.id, exercise_id, exclude_ids=day_exercise_ids)
        if prev_similar is not None:
            recycle_back_url = _day_preview_exercise_url(
                day_template_id, block_exercise_id, prev_similar.id, substitute=True
            )
        if block_exercise.exercise_id is not None and exercise_id != block_exercise.exercise_id:
            revert_url = _day_preview_exercise_url(
                day_template_id, block_exercise_id, block_exercise.exercise_id, substitute=True
            )
        user_rating = get_user_rating(db, user.id, exercise_id)
        user_banned = get_user_ban(db, user.id, exercise_id)

    return templates.TemplateResponse(
        request=request,
        name="programs/day_preview_exercise.html",
        context={
            "program": db.get(Program, day_template.program_id),
            "day_template": day_template,
            "block": block,
            "block_exercise": block_exercise,
            "exercise": exercise,
            "self_url": _day_preview_exercise_url(day_template_id, block_exercise_id, exercise_id),
            "recycle_url": recycle_url,
            "recycle_back_url": recycle_back_url,
            "revert_url": revert_url,
            "user_rating": user_rating,
            "user_banned": user_banned,
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


@router.post("/programs/{program_id}/today/mark-started")
async def mark_today_started(
    program_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """The warmup timer's actual play button -- one of the only two things
    that really start today's day (the other is logging a first set, see
    submit_workout_set). Creates the Workout lazily right here if nothing
    had touched it yet, instead of requiring a separate explicit "start"
    step before this could ever fire."""
    program = get_own_program(db, program_id, user.id)
    today = date.today()

    workout = get_or_create_workout(db, user.id, today)
    if workout.day_template_id is not None and workout.program_id != program.id:
        if workout.started_at is not None:
            # Today's slot is already really started under a different
            # program's session -- silently starting this one too would mix
            # its sets into that other Workout row.
            raise HTTPException(
                status_code=409,
                detail="Ya has registrado otra sesión hoy. Termínala antes de entrenar esta.",
            )
        # An uncommitted pick (see /today/choose-session) for another
        # program -- nothing was ever really started under it, so this
        # program's own due day is free to take over the slot.
        workout.day_template_id = None

    if workout.day_template_id is None:
        day_template = (
            db.query(DayTemplate)
            .filter(
                DayTemplate.program_id == program.id,
                DayTemplate.day_number == program.current_day_number,
            )
            .first()
        )
        workout.program_id = program.id
        if day_template is not None:
            workout.day_template_id = day_template.id
            workout.is_manual_session = False
            promote_day_template_substitutions_to_workout(db, day_template.id, workout.id)
    if workout.started_at is None:
        workout.started_at = datetime.now()
    touch_workout_activity(workout)
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

    workout = get_or_create_workout(db, user.id, today)
    if workout.day_template_id is not None and workout.program_id != program.id:
        if workout.started_at is not None:
            raise HTTPException(
                status_code=409,
                detail="Ya has registrado otra sesión hoy. Termínala antes de entrenar esta.",
            )
        workout.day_template_id = None

    if workout.day_template_id is None:
        day_template = (
            db.query(DayTemplate)
            .filter(
                DayTemplate.program_id == program.id,
                DayTemplate.day_number == program.current_day_number,
            )
            .first()
        )
        workout.program_id = program.id
        if day_template is not None:
            workout.day_template_id = day_template.id
            workout.is_manual_session = False
            promote_day_template_substitutions_to_workout(db, day_template.id, workout.id)
    touch_workout_activity(workout)
    workout.rest_until = datetime.now() + timedelta(seconds=seconds)
    workout.rest_total_seconds = seconds
    # Manually-started timer (e.g. calentamiento): points back at itself,
    # not "the next exercise" -- nothing has been completed yet, unlike
    # the post-log rest timer in submit_workout_set.
    workout.active_block_exercise_id = block_exercise_id
    # Fallback text for the (not reachable via the current UI, but
    # possible via a direct call) case with no block_exercise_id --
    # without this, send_push_for_workout's `not rest_notify_text`
    # guard would silently skip the push with no error and no retry.
    workout.rest_notify_text = "Descanso terminado."
    workout.rest_push_sent_at = None

    block_exercise = (
        db.get(BlockExercise, block_exercise_id) if block_exercise_id is not None else None
    )
    if block_exercise is not None:
        block = db.get(Block, block_exercise.block_id)
        day_exercises = (
            db.query(BlockExercise)
            .join(Block, BlockExercise.block_id == Block.id)
            .filter(Block.day_template_id == block.day_template_id)
            .order_by(Block.position, BlockExercise.position)
            .all()
        )
        substitution_map = get_substitution_map(db, workout.id)
        effective_exercise_id = substitution_map.get(block_exercise.id, block_exercise.exercise_id)
        sets_completed_today = count_sets(db, workout.id, effective_exercise_id, block_exercise.id)
        notify_text, _target_be, _prompt_finish = resolve_rest_step(
            db, block_exercise, block, day_exercises, workout.id, sets_completed_today
        )
        workout.rest_notify_text = notify_text
        workout.rest_push_sent_at = None

    db.commit()

    return Response(status_code=204)


def finish_workout(db: Session, program: Program, workout: Workout) -> None:
    """The one and only place a workout is marked done and the schedule
    advances -- called from the explicit finish button/prompt AND from
    inactivity_poller's auto-finish (app/main.py). Never called just from
    starting a session or from passive viewing/rating/recycling.

    A manually-picked session (see /today/choose-session) still gets its
    weight progression applied -- the exercises were genuinely done -- but
    never advances current_day_number/next_due_date: it was deliberately
    picked outside the normal rotation, so it must not push it."""
    if workout.finished_at is not None:
        return
    if workout.day_template_id is not None:
        apply_weight_progression(db, workout, workout.day_template_id)
        if not workout.is_manual_session:
            day_template = db.get(DayTemplate, workout.day_template_id)
            if day_template is not None:
                program.current_day_number = (day_template.day_number % program.cycle_days) + 1
    if not workout.is_manual_session:
        program.next_due_date = date.today() + timedelta(days=SCHEDULE_INTERVAL_DAYS)
    workout.finished_at = datetime.now()


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
    if todays_workout is not None:
        finish_workout(db, program, todays_workout)
        db.commit()

    return RedirectResponse(url=f"/programs/{program.id}/today", status_code=303)


@router.get("/today/choose-session")
async def choose_session_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Exceptional path alongside the normal calendar: pick any day from
    any of the user's programs to do today, without moving that (or any)
    program's rotation -- see finish_workout/recompute_schedule's
    is_manual_session handling. Lists every program, not just the active
    one, since there's no "archived" state distinct from "not active" in
    this model (archiving a program just sets is_active=False)."""
    programs = (
        db.query(Program)
        .filter(Program.user_id == user.id)
        .order_by(Program.is_active.desc(), Program.name)
        .all()
    )

    day_templates_by_program: dict[int, list[DayTemplate]] = {}
    day_summaries: dict[int, str] = {}
    for program in programs:
        day_templates = (
            db.query(DayTemplate)
            .filter(DayTemplate.program_id == program.id)
            .order_by(DayTemplate.day_number)
            .all()
        )
        day_templates_by_program[program.id] = day_templates

        blocks = (
            db.query(Block)
            .join(DayTemplate, Block.day_template_id == DayTemplate.id)
            .filter(DayTemplate.program_id == program.id)
            .order_by(Block.day_template_id, Block.position)
            .all()
        )
        blocks_by_day: dict[int, list[Block]] = {}
        for block in blocks:
            blocks_by_day.setdefault(block.day_template_id, []).append(block)
        for day_template in day_templates:
            parts = []
            for block in blocks_by_day.get(day_template.id, []):
                label = block.type
                if block.muscle_group:
                    label += f" · {block.muscle_group}"
                label += f" ({block.num_exercises} ej.)"
                parts.append(label)
            day_summaries[day_template.id] = ", ".join(parts) if parts else "Sin bloques todavía"

    done_before = {
        row[0]
        for row in db.query(DayTemplate.id)
        .join(Workout, Workout.day_template_id == DayTemplate.id)
        .join(Program, DayTemplate.program_id == Program.id)
        .filter(Program.user_id == user.id, Workout.finished_at.isnot(None))
        .distinct()
        .all()
    }

    return templates.TemplateResponse(
        request=request,
        name="programs/choose_session.html",
        context={
            "programs": programs,
            "day_templates_by_program": day_templates_by_program,
            "day_summaries": day_summaries,
            "done_before": done_before,
        },
    )


@router.post("/today/choose-session")
async def choose_session_submit(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    day_template_id: int = Form(...),
):
    """Only attaches the chosen day to today's Workout row -- so /today
    shows it right away instead of the program's normal due day -- but
    never sets started_at. Picking a session is exactly like previewing a
    future day: it must not itself count as starting it. That only
    happens via mark_today_started (warmup timer) or submit_workout_set
    (first logged set), same as every other day. Since nothing was really
    started yet, the user is free to come back and pick a different day
    again -- only a real start locks today's slot in."""
    day_template = get_own_day_template(db, day_template_id, user.id)
    program = db.get(Program, day_template.program_id)
    today = date.today()

    workout = get_or_create_workout(db, user.id, today)
    if workout.day_template_id is not None and workout.day_template_id != day_template.id:
        if workout.started_at is not None:
            raise HTTPException(
                status_code=409,
                detail="Ya has empezado otra sesión hoy. Termínala antes de elegir otra.",
            )
        workout.day_template_id = None

    if workout.day_template_id is None:
        workout.program_id = program.id
        workout.day_template_id = day_template.id
        # Picking exactly the day that was already due for this program is
        # just the normal flow via the chooser -- finishing it should still
        # advance the rotation like any other day. Only a day that isn't
        # what this program's own cycle expects counts as a manual,
        # off-cycle session.
        workout.is_manual_session = day_template.day_number != program.current_day_number
        promote_day_template_substitutions_to_workout(db, day_template.id, workout.id)
        db.commit()

    return RedirectResponse(url=f"/programs/{program.id}/today", status_code=303)


@router.post("/programs/{program_id}/today/keep-going")
async def keep_today_session_going(
    program_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """The user answered "no, not done yet" to the inactivity prompt (or is
    otherwise still active) -- resets the inactivity clock so
    inactivity_poller doesn't auto-finish a session that's still in use."""
    program = get_own_program(db, program_id, user.id)
    today = date.today()

    workout = (
        db.query(Workout)
        .filter(Workout.user_id == user.id, Workout.date == today, Workout.program_id == program.id)
        .first()
    )
    if workout is not None:
        touch_workout_activity(workout)
        db.commit()

    return Response(status_code=204)


def build_calendar_weeks(db: Session, program, year: int, month: int):
    today = date.today()
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    # Los días "hechos" son del usuario, no del programa concreto que esté
    # activo ahora -- un entrenamiento no debe desaparecer del calendario
    # solo porque después se archivó el programa con el que se hizo.
    # Se exige al menos una serie registrada: la fila Workout puede existir
    # (calentamiento empezado, sesión elegida a mano...) sin que se haya
    # entrenado nada, así que su mera existencia no puede ser el criterio o
    # el día quedaría marcado como realizado sin haberlo hecho.
    completed_dates = {
        row[0]
        for row in db.query(Workout.date)
        .join(WorkoutSet, WorkoutSet.workout_id == Workout.id)
        .filter(
            Workout.user_id == program.user_id,
            Workout.date >= first_day,
            Workout.date <= last_day,
        )
        .distinct()
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


def get_next_sessions(program, count: int = 2):
    if program.current_day_number is None or program.next_due_date is None:
        return []
    sessions = []
    day_number = program.current_day_number
    due_date = program.next_due_date
    for _ in range(count):
        sessions.append((day_number, due_date))
        day_number = (day_number % program.cycle_days) + 1
        due_date = due_date + timedelta(days=SCHEDULE_INTERVAL_DAYS)
    return sessions


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

    # El workout de ese día puede pertenecer a un programa distinto del que
    # se está navegando ahora mismo (por ejemplo, uno ya archivado) -- se
    # busca solo por usuario+fecha, nunca por program_id.
    workout = (
        db.query(Workout)
        .filter(
            Workout.user_id == user.id,
            Workout.date == session_date,
        )
        .first()
    )
    if workout is None:
        raise HTTPException(status_code=404)

    owning_program = None
    if workout.program_id is not None:
        owning_program = db.get(Program, workout.program_id)
    if owning_program is None:
        owning_program = program

    day_template = db.get(DayTemplate, workout.day_template_id) if workout.day_template_id is not None else None
    blocks, exercises_by_block = get_day_content(db, day_template.id) if day_template else ([], {})
    exercises_by_block = apply_substitutions(
        db, exercises_by_block, get_substitution_map(db, workout.id)
    )

    # workouts.day_template_id is ON DELETE SET NULL -- editing or deleting
    # the day template later (renaming a day, changing the program's
    # structure, re-importing it) silently nulls it on every past workout
    # that pointed at it, even though the actual WorkoutSets are untouched
    # (that's why the per-exercise history still shows them fine). When
    # that leaves nothing to resolve the original block layout from,
    # rebuild the view directly from what was actually logged that day
    # instead of showing a blank page for a session that really happened.
    logged_exercises = None
    if not any(exercises_by_block.get(block.id) for block in blocks):
        logged_sets = (
            db.query(WorkoutSet)
            .filter(WorkoutSet.workout_id == workout.id)
            .order_by(WorkoutSet.order)
            .all()
        )
        seen: dict[int | str, dict] = {}
        for workout_set in logged_sets:
            key = (
                workout_set.exercise_id
                if workout_set.exercise_id is not None
                else f"pending:{workout_set.block_exercise_id}"
            )
            entry = seen.get(key)
            if entry is None:
                entry = {
                    "exercise": (
                        db.get(Exercise, workout_set.exercise_id)
                        if workout_set.exercise_id is not None
                        else None
                    ),
                    "pending_name": workout_set.pending_name,
                    "set_count": 0,
                }
                seen[key] = entry
            entry["set_count"] += 1
        if seen:
            logged_exercises = list(seen.values())

    exercise_ids = [
        exercise.id
        for attached in exercises_by_block.values()
        for _, exercise in attached
        if exercise is not None
    ]
    if logged_exercises:
        exercise_ids += [
            item["exercise"].id for item in logged_exercises if item["exercise"] is not None
        ]

    return templates.TemplateResponse(
        request=request,
        name="programs/session.html",
        context={
            "program": owning_program,
            "session_date": session_date,
            "day_template": day_template,
            "blocks": blocks,
            "exercises_by_block": exercises_by_block,
            "logged_exercises": logged_exercises,
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

    # Igual que en view_session: el workout de esa fecha puede pertenecer a
    # un programa distinto (uno ya archivado), así que se busca solo por
    # usuario+fecha.
    workout = (
        db.query(Workout)
        .filter(
            Workout.user_id == user.id,
            Workout.date == session_date,
        )
        .first()
    )
    if workout is not None:
        owning_program_id = workout.program_id
        db.delete(workout)
        db.flush()
        # El recálculo de progreso tiene que aplicarse al programa dueño del
        # workout borrado, no al que se estaba navegando -- si son distintos
        # (p. ej. borrando una sesión antigua de un programa ya archivado),
        # recalcular el programa activo actual lo desincronizaría sin motivo.
        if owning_program_id is not None:
            owning_program = db.get(Program, owning_program_id)
            if owning_program is not None:
                recompute_schedule(db, owning_program)
        db.commit()

    return RedirectResponse(url=f"/programs/{program.id}/calendar", status_code=303)
