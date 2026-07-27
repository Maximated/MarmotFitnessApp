import unicodedata

from rapidfuzz import fuzz, process
from sqlalchemy.orm import Session

from app.models import Exercise, ExerciseAlias, ExerciseRating

FUZZY_THRESHOLD = 90


def normalize_name(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.lower().split())


class ExerciseMatcher:
    def __init__(self, db: Session, user_id: int):
        banned_ids = {
            row[0]
            for row in db.query(ExerciseRating.exercise_id)
            .filter(ExerciseRating.user_id == user_id, ExerciseRating.banned.is_(True))
            .all()
        }
        self.banned_ids = banned_ids
        self.alias_map: dict[str, int] = {
            alias.normalized_name: alias.exercise_id
            for alias in db.query(ExerciseAlias).all()
            if alias.exercise_id not in banned_ids
        }
        self.normalized_index: dict[str, int] = {
            normalize_name(name): exercise_id
            for exercise_id, name in db.query(Exercise.id, Exercise.name).all()
            if exercise_id not in banned_ids
        }
        self.db = db

    def resolve(
        self, id_dataset: str | int | None, nombre: str
    ) -> tuple[int | None, str, float | None]:
        if id_dataset:
            normalized_id = str(id_dataset).strip().zfill(4)
            exercise = (
                self.db.query(Exercise).filter(Exercise.external_id == normalized_id).first()
            )
            if exercise is not None and exercise.id not in self.banned_ids:
                return exercise.id, "id", None

        normalized = normalize_name(nombre)

        alias_exercise_id = self.alias_map.get(normalized)
        if alias_exercise_id is not None:
            return alias_exercise_id, "alias", None

        exact_exercise_id = self.normalized_index.get(normalized)
        if exact_exercise_id is not None:
            return exact_exercise_id, "name", None

        if self.normalized_index:
            best = process.extractOne(
                normalized, self.normalized_index.keys(), scorer=fuzz.WRatio
            )
            if best is not None:
                candidate_name, score, _ = best
                if score >= FUZZY_THRESHOLD:
                    return self.normalized_index[candidate_name], "fuzzy", score

        return None, "pending", None

    def best_suggestion(self, nombre: str) -> tuple[int | None, str | None, float | None]:
        """Best-effort candidate for a pending name, regardless of threshold — used to
        pre-fill the manual resolution screen. Not persisted."""
        if not self.normalized_index:
            return None, None, None
        normalized = normalize_name(nombre)
        best = process.extractOne(normalized, self.normalized_index.keys(), scorer=fuzz.WRatio)
        if best is None:
            return None, None, None
        candidate_name, score, _ = best
        return self.normalized_index[candidate_name], candidate_name, score
