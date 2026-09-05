import json
from pathlib import Path

DEFAULT_PROGRAMS_DIR = Path(__file__).parent / "default_programs"
LEVELS = ["principiante", "intermedio", "avanzado"]


def list_starter_groups() -> list[dict]:
    """Escanea DEFAULT_PROGRAMS_DIR: una subcarpeta por grupo, un archivo
    *_<nivel>.json por nivel. El nombre del grupo se deriva del propio
    "programa" del JSON (p.ej. "Brazos - Principiante" -> "Brazos") en vez
    de mantener un mapeo aparte, así un cambio de nombre en los JSON no
    puede desincronizarse del catálogo."""
    groups = []
    for group_dir in sorted(DEFAULT_PROGRAMS_DIR.iterdir()):
        if not group_dir.is_dir():
            continue
        levels = []
        group_name = None
        for level in LEVELS:
            matches = list(group_dir.glob(f"*_{level}.json"))
            if not matches:
                continue
            data = json.loads(matches[0].read_text())
            program_name = data.get("programa", matches[0].stem)
            if group_name is None:
                group_name = program_name.rsplit(" - ", 1)[0]
            levels.append(
                {
                    "level": level,
                    "label": level.capitalize(),
                    "program_name": program_name,
                    "notes": data.get("notas"),
                }
            )
        if levels:
            groups.append({"slug": group_dir.name, "name": group_name, "levels": levels})
    groups.sort(key=lambda g: g["name"])
    return groups


def resolve_starter_file(group: str, level: str) -> Path | None:
    """Solo devuelve una ruta si (group, level) aparece literalmente en el
    catálogo escaneado -- nunca se construye un Path a partir de `group`/
    `level` sin pasar por aquí, para que un intento de path traversal en
    esos campos (llegan como Form fields) no tenga ningún efecto."""
    for candidate_group in DEFAULT_PROGRAMS_DIR.iterdir():
        if not candidate_group.is_dir() or candidate_group.name != group:
            continue
        if level not in LEVELS:
            return None
        matches = list(candidate_group.glob(f"*_{level}.json"))
        return matches[0] if matches else None
    return None
