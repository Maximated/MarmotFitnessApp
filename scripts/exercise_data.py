"""Mapeo compartido item-del-dataset -> valores de `Exercise`.

Usado tanto por import_exercises.py (importación manual completa, con
copia de .gif) como por auto_import_exercises.py (bootstrap automático
al arrancar el contenedor, solo filas de base de datos).
"""
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRANSLATIONS_PATH = PROJECT_ROOT / "data" / "translations_es.json"


def load_translations() -> dict:
    if not TRANSLATIONS_PATH.exists():
        return {"category": {}, "equipment": {}, "target_muscle": {}, "name": {}}
    return json.loads(TRANSLATIONS_PATH.read_text())


def load_exercises_dataset() -> list[dict]:
    return json.loads((PROJECT_ROOT / "data" / "exercises.json").read_text())


def build_exercise_values(item: dict, translations: dict) -> dict:
    gif_filename = Path(item["gif_url"]).name
    return {
        "name": translations["name"].get(item["id"], item["name"]),
        "category": translations["category"].get(item["category"], item["category"]),
        "target_muscle": translations["target_muscle"].get(item["target"], item["target"]),
        "equipment": translations["equipment"].get(item["equipment"], item["equipment"]),
        "gif_url": f"/media/exercises/webp/{Path(gif_filename).stem}.webp",
        "instructions": item["instructions"]["es"],
    }
