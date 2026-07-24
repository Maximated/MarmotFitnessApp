"""Genera Exercise.muscle_description para todos los ejercicios.

El texto explica qué grupo muscular trabaja principalmente el ejercicio y,
en términos generales, qué otros músculos suelen intervenir como sinergistas
en ese tipo de movimiento. Se basa en el target_muscle ya verificado de cada
ejercicio (no se inventa el músculo principal) más una plantilla por grupo
muscular con los sinergistas habituales para ese grupo, con alguna variante
por patrón de movimiento detectado en el nombre (empuje/tracción/aislado,
porción del deltoides implicada, estiramientos).

Uso:
    uv run python scripts/generate_muscle_descriptions.py
"""
from app.database import SessionLocal
from app.models import Exercise

# (nombre_visible, sinergistas habituales en términos generales)
BASE_BY_MUSCLE = {
    "pectorales": ("el pectoral mayor", "el tríceps y el deltoides anterior"),
    "bíceps": ("el bíceps braquial", "el braquial anterior y los flexores del antebrazo"),
    "tríceps": ("el tríceps braquial", "el deltoides y el pectoral, según el ángulo del movimiento"),
    "deltoides": ("el deltoides", "el trapecio y el tríceps"),
    "glúteos": ("el glúteo mayor", "los isquiotibiales y el cuádriceps"),
    "cuádriceps": ("el cuádriceps", "el glúteo y los isquiotibiales como estabilizadores"),
    "isquiotibiales": ("los isquiotibiales", "el glúteo y los gemelos"),
    "gemelos": ("el gastrocnemio y el sóleo", "los estabilizadores del tobillo"),
    "abdominales": ("el recto abdominal y los oblicuos", "los flexores de cadera"),
    "dorsales": ("el dorsal ancho", "el bíceps y los romboides/trapecio medio"),
    "espalda alta": ("el trapecio medio y los romboides", "el deltoides posterior"),
    "trapecios": ("el trapecio", "el elevador de la escápula"),
    "antebrazos": ("los flexores y extensores del antebrazo", "el bíceps en el agarre"),
    "aductores": ("los aductores de la cadera", "el glúteo como estabilizador"),
    "abductores": ("el glúteo medio y los abductores de cadera", "el core como estabilizador"),
    "serrato anterior": ("el serrato anterior", "los estabilizadores de la escápula"),
    "elevador de la escápula": ("el elevador de la escápula", "el trapecio superior"),
    "columna": ("los erectores espinales", "el glúteo y los isquiotibiales"),
    "sistema cardiovascular": ("el sistema cardiovascular", "piernas y core de forma general, según la máquina"),
}


def build_description(name: str, target_muscle: str) -> str:
    primary, synergists = BASE_BY_MUSCLE.get(
        target_muscle, (target_muscle, "otros músculos de la zona")
    )
    lower = name.lower()

    if "estiramiento" in lower:
        return f"Estiramiento centrado en {primary}, sin implicación relevante de otros músculos como motores."

    if target_muscle == "deltoides":
        if "posterior" in lower:
            primary = "la porción posterior del deltoides"
            synergists = "el trapecio medio y los romboides"
        elif "lateral" in lower:
            primary = "la porción lateral del deltoides"
            synergists = "el trapecio"
        elif "frontal" in lower or "anterior" in lower:
            primary = "la porción anterior del deltoides"
            synergists = "el pectoral y el tríceps"

    if target_muscle == "sistema cardiovascular":
        return "Ejercicio cardiovascular que eleva la frecuencia cardíaca, trabajando de forma general piernas y core según la máquina."

    return f"Trabaja principalmente {primary}. En este tipo de movimiento suelen participar también, como sinergistas, {synergists}."


def main() -> None:
    with SessionLocal() as db:
        exercises = db.query(Exercise).all()
        updated = 0
        unknown_muscles = set()
        for exercise in exercises:
            if exercise.target_muscle not in BASE_BY_MUSCLE:
                unknown_muscles.add(exercise.target_muscle)
            exercise.muscle_description = build_description(exercise.name, exercise.target_muscle)
            updated += 1
        db.commit()
        print(f"Actualizados {updated} ejercicios.")
        if unknown_muscles:
            print("Músculos sin plantilla específica (se usó fallback genérico):", unknown_muscles)


if __name__ == "__main__":
    main()
