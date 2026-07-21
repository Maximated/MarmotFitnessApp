"""Importa data/exercises.json de un clon del dataset a la tabla `exercises`.

Uso:
    uv run python scripts/import_exercises.py --source data/exercises-dataset-src
"""
import argparse
import json
import shutil
from pathlib import Path

from app.database import SessionLocal
from app.models import Exercise

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MEDIA_DIR = PROJECT_ROOT / "media" / "exercises"
TRANSLATIONS_PATH = PROJECT_ROOT / "data" / "translations_es.json"


def load_translations() -> dict:
    if not TRANSLATIONS_PATH.exists():
        return {"category": {}, "equipment": {}, "target_muscle": {}, "name": {}}
    return json.loads(TRANSLATIONS_PATH.read_text())


def main(source: Path) -> None:
    exercises = json.loads((source / "data" / "exercises.json").read_text())
    translations = load_translations()

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    created = 0
    updated = 0

    with SessionLocal() as db:
        for item in exercises:
            gif_filename = Path(item["gif_url"]).name
            src_gif = source / "videos" / gif_filename
            dst_gif = MEDIA_DIR / gif_filename
            if not dst_gif.exists():
                shutil.copyfile(src_gif, dst_gif)

            values = {
                "name": translations["name"].get(item["id"], item["name"]),
                "category": translations["category"].get(
                    item["category"], item["category"]
                ),
                "target_muscle": translations["target_muscle"].get(
                    item["target"], item["target"]
                ),
                "equipment": translations["equipment"].get(
                    item["equipment"], item["equipment"]
                ),
                "gif_url": f"/media/exercises/{gif_filename}",
                "instructions": item["instructions"]["es"],
            }

            exercise = (
                db.query(Exercise)
                .filter(Exercise.external_id == item["id"])
                .one_or_none()
            )
            if exercise is None:
                db.add(Exercise(external_id=item["id"], **values))
                created += 1
            else:
                for field, value in values.items():
                    setattr(exercise, field, value)
                updated += 1

        db.commit()

    print(f"Creados: {created}, actualizados: {updated}, total: {len(exercises)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    args = parser.parse_args()
    main(args.source)
