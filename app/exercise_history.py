from itertools import groupby

from sqlalchemy.orm import Session

from app.charts import polyline_points, scale_points
from app.models import Workout, WorkoutSet

SPANISH_WEEKDAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def format_day_header(d) -> str:
    return f"{SPANISH_WEEKDAYS[d.weekday()]}, {d.day}/{d.month}/{d.year % 100:02d}"


def _short_date(d) -> str | None:
    return f"{d.day}/{d.month}" if d is not None else None


def build_exercise_history(
    db: Session, user_id: int, exercise_id: int | None, block_exercise_id: int | None = None
) -> dict:
    query = (
        db.query(WorkoutSet, Workout)
        .join(Workout, WorkoutSet.workout_id == Workout.id)
        .filter(Workout.user_id == user_id)
    )
    if exercise_id is not None:
        query = query.filter(WorkoutSet.exercise_id == exercise_id)
    else:
        query = query.filter(WorkoutSet.block_exercise_id == block_exercise_id)
    sets = query.order_by(Workout.date.desc(), WorkoutSet.order.desc()).all()

    day_groups = []
    for day_date, rows in groupby(sets, key=lambda row: row[1].date):
        day_sets = list(rows)
        total = len(day_sets)
        numbered = [(total - i, ws) for i, (ws, _) in enumerate(day_sets)]
        day_groups.append({"header": format_day_header(day_date), "sets": numbered})

    chronological = list(reversed(sets))
    weight_rows = [(ws.weight, ws.is_superset) for ws, _ in chronological if ws.weight is not None]
    reps_rows = [(ws.reps, ws.is_superset) for ws, _ in chronological if ws.reps is not None]
    duration_rows = [
        (ws.duration_seconds, ws.is_superset) for ws, _ in chronological if ws.duration_seconds is not None
    ]
    weights = [v for v, _ in weight_rows]
    reps = [v for v, _ in reps_rows]
    durations = [v for v, _ in duration_rows]

    def with_superset_flag(rows, scaled):
        return [(x, y, is_superset) for (x, y), (_, is_superset) in zip(scaled, rows)]

    weight_scaled = scale_points(weights)
    reps_scaled = scale_points(reps)
    duration_scaled = scale_points(durations)

    return {
        "day_groups": day_groups,
        "has_progress": len(chronological) >= 2,
        "has_weight_progress": len(weights) >= 2,
        "weight_points": with_superset_flag(weight_rows, weight_scaled),
        "weight_line": polyline_points(weight_scaled),
        "weight_min": min(weights) if weights else None,
        "weight_max": max(weights) if weights else None,
        "has_reps_progress": len(reps) >= 2,
        "reps_points": with_superset_flag(reps_rows, reps_scaled),
        "reps_line": polyline_points(reps_scaled),
        "reps_min": min(reps) if reps else None,
        "reps_max": max(reps) if reps else None,
        "has_duration_progress": len(durations) >= 2,
        "duration_points": with_superset_flag(duration_rows, duration_scaled),
        "duration_line": polyline_points(duration_scaled),
        "duration_min": min(durations) if durations else None,
        "duration_max": max(durations) if durations else None,
        "progress_from": chronological[0][1].date if chronological else None,
        "progress_to": chronological[-1][1].date if chronological else None,
        "progress_from_short": _short_date(chronological[0][1].date) if chronological else None,
        "progress_to_short": _short_date(chronological[-1][1].date) if chronological else None,
    }
