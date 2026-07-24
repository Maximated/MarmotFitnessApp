from itertools import groupby

from sqlalchemy.orm import Session

from app.charts import polyline_points, scale_points
from app.models import Workout, WorkoutSet

SPANISH_WEEKDAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def format_day_header(d) -> str:
    return f"{SPANISH_WEEKDAYS[d.weekday()]}, {d.day}/{d.month}/{d.year % 100:02d}"


def build_exercise_history(db: Session, user_id: int, exercise_id: int) -> dict:
    sets = (
        db.query(WorkoutSet, Workout)
        .join(Workout, WorkoutSet.workout_id == Workout.id)
        .filter(Workout.user_id == user_id, WorkoutSet.exercise_id == exercise_id)
        .order_by(Workout.date.desc(), WorkoutSet.order.desc())
        .all()
    )

    day_groups = []
    for day_date, rows in groupby(sets, key=lambda row: row[1].date):
        day_sets = list(rows)
        total = len(day_sets)
        numbered = [(total - i, ws) for i, (ws, _) in enumerate(day_sets)]
        day_groups.append({"header": format_day_header(day_date), "sets": numbered})

    chronological = list(reversed(sets))
    weights = [ws.weight for ws, _ in chronological if ws.weight is not None]
    reps = [ws.reps for ws, _ in chronological if ws.reps is not None]
    durations = [ws.duration_seconds for ws, _ in chronological if ws.duration_seconds is not None]

    return {
        "day_groups": day_groups,
        "has_progress": len(chronological) >= 2,
        "has_weight_progress": len(weights) >= 2,
        "weight_points": scale_points(weights),
        "weight_line": polyline_points(scale_points(weights)),
        "weight_min": min(weights) if weights else None,
        "weight_max": max(weights) if weights else None,
        "has_reps_progress": len(reps) >= 2,
        "reps_points": scale_points(reps),
        "reps_line": polyline_points(scale_points(reps)),
        "reps_min": min(reps) if reps else None,
        "reps_max": max(reps) if reps else None,
        "has_duration_progress": len(durations) >= 2,
        "duration_points": scale_points(durations),
        "duration_line": polyline_points(scale_points(durations)),
        "duration_min": min(durations) if durations else None,
        "duration_max": max(durations) if durations else None,
        "progress_from": chronological[0][1].date if chronological else None,
        "progress_to": chronological[-1][1].date if chronological else None,
    }
