from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import and_, case
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_user
from app.models import Exercise, ExerciseRating, User

router = APIRouter()

UNRATED_PRIORITY = 3


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

    return (
        db.query(Exercise)
        .outerjoin(
            ExerciseRating,
            and_(
                ExerciseRating.exercise_id == Exercise.id,
                ExerciseRating.user_id == user_id,
            ),
        )
        .filter(Exercise.target_muscle == exercise.target_muscle, Exercise.id != exercise_id)
        .order_by(rating_order_case(), Exercise.name)
        .limit(limit)
        .all()
    )


@router.post("/exercises/{exercise_id}/rate")
async def rate_exercise(
    exercise_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    rating: int = Form(...),
    next: str | None = Form(None),
):
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

    return RedirectResponse(url=next or f"/exercises/{exercise_id}/log", status_code=303)
