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


# Kept in sync by hand with migrations/versions/0031_exercise_variante.py,
# which backfills existing rows with the same rules -- this copy only
# affects exercises imported from now on.
def compute_variante(name: str, target_muscle: str) -> str | None:
    name_lower = name.lower()
    if target_muscle == "pectorales":
        if "declinad" in name_lower:
            return "bajo"
        if "inclinad" in name_lower:
            return "alto"
        return None
    if target_muscle in ("dorsales", "espalda alta"):
        if "jalón" in name_lower or "jalon" in name_lower or "dominada" in name_lower:
            return "vertical"
        if "remo" in name_lower:
            return "horizontal"
        return None
    return None


def build_exercise_values(item: dict, translations: dict) -> dict:
    gif_filename = Path(item["gif_url"]).name
    name = translations["name"].get(item["id"], item["name"])
    target_muscle = translations["target_muscle"].get(item["target"], item["target"])
    return {
        "name": name,
        "category": translations["category"].get(item["category"], item["category"]),
        "target_muscle": target_muscle,
        "variante": compute_variante(name, target_muscle),
        "equipment": translations["equipment"].get(item["equipment"], item["equipment"]),
        "gif_url": f"/media/exercises/webp/{Path(gif_filename).stem}.webp",
        "instructions": item["instructions"]["es"],
    }
