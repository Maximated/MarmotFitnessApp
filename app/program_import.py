import json

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.blocks import BLOCK_TYPES
from app.database import get_db
from app.dependencies import require_user
from app.exercise_matching import ExerciseMatcher
from app.models import Block, BlockExercise, DayTemplate, Program, User
from app.templates import templates

router = APIRouter()

TIPO_MAP = {
    "calentamiento": "Calentamiento",
    "grupo_muscular": "Grupo muscular",
    "cardio": "Cardio",
    "estiramiento": "Estiramiento",
}


def map_block_type(tipo: str) -> str:
    key = (tipo or "").strip().lower()
    if key in TIPO_MAP:
        return TIPO_MAP[key]
    fallback = tipo.replace("_", " ").strip().capitalize()
    return fallback or BLOCK_TYPES[1]


def compute_superset_flags(ejercicios: list[dict]) -> list[bool]:
    flags = []
    for i, item in enumerate(ejercicios):
        current = item.get("superset_con")
        following = ejercicios[i + 1].get("superset_con") if i + 1 < len(ejercicios) else None
        flags.append(bool(current) and current == following)
    return flags


@router.post("/programs/import")
async def import_program_submit(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    file: UploadFile = File(...),
):
    raw = await file.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return templates.TemplateResponse(
            request=request,
            name="programs/new.html",
            context={"error": f"El archivo no es un JSON válido: {exc}"},
        )

    jornadas = data.get("jornadas") or []
    if not data.get("programa") or not jornadas:
        return templates.TemplateResponse(
            request=request,
            name="programs/new.html",
            context={"error": "El JSON debe traer \"programa\" y al menos una jornada en \"jornadas\"."},
        )

    try:
        matcher = ExerciseMatcher(db)
        counts = {"id": 0, "alias": 0, "name": 0, "fuzzy": 0, "pending": 0}
        detail_rows = []
        pending_refs = []

        program = Program(
            user_id=user.id, name=data["programa"], cycle_days=len(jornadas), is_active=False
        )
        db.add(program)
        db.flush()

        for day_number, jornada in enumerate(jornadas, start=1):
            day_template = DayTemplate(
                program_id=program.id, day_number=day_number, subtitle=jornada.get("nombre")
            )
            db.add(day_template)
            db.flush()

            for block_pos, bloque in enumerate(jornada.get("bloques", []), start=1):
                ejercicios = bloque.get("ejercicios")
                block = Block(
                    day_template_id=day_template.id,
                    type=map_block_type(bloque.get("tipo", "")),
                    muscle_group=bloque.get("muscle_group") or None,
                    variant=bloque.get("variante") or None,
                    position=block_pos,
                    num_exercises=len(ejercicios) if ejercicios else 0,
                    num_sets=bloque.get("num_sets"),
                    rest_seconds=bloque.get("descanso_segundos") or 0,
                )
                db.add(block)
                db.flush()

                if not ejercicios:
                    continue

                superset_flags = compute_superset_flags(ejercicios)
                for ex_pos, (item, is_superset) in enumerate(zip(ejercicios, superset_flags), start=1):
                    exercise_id, method, score = matcher.resolve(
                        item.get("id_dataset"), item["nombre"]
                    )
                    counts[method] += 1
                    detail_rows.append(
                        {
                            "jornada": day_number,
                            "nombre": item["nombre"],
                            "method": method,
                            "score": round(score) if score is not None else None,
                        }
                    )
                    modo = item.get("modo", "series")
                    block_exercise = BlockExercise(
                        block_id=block.id,
                        exercise_id=exercise_id,
                        pending_name=item["nombre"] if exercise_id is None else None,
                        position=ex_pos,
                        modo_registro=modo,
                        reps_min=item.get("reps_min") if modo != "tiempo" else None,
                        reps_max=item.get("reps_max") if modo != "tiempo" else None,
                        duracion_segundos=item.get("duracion_segundos") if modo == "tiempo" else None,
                        is_superset_with_next=is_superset,
                    )
                    db.add(block_exercise)
                    if exercise_id is None:
                        pending_refs.append(block_exercise)

        db.flush()
        pending_list = [{"id": be.id, "name": be.pending_name} for be in pending_refs]
        db.commit()
    except Exception as exc:
        db.rollback()
        return templates.TemplateResponse(
            request=request,
            name="programs/new.html",
            context={"error": f"No se pudo importar el programa: {exc}"},
        )

    return templates.TemplateResponse(
        request=request,
        name="programs/import_result.html",
        context={
            "program": program,
            "counts": counts,
            "detail_rows": detail_rows,
            "pending_list": pending_list,
        },
    )
