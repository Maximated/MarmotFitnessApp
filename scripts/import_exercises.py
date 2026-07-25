"""Importa data/exercises.json (versionado en el repo) a la tabla `exercises`.

Uso:
    uv run python scripts/import_exercises.py --source data/exercises-dataset-src

`--source` apunta al clon del dataset original (no versionado, solo local)
del que se copian los .gif; `data/exercises.json` y `data/translations_es.json`
sí están versionados porque son necesarios para poblar la tabla en cualquier
entorno, incluido un servidor donde ese clon no existe.

Este script solo copia los .gif originales. `gif_url` apunta al .webp
correspondiente en media/exercises/webp/, así que tras importar hace falta
ejecutar además media/exercises/proc_gif.py para generar esos .webp con
transparencia a partir de los .gif recién copiados.
"""
import argparse
import shutil
from pathlib import Path

from app.database import SessionLocal
from app.models import Exercise
from scripts.exercise_data import build_exercise_values, load_exercises_dataset, load_translations

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MEDIA_DIR = PROJECT_ROOT / "media" / "exercises"


def main(source: Path) -> None:
    exercises = load_exercises_dataset()
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

            values = build_exercise_values(item, translations)

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
