from sqlalchemy.orm import Session

from app.models import BlockExercise, Exercise, WorkoutSubstitution


def get_substitution_map(db: Session, workout_id: int | None) -> dict[int, int]:
    """block_exercise_id -> exercise_id, only for slots substituted in this
    specific workout. Absence from the map means "use the block's own
    default exercise"."""
    if workout_id is None:
        return {}
    rows = (
        db.query(WorkoutSubstitution.block_exercise_id, WorkoutSubstitution.exercise_id)
        .filter(WorkoutSubstitution.workout_id == workout_id)
        .all()
    )
    return dict(rows)


def set_substitution(db: Session, workout_id: int, block_exercise_id: int, exercise_id: int) -> None:
    existing = (
        db.query(WorkoutSubstitution)
        .filter(
            WorkoutSubstitution.workout_id == workout_id,
            WorkoutSubstitution.block_exercise_id == block_exercise_id,
        )
        .first()
    )
    if existing is not None:
        existing.exercise_id = exercise_id
    else:
        db.add(
            WorkoutSubstitution(
                workout_id=workout_id,
                block_exercise_id=block_exercise_id,
                exercise_id=exercise_id,
            )
        )


def apply_substitutions(
    db: Session,
    exercises_by_block: dict[int, list[tuple[BlockExercise, Exercise | None]]],
    substitution_map: dict[int, int],
) -> dict[int, list[tuple[BlockExercise, Exercise | None]]]:
    if not substitution_map:
        return exercises_by_block

    substitute_exercise_ids = set(substitution_map.values())
    substitute_exercises = {
        e.id: e for e in db.query(Exercise).filter(Exercise.id.in_(substitute_exercise_ids)).all()
    }

    result = {}
    for block_id, attached in exercises_by_block.items():
        new_attached = []
        for block_exercise, exercise in attached:
            substitute_id = substitution_map.get(block_exercise.id)
            if substitute_id is not None and substitute_id in substitute_exercises:
                exercise = substitute_exercises[substitute_id]
            new_attached.append((block_exercise, exercise))
        result[block_id] = new_attached
    return result
