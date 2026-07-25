"""Bootstrap automático de la tabla `exercises`, ejecutado en cada arranque
del contenedor (ver docker-entrypoint.sh), igual que `alembic upgrade head`.

Idempotente: si la tabla ya tiene filas, no hace nada. Solo crea las filas
a partir de data/exercises.json y data/translations_es.json (versionados
en el repo); NO copia .gif/.webp — esos siguen fuera del repo y de la
imagen por su peso, así que media/ debe poblarse aparte (el mismo proceso
manual de siempre) para que las imágenes no den 404.
"""
from app.database import SessionLocal
from app.models import Exercise
from scripts.exercise_data import build_exercise_values, load_exercises_dataset, load_translations


def main() -> None:
    with SessionLocal() as db:
        if db.query(Exercise.id).first() is not None:
            print("auto_import_exercises: la tabla exercises ya tiene datos, no hago nada.")
            return

        exercises = load_exercises_dataset()
        translations = load_translations()

        for item in exercises:
            values = build_exercise_values(item, translations)
            db.add(Exercise(external_id=item["id"], **values))

        db.commit()
        print(f"auto_import_exercises: importados {len(exercises)} ejercicios.")


if __name__ == "__main__":
    main()
