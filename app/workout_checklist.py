from sqlalchemy.orm import Session

from app.models import WorkoutChecklistItem


def get_checklist_done_ids(db: Session, workout_id: int | None) -> set[int]:
    """block_exercise_ids marked done for this specific workout."""
    if workout_id is None:
        return set()
    rows = (
        db.query(WorkoutChecklistItem.block_exercise_id)
        .filter(WorkoutChecklistItem.workout_id == workout_id)
        .all()
    )
    return {row[0] for row in rows}


def is_checklist_done(db: Session, workout_id: int, block_exercise_id: int) -> bool:
    return (
        db.query(WorkoutChecklistItem.id)
        .filter(
            WorkoutChecklistItem.workout_id == workout_id,
            WorkoutChecklistItem.block_exercise_id == block_exercise_id,
        )
        .first()
        is not None
    )


def toggle_checklist_item(db: Session, workout_id: int, block_exercise_id: int) -> bool:
    """Flips done/not-done for this workout+block_exercise. Returns the new state."""
    existing = (
        db.query(WorkoutChecklistItem)
        .filter(
            WorkoutChecklistItem.workout_id == workout_id,
            WorkoutChecklistItem.block_exercise_id == block_exercise_id,
        )
        .first()
    )
    if existing is not None:
        db.delete(existing)
        return False
    db.add(WorkoutChecklistItem(workout_id=workout_id, block_exercise_id=block_exercise_id))
    return True
