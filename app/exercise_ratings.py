from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import and_, case, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_user
from app.http_utils import safe_next, wants_json
from app.models import Exercise, ExerciseRating, User

router = APIRouter()

UNRATED_PRIORITY = 3

# dorsales/espalda alta are separate target_muscle values in the catalog,
# but the two are naturally lopsided (dorsales skews pulldowns/pull-ups,
# espalda alta skews rows) -- for "ejercicios similares" they're treated as
# one combined pool, with `variante` (vertical/horizontal) doing the actual
# distinguishing.
BACK_MUSCLE_GROUP = {"dorsales", "espalda alta"}


def muscle_pool(target_muscle: str) -> tuple[str, ...]:
    if target_muscle in BACK_MUSCLE_GROUP:
        return tuple(BACK_MUSCLE_GROUP)
    return (target_muscle,)


def rating_order_case():
    """Order by best-rated-first, with unrated exercises placed right after
    3-star ones (not hidden, not forced to the very end)."""
    return case(
        (ExerciseRating.rating == 5, 0),
        (ExerciseRating.rating == 4, 1),
        (ExerciseRating.rating == 3, 2),
        (ExerciseRating.rating == 2, 4),
        (ExerciseRating.rating == 1, 5),
        else_=UNRATED_PRIORITY,
    )


def get_user_rating(db: Session, user_id: int, exercise_id: int) -> int | None:
    rating = (
        db.query(ExerciseRating)
        .filter(ExerciseRating.user_id == user_id, ExerciseRating.exercise_id == exercise_id)
        .first()
    )
    return rating.rating if rating else None


def get_user_ban(db: Session, user_id: int, exercise_id: int) -> bool:
    rating = (
        db.query(ExerciseRating)
        .filter(ExerciseRating.user_id == user_id, ExerciseRating.exercise_id == exercise_id)
        .first()
    )
    return bool(rating.banned) if rating else False


def get_user_ratings_map(db: Session, user_id: int, exercise_ids: list[int]) -> dict[int, int]:
    if not exercise_ids:
        return {}
    rows = (
        db.query(ExerciseRating.exercise_id, ExerciseRating.rating)
        .filter(ExerciseRating.user_id == user_id, ExerciseRating.exercise_id.in_(exercise_ids))
        .all()
    )
    return dict(rows)


def get_similar_exercises(db: Session, user_id: int, exercise_id: int, limit: int = 8):
    exercise = db.get(Exercise, exercise_id)
    if exercise is None:
        return []

    query = (
        db.query(Exercise)
        .outerjoin(
            ExerciseRating,
            and_(
                ExerciseRating.exercise_id == Exercise.id,
                ExerciseRating.user_id == user_id,
            ),
        )
        .filter(
            Exercise.target_muscle.in_(muscle_pool(exercise.target_muscle)),
            Exercise.id != exercise_id,
            ExerciseRating.banned.isnot(True),
        )
    )
    if exercise.variante is not None:
        query = query.filter(Exercise.variante == exercise.variante)
    return query.order_by(rating_order_case(), Exercise.name).limit(limit).all()


def _ranked_similar(db: Session, user_id: int, exercise: Exercise):
    # The current exercise always stays in its own pool (even if the user
    # banned it) so get_next_similar_exercise/get_previous_similar_exercise
    # can still find its position to cycle from -- only OTHER banned
    # exercises are excluded as candidates.
    query = (
        db.query(Exercise)
        .outerjoin(
            ExerciseRating,
            and_(
                ExerciseRating.exercise_id == Exercise.id,
                ExerciseRating.user_id == user_id,
            ),
        )
        .filter(
            Exercise.target_muscle.in_(muscle_pool(exercise.target_muscle)),
            or_(Exercise.id == exercise.id, ExerciseRating.banned.isnot(True)),
        )
    )
    if exercise.variante is not None:
        query = query.filter(Exercise.variante == exercise.variante)
    return query.order_by(rating_order_case(), Exercise.name).all()


def get_next_similar_exercise(db: Session, user_id: int, exercise_id: int) -> Exercise | None:
    """Cycle to the next exercise in the same similar-exercises group, ranked
    by the user's rating (best first). The group forms a loop: cycling past
    the last one wraps back to the exercise the user started from."""
    exercise = db.get(Exercise, exercise_id)
    if exercise is None:
        return None

    ranked = _ranked_similar(db, user_id, exercise)
    if len(ranked) <= 1:
        return None

    ids = [e.id for e in ranked]
    current_index = ids.index(exercise_id)
    return ranked[(current_index + 1) % len(ranked)]


def get_previous_similar_exercise(db: Session, user_id: int, exercise_id: int) -> Exercise | None:
    """Cycle to the previous exercise in the same ranked group -- the mirror
    of get_next_similar_exercise, for a "go back one suggestion" control."""
    exercise = db.get(Exercise, exercise_id)
    if exercise is None:
        return None

    ranked = _ranked_similar(db, user_id, exercise)
    if len(ranked) <= 1:
        return None

    ids = [e.id for e in ranked]
    current_index = ids.index(exercise_id)
    return ranked[(current_index - 1) % len(ranked)]


@router.post("/exercises/{exercise_id}/rate")
async def rate_exercise(
    exercise_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    rating: int = Form(...),
    next: str | None = Form(None),
):
    next = safe_next(next)
    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="La valoración debe estar entre 1 y 5.")

    existing = (
        db.query(ExerciseRating)
        .filter(ExerciseRating.user_id == user.id, ExerciseRating.exercise_id == exercise_id)
        .first()
    )
    if existing is not None:
        existing.rating = rating
        existing.updated_at = datetime.now()
    else:
        db.add(ExerciseRating(user_id=user.id, exercise_id=exercise_id, rating=rating))
    db.commit()

    if wants_json(request):
        return JSONResponse({"rating": rating})
    return RedirectResponse(url=next or f"/exercises/{exercise_id}/log", status_code=303)


@router.post("/exercises/{exercise_id}/ban")
async def ban_exercise(
    exercise_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    banned: bool = Form(...),
    next: str | None = Form(None),
):
    next = safe_next(next)
    existing = (
        db.query(ExerciseRating)
        .filter(ExerciseRating.user_id == user.id, ExerciseRating.exercise_id == exercise_id)
        .first()
    )
    if existing is not None:
        existing.banned = banned
    else:
        db.add(ExerciseRating(user_id=user.id, exercise_id=exercise_id, rating=None, banned=banned))
    db.commit()

    if wants_json(request):
        return JSONResponse({"banned": banned})
    return RedirectResponse(url=next or f"/exercises/{exercise_id}/log", status_code=303)
