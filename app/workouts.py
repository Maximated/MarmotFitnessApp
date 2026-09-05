from datetime import date as date_type
from datetime import datetime
from datetime import time as time_type
from datetime import timedelta
from datetime import timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_user
from app.exercise_history import build_exercise_history, format_day_header
from app.http_utils import safe_next, wants_json
from app.exercise_ratings import (
    get_next_similar_exercise,
    get_previous_similar_exercise,
    get_similar_exercises,
    get_user_ban,
    get_user_rating,
)
from app.workout_substitutions import (
    get_day_template_substitution_map,
    get_substitution_map,
    promote_day_template_substitutions_to_workout,
    set_day_template_substitution,
    set_substitution,
)
from app.models import Block, BlockExercise, DayTemplate, Exercise, ExerciseUserProgress, Program, User, Workout, WorkoutSet
from app.templates import templates
from app.training_urls import training_url

router = APIRouter()

SCHEDULE_INTERVAL_DAYS = 2


def recompute_schedule(db: Session, program: Program) -> None:
    """Re-anchors the schedule on the most recently FINISHED workout --
    never on one that's merely in progress or was left open. Same rule as
    finish_today_session: only a genuine finish can move
    current_day_number/next_due_date forward. Manually-picked sessions
    (see /today/choose-session) are excluded too -- they never counted
    toward the rotation when they finished, so they can't anchor it here
    either."""
    last_workout = (
        db.query(Workout)
        .filter(
            Workout.program_id == program.id,
            Workout.finished_at.isnot(None),
            Workout.is_manual_session.is_(False),
        )
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


def touch_workout_activity(workout: Workout) -> None:
    """Marks the workout as just having had real user activity -- resets
    the inactivity-prompt clock (see inactivity_poller in app/main.py) so a
    session the user is actually still using never gets auto-finished out
    from under them."""
    workout.last_activity_at = datetime.now(timezone.utc)
    workout.inactivity_prompt_sent_at = None


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


def parse_optional_weight(raw: str) -> float:
    return float(raw) if raw.strip() else 0.0


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


def count_sets(db: Session, workout_id: int, exercise_id: int | None, block_exercise_id: int) -> int:
    query = db.query(WorkoutSet).filter(WorkoutSet.workout_id == workout_id)
    if exercise_id is not None:
        query = query.filter(WorkoutSet.exercise_id == exercise_id)
    else:
        query = query.filter(WorkoutSet.block_exercise_id == block_exercise_id)
    return query.count()


def resolve_rest_step(
    db: Session,
    block_exercise: BlockExercise,
    block: Block,
    day_exercises: list[BlockExercise],
    workout_id: int | None,
    sets_completed_today: int,
) -> tuple[str, BlockExercise | None, bool]:
    """What should happen once this exercise's rest/duration countdown ends:
    the notification text, and which block_exercise the header timer and
    the push notification should point to next -- the superset partner
    while a round is still in progress, the next exercise in the day once
    this one (or the pair) is fully done, or None if there's nowhere new to
    go yet (prompt_finish=True if that's because the day is over).

    Computed independently of any specific page/request (no `next`
    return-to param, no URL building) so it can run both from a live page
    render and right when a set is logged, with no page ever having to
    load again for the text to exist."""
    substitution_map = get_substitution_map(db, workout_id)

    def effective_exercise_id(be: BlockExercise) -> int | None:
        return substitution_map.get(be.id, be.exercise_id)

    def display_name(be: BlockExercise) -> str:
        eff = effective_exercise_id(be)
        if eff is not None:
            ex = db.get(Exercise, eff)
            if ex is not None:
                return ex.name
        return be.pending_name or "el ejercicio"

    superset_partner = None
    if block_exercise.is_superset_with_next:
        superset_partner = (
            db.query(BlockExercise)
            .filter(
                BlockExercise.block_id == block_exercise.block_id,
                BlockExercise.position == block_exercise.position + 1,
            )
            .first()
        )
    else:
        prev_in_block = (
            db.query(BlockExercise)
            .filter(
                BlockExercise.block_id == block_exercise.block_id,
                BlockExercise.position == block_exercise.position - 1,
            )
            .first()
        )
        if prev_in_block is not None and prev_in_block.is_superset_with_next:
            superset_partner = prev_in_block

    partner_sets_completed_today = 0
    if superset_partner is not None and workout_id is not None:
        partner_exercise_id = effective_exercise_id(superset_partner)
        partner_sets_completed_today = count_sets(
            db, workout_id, partner_exercise_id, superset_partner.id
        )

    index = None
    partner_index = None
    for i, day_exercise in enumerate(day_exercises):
        if day_exercise.id == block_exercise.id:
            index = i
        if superset_partner is not None and day_exercise.id == superset_partner.id:
            partner_index = i

    superset_done = (
        superset_partner is not None
        and block.num_sets is not None
        and sets_completed_today >= block.num_sets
        and partner_sets_completed_today >= block.num_sets
    )

    target_be = None
    prompt_finish = False
    if superset_partner is not None and not superset_done:
        target_be = superset_partner
    elif block_exercise.modo_registro == "tiempo":
        if index is not None:
            if index < len(day_exercises) - 1:
                target_be = day_exercises[index + 1]
            else:
                prompt_finish = True
    elif superset_done or (block.num_sets and sets_completed_today >= block.num_sets and index is not None):
        exit_index = max(index, partner_index) if partner_index is not None else index
        if exit_index < len(day_exercises) - 1:
            target_be = day_exercises[exit_index + 1]
        else:
            prompt_finish = True

    current_name = display_name(block_exercise)
    next_name = display_name(target_be) if target_be is not None else None

    if block_exercise.modo_registro == "tiempo":
        if next_name:
            notify_text = f"{current_name} completado. Siguiente: {next_name}."
        else:
            notify_text = f"{current_name} completado. ¡Entrenamiento terminado!"
    else:
        sets_remaining = None
        if block.num_sets is not None:
            sets_remaining = max(0, block.num_sets - sets_completed_today)
        if sets_remaining and next_name:
            notify_text = (
                f"El tiempo de descanso del ejercicio {current_name} ha terminado. "
                f"Te quedan {sets_remaining} series para pasar al ejercicio {next_name}."
            )
        elif sets_remaining:
            notify_text = (
                f"El tiempo de descanso del ejercicio {current_name} ha terminado. "
                f"Te quedan {sets_remaining} series."
            )
        elif next_name:
            notify_text = (
                f"Descanso terminado. {current_name} completado — pasa al ejercicio {next_name}."
            )
        else:
            notify_text = f"Descanso terminado. {current_name} completado."

    return notify_text, target_be, prompt_finish


def resolve_weight_progress_prompt(
    db: Session,
    user_id: int,
    exercise_id: int | None,
    block_exercise: BlockExercise,
    block: Block,
    todays_workout: Workout | None,
    sets_completed_today: int,
) -> tuple[bool, float | None]:
    """Whether to ask what weight to start tracking for this exercise --
    only right after the log action that completed all of today's sets for
    it. Asks the first time nothing is tracked yet, and again any time the
    weight just logged has overtaken the tracked target -- e.g. the user
    pushed past it on their own, ahead of apply_weight_progression's own
    automatic bump. Never asks to go DOWN: a lighter set (a bad day, a
    deload) shouldn't second-guess an already-tracked target."""
    if (
        exercise_id is None
        or block_exercise.modo_registro != "series"
        or sets_completed_today != block.num_sets
        or todays_workout is None
    ):
        return False, None

    last_set = (
        db.query(WorkoutSet)
        .filter(WorkoutSet.workout_id == todays_workout.id, WorkoutSet.exercise_id == exercise_id)
        .order_by(WorkoutSet.order.desc())
        .first()
    )
    if last_set is None or not last_set.weight:
        return False, None

    existing_progress = (
        db.query(ExerciseUserProgress)
        .filter(
            ExerciseUserProgress.user_id == user_id,
            ExerciseUserProgress.exercise_id == exercise_id,
        )
        .first()
    )
    if existing_progress is not None and last_set.weight <= existing_progress.current_weight:
        return False, None

    return True, last_set.weight


def resolve_weight_target(
    db: Session, user_id: int, exercise_id: int | None, block_exercise: BlockExercise
) -> float | None:
    """The weight to show/suggest for this exercise -- ExerciseUserProgress
    once it exists, falling back to the block's initial manual suggestion."""
    weight_target = block_exercise.target_weight
    if exercise_id is not None:
        progress = (
            db.query(ExerciseUserProgress)
            .filter(
                ExerciseUserProgress.user_id == user_id,
                ExerciseUserProgress.exercise_id == exercise_id,
            )
            .first()
        )
        if progress is not None:
            weight_target = progress.current_weight
    return weight_target


def build_training_state(
    todays_workout: Workout | None,
    block: Block,
    sets_completed_today: int,
) -> dict:
    """Read-only snapshot of the server's current truth for the ring and
    the rest timer -- used both by the optimistic-log JSON response and by
    a passive client-side re-sync (e.g. after the tab was backgrounded),
    so the client is never left trusting its own drifted idea of these
    values instead of asking the server again."""
    return {
        "sets_completed": sets_completed_today,
        "sets_target": block.num_sets,
        "rest_until": (
            todays_workout.rest_until.isoformat()
            if todays_workout is not None and todays_workout.rest_until is not None
            else None
        ),
        "rest_total_seconds": todays_workout.rest_total_seconds if todays_workout is not None else None,
        "rest_notify_text": todays_workout.rest_notify_text if todays_workout is not None else None,
    }


def find_active_block_exercise(
    db: Session, user: User, exercise_id: int, session_date: date_type | None
) -> int | None:
    """A bare /exercises/{id}/log link (no block_exercise_id) normally means
    a genuine catálogo lookup -- but if this exercise is actually part of
    the day being trained/browsed (through any active substitution), route
    it back into that day's context instead. Without this, any entry point
    that drops block_exercise_id off the URL (a stale bookmark, an OS/
    browser notification opened at its own idea of the URL, a link built
    before this slot existed) strands the user on a page with no pin, no
    superset bar, no day nav -- indistinguishable from having lost all of
    it, even though it never actually left the Workout row."""
    today = session_date or date_type.today()
    workout = db.query(Workout).filter(Workout.user_id == user.id, Workout.date == today).first()
    if workout is None or workout.day_template_id is None:
        return None
    day_exercises = (
        db.query(BlockExercise)
        .join(Block, BlockExercise.block_id == Block.id)
        .filter(Block.day_template_id == workout.day_template_id)
        .all()
    )
    substitution_map = get_substitution_map(db, workout.id)
    for day_exercise in day_exercises:
        effective_exercise_id = substitution_map.get(day_exercise.id, day_exercise.exercise_id)
        if effective_exercise_id == exercise_id:
            return day_exercise.id
    return None


async def render_training_log(
    request: Request,
    db: Session,
    user: User,
    exercise_id: int | None,
    block_exercise_id: int,
    next: str | None,
    logged: bool,
    substitute: bool,
    pin: str | None = None,
    session_date: date_type | None = None,
    unpin: bool = False,
    preview: bool = False,
):
    """Shared training-screen logic for both /exercises/{id}/log?block_exercise_id=
    (has a catalog Exercise) and /block-exercises/{id}/log (no catálogo,
    pending_name only).

    `session_date` is what makes this page reusable for browsing a PAST
    day's session (see programs/session.html) instead of only ever "today"
    -- it defaults to real today (unchanged live-training behavior) but,
    when given, every "today" concept below (which substitution is active
    for this slot, sets completed, rest step, superset partner progress)
    resolves against that date's Workout instead. Without this, following
    a link from a past day's exercise list would silently redirect to
    whatever TODAY's (unrelated) substitution happens to be for that same
    block_exercise slot -- landing on a completely different exercise than
    the one actually logged that day.

    `preview` is the same idea for a day that hasn't happened yet at all
    (see /days/{id}/preview): there's no Workout to browse, only the
    day-template itself, so the set-logging form is hidden (see
    exercises/log.html) -- everything else (swipe between exercises,
    superset partner, history, rating, recycling) stays identical to the
    real training screen on purpose."""
    block_exercise = (
        db.query(BlockExercise)
        .join(Block, BlockExercise.block_id == Block.id)
        .join(DayTemplate, Block.day_template_id == DayTemplate.id)
        .join(Program, DayTemplate.program_id == Program.id)
        .filter(BlockExercise.id == block_exercise_id, Program.user_id == user.id)
        .first()
    )
    if block_exercise is None:
        raise HTTPException(status_code=404)

    block = db.get(Block, block_exercise.block_id)
    day_template = db.get(DayTemplate, block.day_template_id)
    today = session_date or date_type.today()
    todays_workout = (
        db.query(Workout)
        .filter(Workout.user_id == user.id, Workout.date == today)
        .first()
    )
    # A Workout that's still unattached (day_template_id is None -- the
    # normal state before the day is really started, see
    # mark_today_started/submit_workout_set) is still "the" workout for
    # today's due day. But one that's DEFINITELY attached to some OTHER day
    # must not leak in here -- without this, previewing a day that isn't
    # today's due day (or a stray/aborted date-collision, see
    # /today/choose-session) would show whatever workout happens to sit on
    # today's calendar date instead: its sets, its pin, its rest timer, none
    # of which belong to the day actually on screen.
    if (
        todays_workout is not None
        and todays_workout.day_template_id is not None
        and todays_workout.day_template_id != day_template.id
    ):
        todays_workout = None

    if substitute and exercise_id is not None:
        # No Workout yet means today's day hasn't really started (see
        # program_today/submit_workout_set) -- the swap is prepared at the
        # day-template level instead, exactly like a future day's
        # /preview, and gets promoted the moment real activity starts.
        if todays_workout is not None:
            set_substitution(db, todays_workout.id, block_exercise.id, exercise_id)
        else:
            set_day_template_substitution(db, day_template.id, block_exercise.id, exercise_id)
        db.commit()
        redirect_params = {"block_exercise_id": block_exercise_id}
        if next is not None:
            redirect_params["next"] = next
        if pin is not None:
            redirect_params["pin"] = pin
        if session_date is not None:
            redirect_params["session_date"] = session_date.isoformat()
        if preview:
            redirect_params["preview"] = "1"
        return RedirectResponse(
            url=training_url(block_exercise_id, exercise_id, redirect_params), status_code=303
        )

    substitution_map = (
        get_substitution_map(db, todays_workout.id)
        if todays_workout is not None
        else get_day_template_substitution_map(db, day_template.id)
    )
    effective_exercise_id = substitution_map.get(block_exercise.id, block_exercise.exercise_id)
    if effective_exercise_id != exercise_id:
        redirect_params = {"block_exercise_id": block_exercise_id}
        if next is not None:
            redirect_params["next"] = next
        if pin is not None:
            redirect_params["pin"] = pin
        if session_date is not None:
            redirect_params["session_date"] = session_date.isoformat()
        if logged:
            redirect_params["logged"] = "1"
        if preview:
            redirect_params["preview"] = "1"
        return RedirectResponse(
            url=training_url(block_exercise_id, effective_exercise_id, redirect_params),
            status_code=303,
        )

    exercise = db.get(Exercise, exercise_id) if exercise_id is not None else None

    sets_completed_today = 0
    if todays_workout is not None:
        sets_completed_today = count_sets(db, todays_workout.id, exercise_id, block_exercise.id)

    # Passive re-sync: the client asks for this (instead of a full page
    # reload) when the tab regains focus after being backgrounded, or
    # whenever it wants to double-check the ring/rest-timer against the
    # server's actual state instead of trusting whatever it was showing
    # while unattended. No `next`/nav/similar-exercise computation needed
    # for this, so it returns before any of that gets built below.
    if wants_json(request):
        return JSONResponse(build_training_state(todays_workout, block, sets_completed_today))

    def build_nav_url(neighbor: BlockExercise) -> str:
        nav_params = {"block_exercise_id": neighbor.id}
        if next is not None:
            nav_params["next"] = next
        if effective_pin is not None:
            nav_params["pin"] = effective_pin
        if session_date is not None:
            nav_params["session_date"] = session_date.isoformat()
        if preview:
            nav_params["preview"] = "1"
        neighbor_exercise_id = substitution_map.get(neighbor.id, neighbor.exercise_id)
        return training_url(neighbor.id, neighbor_exercise_id, nav_params)

    def build_recycle_url(candidate_exercise_id: int) -> str:
        nav_params = {"block_exercise_id": block_exercise.id, "substitute": "1"}
        if next is not None:
            nav_params["next"] = next
        if effective_pin is not None:
            nav_params["pin"] = effective_pin
        if session_date is not None:
            nav_params["session_date"] = session_date.isoformat()
        if preview:
            nav_params["preview"] = "1"
        return training_url(block_exercise.id, candidate_exercise_id, nav_params)

    day_exercises = (
        db.query(BlockExercise)
        .join(Block, BlockExercise.block_id == Block.id)
        .filter(Block.day_template_id == block.day_template_id)
        .order_by(Block.position, BlockExercise.position)
        .all()
    )
    # Never suggest, as a "similar" recycle candidate, an exercise that's
    # already sitting elsewhere in today's day (resolved through any active
    # substitutions) -- excludes the current slot itself so recycling still
    # offers alternatives even when re-cycling back toward it.
    day_exercise_ids = {
        substitution_map.get(be.id, be.exercise_id)
        for be in day_exercises
        if be.id != block_exercise.id
    } - {None}

    # Pin: bookmarks a specific (slot, exercise) pair -- not just the slot --
    # as the "home" to return to after roaming (recycle, prev/next,
    # auto-advance after logging). Encoded as "{block_exercise_id}:
    # {exercise_id}" precisely so that recycling through several candidates
    # in the SAME slot doesn't leave the toggle lit for every candidate that
    # passes through it afterwards -- only the one actually pinned. Unless
    # the user has explicitly pinned something, the slot's own routine
    # exercise IS the pin target, so the single "go back" button built from
    # this (see revert_url below) doubles as both "undo my recycling"
    # (nothing pinned) and "take me to what I pinned" (something pinned) --
    # deliberately one button, not two, since they're the same action once
    # the default target is the original exercise. A stale/foreign/
    # malformed pin value is silently dropped instead of erroring.
    #
    # Also persisted onto the Workout row (not just carried in the URL) --
    # otherwise any fresh navigation that doesn't happen to echo `pin`
    # back (a tapped rest-timer push notification chief among them) reset
    # it, which looked like the pin "randomly disappearing". `unpin` is a
    # separate explicit flag rather than just omitting `pin`, precisely so
    # that omission (arriving fresh, with no opinion either way) can fall
    # back to whatever's stored instead of being indistinguishable from
    # "the user just unpinned this".
    if unpin and todays_workout is not None and todays_workout.pinned_block_exercise_id is not None:
        todays_workout.pinned_block_exercise_id = None
        todays_workout.pinned_exercise_id = None
        db.commit()
    elif (
        pin is None
        and not unpin
        and todays_workout is not None
        and todays_workout.pinned_block_exercise_id is not None
    ):
        pin = f"{todays_workout.pinned_block_exercise_id}:{todays_workout.pinned_exercise_id}"

    pinned_block_exercise = None
    pin_exercise_id = None
    if pin is not None:
        pin_be_id = None
        try:
            pin_be_id_str, pin_ex_id_str = pin.split(":", 1)
            pin_be_id, pin_exercise_id = int(pin_be_id_str), int(pin_ex_id_str)
        except (ValueError, AttributeError):
            pin_be_id = None
        if pin_be_id is not None:
            for candidate in day_exercises:
                if candidate.id == pin_be_id:
                    pinned_block_exercise = candidate
                    break

    if (
        todays_workout is not None
        and (pinned_block_exercise.id if pinned_block_exercise is not None else None)
        != todays_workout.pinned_block_exercise_id
    ):
        todays_workout.pinned_block_exercise_id = (
            pinned_block_exercise.id if pinned_block_exercise is not None else None
        )
        todays_workout.pinned_exercise_id = pin_exercise_id if pinned_block_exercise is not None else None
        db.commit()

    if pinned_block_exercise is not None:
        effective_pin = f"{pinned_block_exercise.id}:{pin_exercise_id}"
        pin_target_block_exercise = pinned_block_exercise
        pin_target_exercise_id = pin_exercise_id
    else:
        effective_pin = None
        pin_target_block_exercise = block_exercise
        pin_target_exercise_id = block_exercise.exercise_id

    pin_active = (
        pin_target_block_exercise.id == block_exercise.id
        and pin_target_exercise_id == exercise_id
    )

    pin_toggle_params = {"block_exercise_id": block_exercise_id}
    if next is not None:
        pin_toggle_params["next"] = next
    if not pin_active:
        pin_toggle_params["pin"] = f"{block_exercise_id}:{exercise_id}"
    else:
        # Explicit, not just an absent `pin` -- see the write-through note
        # above for why the two can't be treated the same.
        pin_toggle_params["unpin"] = "1"
    if session_date is not None:
        pin_toggle_params["session_date"] = session_date.isoformat()
    if preview:
        pin_toggle_params["preview"] = "1"
    pin_toggle_url = training_url(block_exercise_id, exercise_id, pin_toggle_params)

    recycle_url = None
    recycle_back_url = None
    revert_url = None
    user_rating = None
    user_banned = False
    similar_exercises = []
    if exercise_id is not None:
        next_similar = get_next_similar_exercise(db, user.id, exercise_id, exclude_ids=day_exercise_ids)
        recycle_url = build_recycle_url(next_similar.id) if next_similar is not None else None
        prev_similar = get_previous_similar_exercise(db, user.id, exercise_id, exclude_ids=day_exercise_ids)
        recycle_back_url = build_recycle_url(prev_similar.id) if prev_similar is not None else None
        if not pin_active and pin_target_exercise_id is not None:
            if pin_target_block_exercise.id == block_exercise.id:
                revert_url = build_recycle_url(pin_target_exercise_id)
            else:
                revert_nav_params = {"block_exercise_id": pin_target_block_exercise.id, "substitute": "1"}
                if next is not None:
                    revert_nav_params["next"] = next
                if effective_pin is not None:
                    revert_nav_params["pin"] = effective_pin
                if session_date is not None:
                    revert_nav_params["session_date"] = session_date.isoformat()
                if preview:
                    revert_nav_params["preview"] = "1"
                revert_url = training_url(
                    pin_target_block_exercise.id, pin_target_exercise_id, revert_nav_params
                )
        user_rating = get_user_rating(db, user.id, exercise_id)
        user_banned = get_user_ban(db, user.id, exercise_id)
        similar_exercises = get_similar_exercises(db, user.id, exercise_id)

    superset_partner = None
    if block_exercise.is_superset_with_next:
        superset_partner = (
            db.query(BlockExercise)
            .filter(
                BlockExercise.block_id == block_exercise.block_id,
                BlockExercise.position == block_exercise.position + 1,
            )
            .first()
        )
    else:
        prev_in_block = (
            db.query(BlockExercise)
            .filter(
                BlockExercise.block_id == block_exercise.block_id,
                BlockExercise.position == block_exercise.position - 1,
            )
            .first()
        )
        if prev_in_block is not None and prev_in_block.is_superset_with_next:
            superset_partner = prev_in_block

    superset_partner_exercise = None
    partner_sets_completed_today = 0
    if superset_partner is not None:
        partner_exercise_id = substitution_map.get(superset_partner.id, superset_partner.exercise_id)
        superset_partner_exercise = (
            db.get(Exercise, partner_exercise_id) if partner_exercise_id is not None else None
        )
        if todays_workout is not None:
            partner_sets_completed_today = count_sets(
                db, todays_workout.id, partner_exercise_id, superset_partner.id
            )

    weight_target = resolve_weight_target(db, user.id, exercise_id, block_exercise)

    training = {
        "modo_registro": block_exercise.modo_registro,
        "reps_min": block_exercise.reps_min,
        "reps_max": block_exercise.reps_max,
        "duracion_segundos": block_exercise.duracion_segundos,
        "weight_target": weight_target,
        "rest_seconds": block.rest_seconds,
        "no_rest": block_exercise.is_superset_with_next,
        "sets_completed": sets_completed_today,
        "sets_target": block.num_sets,
        "is_warmup": block.type == "Calentamiento",
        "program_id": day_template.program_id,
        "is_superset": superset_partner is not None,
        "superset_is_first": block_exercise.is_superset_with_next,
        "superset_partner_gif_url": superset_partner_exercise.gif_url if superset_partner_exercise else None,
        "superset_partner_name": (
            superset_partner_exercise.name
            if superset_partner_exercise
            else (superset_partner.pending_name if superset_partner else None)
        ),
        "superset_partner_sets_completed": partner_sets_completed_today,
        "superset_partner_url": build_nav_url(superset_partner) if superset_partner is not None else None,
        "recycle_url": recycle_url,
        "recycle_back_url": recycle_back_url,
        "revert_url": revert_url,
        "pin_active": pin_active,
        "pin_toggle_url": pin_toggle_url,
    }

    index = None
    for i, day_exercise in enumerate(day_exercises):
        if day_exercise.id == block_exercise.id:
            index = i

    prev_url = None
    next_exercise_url = None

    notify_text, target_be, prompt_finish = resolve_rest_step(
        db,
        block_exercise,
        block,
        day_exercises,
        todays_workout.id if todays_workout is not None else None,
        sets_completed_today,
    )
    training["rest_notify_text"] = notify_text
    training["auto_advance_url"] = build_nav_url(target_be) if target_be is not None else None
    training["prompt_finish"] = prompt_finish

    # Gated by `logged`, same reasoning as resolve_rest_step: only ask right
    # after the log action that actually completed today's sets, not on
    # every subsequent page view of an already-finished exercise.
    ask_weight_progress, suggested_weight = (
        resolve_weight_progress_prompt(
            db, user.id, exercise_id, block_exercise, block, todays_workout, sets_completed_today
        )
        if logged
        else (False, None)
    )
    training["ask_weight_progress"] = ask_weight_progress
    training["suggested_weight"] = suggested_weight

    if index is not None:
        if index > 0:
            prev_url = build_nav_url(day_exercises[index - 1])
        if index < len(day_exercises) - 1:
            next_exercise_url = build_nav_url(day_exercises[index + 1])

    self_params = {"block_exercise_id": block_exercise_id}
    if next is not None:
        self_params["next"] = next
    if effective_pin is not None:
        self_params["pin"] = effective_pin
    if session_date is not None:
        self_params["session_date"] = session_date.isoformat()
    if preview:
        self_params["preview"] = "1"
    self_url = training_url(block_exercise_id, exercise_id, self_params)

    history = build_exercise_history(db, user.id, exercise_id, block_exercise_id)

    # `next` is whatever the client happened to echo back -- fragile by
    # nature (a stale bookmark, a notification the OS opened at its own
    # idea of the URL, any link built before this exercise's slot
    # existed). Unlike the catálogo-only branch below, here we always know
    # which day this exercise belongs to, so the "<<" button never needs
    # to fall back to the generic /exercises list: it can always derive
    # today's (or the browsed day's/previewed day's) own list instead.
    if preview:
        fallback_back_url = f"/days/{day_template.id}/preview"
    elif session_date is not None:
        fallback_back_url = f"/programs/{day_template.program_id}/sessions/{session_date.isoformat()}/detail"
    else:
        fallback_back_url = f"/programs/{day_template.program_id}/today"

    now = datetime.now()
    context = {
        "exercise": exercise,
        "pending_name": block_exercise.pending_name,
        "self_url": self_url,
        "today": now.date().isoformat(),
        "now_time": now.time().isoformat(timespec="minutes"),
        "training": training,
        "next": next,
        "back_url": next or fallback_back_url,
        "pin": effective_pin,
        "session_date": session_date.isoformat() if session_date is not None else None,
        "preview": preview,
        "day_template": day_template,
        "block_exercise_id": block_exercise_id,
        "prev_url": prev_url,
        "next_exercise_url": next_exercise_url,
        "logged": logged,
        "user_rating": user_rating,
        "user_banned": user_banned,
        "similar_exercises": similar_exercises,
    }
    context.update(history)
    return templates.TemplateResponse(request=request, name="exercises/log.html", context=context)


@router.get("/exercises/{exercise_id}/log")
async def log_exercise_form(
    exercise_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    block_exercise_id: int | None = None,
    next: str | None = None,
    logged: bool = False,
    substitute: bool = False,
    pin: str | None = None,
    session_date: date_type | None = None,
    unpin: bool = False,
    preview: bool = False,
):
    next = safe_next(next)
    if block_exercise_id is None:
        block_exercise_id = find_active_block_exercise(db, user, exercise_id, session_date)

    if block_exercise_id is None:
        # Ficha de catálogo, fuera de una jornada de entrenamiento.
        exercise = db.get(Exercise, exercise_id)
        history = build_exercise_history(db, user.id, exercise_id, None)
        self_params = {}
        if next is not None:
            self_params["next"] = next
        self_url = f"/exercises/{exercise_id}/log"
        if self_params:
            self_url += f"?{urlencode(self_params)}"
        now = datetime.now()
        context = {
            "exercise": exercise,
            "pending_name": None,
            "self_url": self_url,
            "today": now.date().isoformat(),
            "now_time": now.time().isoformat(timespec="minutes"),
            "training": None,
            "next": next,
            "block_exercise_id": None,
            "prev_url": None,
            "next_exercise_url": None,
            "logged": logged,
            "user_rating": get_user_rating(db, user.id, exercise_id),
            "user_banned": get_user_ban(db, user.id, exercise_id),
            "similar_exercises": get_similar_exercises(db, user.id, exercise_id),
        }
        context.update(history)
        return templates.TemplateResponse(request=request, name="exercises/log.html", context=context)

    return await render_training_log(
        request, db, user, exercise_id, block_exercise_id, next, logged, substitute, pin, session_date, unpin, preview
    )


@router.get("/block-exercises/{block_exercise_id}/log")
async def log_block_exercise_form(
    block_exercise_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    next: str | None = None,
    logged: bool = False,
    pin: str | None = None,
    session_date: date_type | None = None,
    unpin: bool = False,
    preview: bool = False,
):
    next = safe_next(next)
    return await render_training_log(
        request, db, user, None, block_exercise_id, next, logged, False, pin, session_date, unpin, preview
    )


def submit_workout_set(
    db: Session,
    user: User,
    exercise_id: int | None,
    block_exercise_id: int | None,
    weight: str,
    reps: int | None,
    duration_seconds: int | None,
    workout_date: date_type | None,
    set_time: time_type | None,
    comment: str | None,
) -> tuple[Workout, WorkoutSet, BlockExercise | None, bool, int]:
    """Returns (workout, workout_set, target_be, prompt_finish,
    sets_completed_today) -- target_be/prompt_finish/sets_completed_today
    are always resolved (needed for the optimistic-UI JSON response: what
    to auto-advance to, whether the day is done, and the sets-ring), even
    though only some of that also gets written onto `workout.rest_*` as a
    side effect, exactly like before this was exposed."""
    if reps is None and duration_seconds is None:
        raise HTTPException(status_code=400, detail="Indica repeticiones o duración.")

    now = datetime.now()
    workout = get_or_create_workout(db, user.id, workout_date or now.date())

    pending_name_snapshot = None
    is_superset = False
    block_exercise = None
    block = None
    if block_exercise_id is not None:
        block_exercise = db.get(BlockExercise, block_exercise_id)
        if block_exercise is not None and exercise_id is None:
            pending_name_snapshot = block_exercise.pending_name
        if block_exercise is not None:
            block = db.get(Block, block_exercise.block_id)
            is_superset = block_exercise.is_superset_with_next or (
                db.query(BlockExercise)
                .filter(
                    BlockExercise.block_id == block_exercise.block_id,
                    BlockExercise.position == block_exercise.position - 1,
                    BlockExercise.is_superset_with_next.is_(True),
                )
                .first()
                is not None
            )

    if block is not None:
        if workout.day_template_id is not None and block.day_template_id != workout.day_template_id:
            if workout.started_at is not None:
                # That date's Workout already really started under a
                # different day -- logging here too would silently mix this
                # exercise's set into that other session.
                raise HTTPException(
                    status_code=409,
                    detail="Ya hay otra sesión registrada ese día. Termínala antes de entrenar esta.",
                )
            # An uncommitted pick (see /today/choose-session) for a
            # different day -- nothing was ever really started under it, so
            # this exercise's own day is free to take over the slot.
            workout.day_template_id = None

        if workout.day_template_id is None:
            # Logging the very first set of the day is one of the two
            # things that actually starts it (the other is the warmup
            # timer, see mark_today_started) -- lazily associates the
            # Workout with its day and promotes whatever was prepared on
            # the /preview screen.
            day_template = db.get(DayTemplate, block.day_template_id)
            workout.day_template_id = block.day_template_id
            if day_template is not None:
                workout.program_id = day_template.program_id
                owning_program = db.get(Program, day_template.program_id)
                workout.is_manual_session = (
                    owning_program is None
                    or day_template.day_number != owning_program.current_day_number
                )
            promote_day_template_substitutions_to_workout(db, block.day_template_id, workout.id)

    if workout.started_at is None:
        workout.started_at = now
    set_time = set_time or now.time().replace(microsecond=0)
    touch_workout_activity(workout)

    next_order = (
        db.query(WorkoutSet).filter(WorkoutSet.workout_id == workout.id).count() + 1
    )

    workout_set = WorkoutSet(
        workout_id=workout.id,
        exercise_id=exercise_id,
        block_exercise_id=block_exercise_id if exercise_id is None else None,
        pending_name=pending_name_snapshot,
        is_superset=is_superset,
        weight=parse_optional_weight(weight),
        reps=reps,
        duration_seconds=duration_seconds,
        time=set_time,
        comment=comment or None,
        order=next_order,
    )
    db.add(workout_set)
    db.flush()

    target_be = None
    prompt_finish = False
    sets_completed_today = 0
    if block_exercise is not None:
        day_exercises = (
            db.query(BlockExercise)
            .join(Block, BlockExercise.block_id == Block.id)
            .filter(Block.day_template_id == block.day_template_id)
            .order_by(Block.position, BlockExercise.position)
            .all()
        )
        sets_completed_today = count_sets(db, workout.id, exercise_id, block_exercise_id)
        notify_text, target_be, prompt_finish = resolve_rest_step(
            db, block_exercise, block, day_exercises, workout.id, sets_completed_today
        )

        if block_exercise.modo_registro == "tiempo":
            workout.rest_until = None
            workout.rest_total_seconds = None
            workout.rest_notify_text = None
            workout.rest_push_sent_at = None
            workout.active_block_exercise_id = None
        elif not block_exercise.is_superset_with_next:
            workout.rest_until = now + timedelta(seconds=block.rest_seconds)
            workout.rest_total_seconds = block.rest_seconds
            workout.rest_notify_text = notify_text
            workout.rest_push_sent_at = None
            workout.active_block_exercise_id = target_be.id if target_be is not None else block_exercise_id

    db.commit()
    return workout, workout_set, target_be, prompt_finish, sets_completed_today


def build_optimistic_log_response(
    db: Session,
    user: User,
    exercise_id: int | None,
    block_exercise_id: int,
    next: str | None,
    workout: Workout,
    workout_set: WorkoutSet,
    target_be: BlockExercise | None,
    prompt_finish: bool,
    sets_completed_today: int,
    pin: str | None = None,
    session_date: date_type | None = None,
) -> dict:
    """The JSON payload the optimistic-UI fetch() needs to update the whole
    training screen (row, ring, rest timer, next-step prompts) without a
    page reload -- everything a full page render would otherwise have
    recomputed from scratch after the redirect."""
    block_exercise = db.get(BlockExercise, block_exercise_id)
    block = db.get(Block, block_exercise.block_id) if block_exercise is not None else None

    is_first_set_of_day = sets_completed_today == 1
    day_header = format_day_header(date_type.today()) if is_first_set_of_day else None

    self_params = {"block_exercise_id": block_exercise_id}
    if next is not None:
        self_params["next"] = next
    self_url = training_url(block_exercise_id, exercise_id, self_params)

    row_template = templates.get_template("exercises/_history_row.html")
    row_html = row_template.module.history_row(sets_completed_today, workout_set, self_url)

    # The chart/progress section can't be patched incrementally (a new
    # point can flip has_progress from False to True, or shift the whole
    # scale) -- re-render it wholesale with the set that was just
    # committed, so it shows up immediately instead of only after leaving
    # and re-entering the exercise.
    history = build_exercise_history(db, user.id, exercise_id, block_exercise_id)
    progress_html = templates.get_template("exercises/_progress_section.html").render(**history)

    auto_advance_url = None
    if target_be is not None:
        substitution_map = get_substitution_map(db, workout.id)
        target_exercise_id = substitution_map.get(target_be.id, target_be.exercise_id)
        nav_params = {"block_exercise_id": target_be.id}
        if next is not None:
            nav_params["next"] = next
        if pin is not None:
            nav_params["pin"] = pin
        if session_date is not None:
            nav_params["session_date"] = session_date.isoformat()
        auto_advance_url = training_url(target_be.id, target_exercise_id, nav_params)

    ask_weight_progress, suggested_weight = (
        resolve_weight_progress_prompt(
            db, user.id, exercise_id, block_exercise, block, workout, sets_completed_today
        )
        if block_exercise is not None and block is not None
        else (False, None)
    )

    weight_target = (
        resolve_weight_target(db, user.id, exercise_id, block_exercise)
        if block_exercise is not None
        else None
    )

    return {
        "row_html": row_html,
        "progress_html": progress_html,
        "is_first_set_of_day": is_first_set_of_day,
        "day_header": day_header,
        "sets_completed": sets_completed_today,
        "sets_target": block.num_sets if block is not None else None,
        "rest_until": workout.rest_until.isoformat() if workout.rest_until is not None else None,
        "rest_total_seconds": workout.rest_total_seconds,
        "rest_notify_text": workout.rest_notify_text,
        "ask_weight_progress": ask_weight_progress,
        "suggested_weight": suggested_weight,
        "auto_advance_url": auto_advance_url,
        "prompt_finish": prompt_finish,
        "weight_target": weight_target,
    }


@router.post("/exercises/{exercise_id}/log")
async def log_exercise_submit(
    exercise_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    weight: str = Form(""),
    reps: int | None = Form(None),
    duration_seconds: int | None = Form(None),
    workout_date: date_type | None = Form(None, alias="date"),
    set_time: time_type | None = Form(None, alias="time"),
    comment: str | None = Form(None),
    block_exercise_id: int | None = Form(None),
    next: str | None = Form(None),
    pin: str | None = Form(None),
    session_date: date_type | None = Form(None),
):
    next = safe_next(next)
    workout, workout_set, target_be, prompt_finish, sets_completed_today = submit_workout_set(
        db, user, exercise_id, block_exercise_id, weight, reps, duration_seconds, workout_date, set_time, comment
    )

    if block_exercise_id is not None and wants_json(request):
        return JSONResponse(
            build_optimistic_log_response(
                db, user, exercise_id, block_exercise_id, next,
                workout, workout_set, target_be, prompt_finish, sets_completed_today, pin, session_date,
            )
        )

    redirect_url = f"/exercises/{exercise_id}/log"
    params = {"logged": "1"}
    if block_exercise_id is not None:
        params["block_exercise_id"] = block_exercise_id
    if next is not None:
        params["next"] = next
    if pin is not None:
        params["pin"] = pin
    if session_date is not None:
        params["session_date"] = session_date.isoformat()
    redirect_url += f"?{urlencode(params)}"

    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/block-exercises/{block_exercise_id}/log")
async def log_block_exercise_submit(
    block_exercise_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    weight: str = Form(""),
    reps: int | None = Form(None),
    duration_seconds: int | None = Form(None),
    workout_date: date_type | None = Form(None, alias="date"),
    set_time: time_type | None = Form(None, alias="time"),
    comment: str | None = Form(None),
    next: str | None = Form(None),
    pin: str | None = Form(None),
    session_date: date_type | None = Form(None),
):
    next = safe_next(next)
    workout, workout_set, target_be, prompt_finish, sets_completed_today = submit_workout_set(
        db, user, None, block_exercise_id, weight, reps, duration_seconds, workout_date, set_time, comment
    )

    if wants_json(request):
        return JSONResponse(
            build_optimistic_log_response(
                db, user, None, block_exercise_id, next,
                workout, workout_set, target_be, prompt_finish, sets_completed_today, pin, session_date,
            )
        )

    redirect_url = f"/block-exercises/{block_exercise_id}/log"
    params = {"logged": "1"}
    if next is not None:
        params["next"] = next
    if pin is not None:
        params["pin"] = pin
    if session_date is not None:
        params["session_date"] = session_date.isoformat()
    redirect_url += f"?{urlencode(params)}"

    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/exercises/{exercise_id}/set-target-weight")
async def set_target_weight(
    exercise_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    weight: float = Form(...),
    block_exercise_id: int | None = Form(None),
    next: str | None = Form(None),
    pin: str | None = Form(None),
    session_date: date_type | None = Form(None),
):
    next = safe_next(next)
    existing = (
        db.query(ExerciseUserProgress)
        .filter(
            ExerciseUserProgress.user_id == user.id,
            ExerciseUserProgress.exercise_id == exercise_id,
        )
        .first()
    )
    if existing is None:
        db.add(ExerciseUserProgress(user_id=user.id, exercise_id=exercise_id, current_weight=weight))
    else:
        existing.current_weight = weight
    db.commit()

    redirect_params = {"logged": "1"}
    if block_exercise_id is not None:
        redirect_params["block_exercise_id"] = block_exercise_id
    if next is not None:
        redirect_params["next"] = next
    if pin is not None:
        redirect_params["pin"] = pin
    if session_date is not None:
        redirect_params["session_date"] = session_date.isoformat()
    return RedirectResponse(
        url=training_url(block_exercise_id, exercise_id, redirect_params), status_code=303
    )


@router.get("/workout-sets/{set_id}/edit")
async def edit_workout_set_form(
    set_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    next: str | None = None,
):
    next = safe_next(next) or "/history"
    workout_set = get_own_workout_set(db, set_id, user.id)
    workout = db.get(Workout, workout_set.workout_id)
    exercise = db.get(Exercise, workout_set.exercise_id) if workout_set.exercise_id is not None else None
    block_exercise = (
        db.get(BlockExercise, workout_set.block_exercise_id)
        if workout_set.block_exercise_id is not None
        else None
    )

    if exercise is not None:
        default_next = f"/exercises/{exercise.id}/log"
    elif block_exercise is not None:
        default_next = f"/block-exercises/{block_exercise.id}/log"
    else:
        # The program/block-exercise this was logged against no longer exists
        # (e.g. the program was deleted) -- fall back to the global history.
        default_next = "/history"

    return templates.TemplateResponse(
        request=request,
        name="exercises/edit_set.html",
        context={
            "exercise": exercise,
            "pending_name": block_exercise.pending_name if block_exercise else workout_set.pending_name,
            "workout_set": workout_set,
            "date": workout.date.isoformat(),
            "next": next or default_next,
        },
    )


@router.post("/workout-sets/{set_id}/edit")
async def edit_workout_set_submit(
    set_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    weight: str = Form(""),
    reps: int | None = Form(None),
    duration_seconds: int | None = Form(None),
    workout_date: date_type = Form(..., alias="date"),
    set_time: time_type = Form(..., alias="time"),
    comment: str | None = Form(None),
    next: str = Form(...),
):
    next = safe_next(next) or "/history"
    if reps is None and duration_seconds is None:
        raise HTTPException(status_code=400, detail="Indica repeticiones o duración.")

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
    workout_set.duration_seconds = duration_seconds
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
    next = safe_next(next) or "/history"
    workout_set = get_own_workout_set(db, set_id, user.id)
    workout_id = workout_set.workout_id

    db.delete(workout_set)
    db.flush()

    delete_workout_if_empty(db, workout_id)

    db.commit()

    return RedirectResponse(url=next, status_code=303)
