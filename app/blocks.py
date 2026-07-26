from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_user
from app.models import Block, BlockExercise, DayTemplate, Program, User
from app.programs import get_own_day_template
from app.templates import templates

router = APIRouter()

BLOCK_TYPES = ["Calentamiento", "Grupo muscular", "Cardio", "Estiramiento"]
MUSCLE_GROUPS = [
    "Abdomen",
    "Pecho",
    "Espalda",
    "Bíceps",
    "Tríceps",
    "Hombro",
    "Pierna",
    "Pantorrilla",
]
REST_SECONDS_CHOICES = [15, 30, 60, 90, 120, 150, 180, 210]


def get_own_block(db: Session, block_id: int, user_id: int) -> Block:
    block = (
        db.query(Block)
        .join(DayTemplate, Block.day_template_id == DayTemplate.id)
        .join(Program, DayTemplate.program_id == Program.id)
        .filter(Block.id == block_id, Program.user_id == user_id)
        .first()
    )
    if block is None:
        raise HTTPException(status_code=404)
    return block


def resolve_rest_seconds(rest_seconds_select: str, rest_seconds_custom: str) -> int:
    if rest_seconds_select == "other":
        if not rest_seconds_custom.strip():
            raise HTTPException(
                status_code=400, detail="Indica el descanso personalizado en segundos."
            )
        return int(rest_seconds_custom)
    return int(rest_seconds_select)


@router.get("/days/{day_template_id}")
async def view_day_template(
    day_template_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    day_template = get_own_day_template(db, day_template_id, user.id)
    program = db.get(Program, day_template.program_id)
    blocks = (
        db.query(Block)
        .filter(Block.day_template_id == day_template.id)
        .order_by(Block.position)
        .all()
    )
    exercise_counts = {
        block_id: count
        for block_id, count in db.query(
            BlockExercise.block_id, func.count(BlockExercise.id)
        )
        .filter(BlockExercise.block_id.in_([b.id for b in blocks]))
        .group_by(BlockExercise.block_id)
        .all()
    }
    pending_counts = {
        block_id: count
        for block_id, count in db.query(
            BlockExercise.block_id, func.count(BlockExercise.id)
        )
        .filter(
            BlockExercise.block_id.in_([b.id for b in blocks]),
            BlockExercise.exercise_id.is_(None),
            BlockExercise.modo_registro != "checklist",
        )
        .group_by(BlockExercise.block_id)
        .all()
    }
    return templates.TemplateResponse(
        request=request,
        name="days/view.html",
        context={
            "program": program,
            "day_template": day_template,
            "blocks": blocks,
            "exercise_counts": exercise_counts,
            "pending_counts": pending_counts,
            "block_types": BLOCK_TYPES,
            "muscle_groups": MUSCLE_GROUPS,
            "rest_seconds_choices": REST_SECONDS_CHOICES,
        },
    )


@router.post("/days/{day_template_id}/blocks")
async def create_block(
    day_template_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    type: str = Form(...),
    muscle_group: str = Form(""),
    num_exercises: int = Form(...),
    num_sets: str = Form(""),
    rest_seconds_select: str = Form(...),
    rest_seconds_custom: str = Form(""),
):
    day_template = get_own_day_template(db, day_template_id, user.id)
    rest_seconds = resolve_rest_seconds(rest_seconds_select, rest_seconds_custom)

    next_position = (
        db.query(Block).filter(Block.day_template_id == day_template.id).count() + 1
    )

    db.add(
        Block(
            day_template_id=day_template.id,
            type=type,
            muscle_group=muscle_group or None,
            position=next_position,
            num_exercises=num_exercises,
            num_sets=int(num_sets) if num_sets.strip() else None,
            rest_seconds=rest_seconds,
        )
    )
    db.commit()

    return RedirectResponse(url=f"/days/{day_template.id}", status_code=303)


@router.get("/blocks/{block_id}/edit")
async def edit_block_form(
    block_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    block = get_own_block(db, block_id, user.id)
    rest_seconds_select = (
        str(block.rest_seconds)
        if block.rest_seconds in REST_SECONDS_CHOICES
        else "other"
    )
    return templates.TemplateResponse(
        request=request,
        name="blocks/edit.html",
        context={
            "block": block,
            "block_types": BLOCK_TYPES,
            "muscle_groups": MUSCLE_GROUPS,
            "rest_seconds_choices": REST_SECONDS_CHOICES,
            "rest_seconds_select": rest_seconds_select,
        },
    )


@router.post("/blocks/{block_id}/edit")
async def edit_block_submit(
    block_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    type: str = Form(...),
    muscle_group: str = Form(""),
    num_exercises: int = Form(...),
    num_sets: str = Form(""),
    rest_seconds_select: str = Form(...),
    rest_seconds_custom: str = Form(""),
):
    block = get_own_block(db, block_id, user.id)
    rest_seconds = resolve_rest_seconds(rest_seconds_select, rest_seconds_custom)

    block.type = type
    block.muscle_group = muscle_group or None
    block.num_exercises = num_exercises
    block.num_sets = int(num_sets) if num_sets.strip() else None
    block.rest_seconds = rest_seconds
    db.commit()

    return RedirectResponse(url=f"/days/{block.day_template_id}", status_code=303)


@router.post("/blocks/{block_id}/delete")
async def delete_block(
    block_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    block = get_own_block(db, block_id, user.id)
    day_template_id = block.day_template_id
    deleted_position = block.position

    db.delete(block)
    db.flush()

    later_blocks = (
        db.query(Block)
        .filter(
            Block.day_template_id == day_template_id,
            Block.position > deleted_position,
        )
        .order_by(Block.position)
        .all()
    )
    for later_block in later_blocks:
        later_block.position -= 1
        db.flush()

    db.commit()

    return RedirectResponse(url=f"/days/{day_template_id}", status_code=303)
