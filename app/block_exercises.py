from math import ceil
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.blocks import get_own_block
from app.database import get_db
from app.dependencies import require_user
from app.models import BlockExercise, Exercise, User
from app.templates import templates

router = APIRouter()

SEARCH_PER_PAGE = 12


def get_own_block_exercise(db: Session, block_exercise_id: int, user_id: int) -> BlockExercise:
    block_exercise = db.get(BlockExercise, block_exercise_id)
    if block_exercise is None:
        raise HTTPException(status_code=404)
    get_own_block(db, block_exercise.block_id, user_id)
    return block_exercise


def group_by_superset(attached: list[tuple[BlockExercise, Exercise]]) -> list[list]:
    groups = []
    i = 0
    while i < len(attached):
        block_exercise, _ = attached[i]
        if block_exercise.is_superset_with_next and i + 1 < len(attached):
            groups.append([attached[i], attached[i + 1]])
            i += 2
        else:
            groups.append([attached[i]])
            i += 1
    return groups


@router.get("/blocks/{block_id}/exercises")
async def view_block_exercises(
    block_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    q: str | None = None,
    category: str | None = None,
    equipment: str | None = None,
):
    block = get_own_block(db, block_id, user.id)

    attached = (
        db.query(BlockExercise, Exercise)
        .join(Exercise, BlockExercise.exercise_id == Exercise.id)
        .filter(BlockExercise.block_id == block.id)
        .order_by(BlockExercise.position)
        .all()
    )

    groups = group_by_superset(attached)

    results = []
    if q or category or equipment:
        query = db.query(Exercise)
        if q:
            query = query.filter(Exercise.name.ilike(f"%{q}%"))
        if category:
            query = query.filter(Exercise.category == category)
        if equipment:
            query = query.filter(Exercise.equipment == equipment)
        results = query.order_by(Exercise.name).limit(SEARCH_PER_PAGE).all()

    categories = [
        row[0]
        for row in db.query(Exercise.category).distinct().order_by(Exercise.category)
    ]
    equipments = [
        row[0]
        for row in db.query(Exercise.equipment).distinct().order_by(Exercise.equipment)
    ]

    filters = {
        k: v for k, v in {"q": q, "category": category, "equipment": equipment}.items() if v
    }

    return templates.TemplateResponse(
        request=request,
        name="blocks/exercises.html",
        context={
            "block": block,
            "attached": attached,
            "groups": groups,
            "results": results,
            "searched": bool(q or category or equipment),
            "categories": categories,
            "equipments": equipments,
            "q": q or "",
            "category": category or "",
            "equipment": equipment or "",
            "filters_qs": urlencode(filters),
            "is_full": len(attached) >= block.num_exercises,
        },
    )


@router.post("/blocks/{block_id}/exercises")
async def add_block_exercise(
    block_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    exercise_id: int = Form(...),
    reps: str = Form(""),
    filters_qs: str = Form(""),
):
    block = get_own_block(db, block_id, user.id)

    current_count = (
        db.query(BlockExercise).filter(BlockExercise.block_id == block.id).count()
    )
    if current_count >= block.num_exercises:
        raise HTTPException(
            status_code=400,
            detail=f"Este bloque ya tiene los {block.num_exercises} ejercicios declarados.",
        )

    db.add(
        BlockExercise(
            block_id=block.id,
            exercise_id=exercise_id,
            position=current_count + 1,
            reps=int(reps) if reps.strip() else None,
        )
    )
    db.commit()

    redirect_url = f"/blocks/{block.id}/exercises"
    if filters_qs:
        redirect_url += f"?{filters_qs}"
    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/block-exercises/{block_exercise_id}/edit")
async def edit_block_exercise_form(
    block_exercise_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    block_exercise = get_own_block_exercise(db, block_exercise_id, user.id)
    exercise = db.get(Exercise, block_exercise.exercise_id)
    return templates.TemplateResponse(
        request=request,
        name="blocks/edit_exercise.html",
        context={"block_exercise": block_exercise, "exercise": exercise},
    )


@router.post("/block-exercises/{block_exercise_id}/edit")
async def edit_block_exercise_submit(
    block_exercise_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    reps: str = Form(""),
    is_superset_with_next: bool = Form(False),
):
    block_exercise = get_own_block_exercise(db, block_exercise_id, user.id)
    block_exercise.reps = int(reps) if reps.strip() else None
    block_exercise.is_superset_with_next = is_superset_with_next
    db.commit()

    return RedirectResponse(url=f"/blocks/{block_exercise.block_id}/exercises", status_code=303)


@router.post("/block-exercises/{block_exercise_id}/delete")
async def delete_block_exercise(
    block_exercise_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    block_exercise = get_own_block_exercise(db, block_exercise_id, user.id)
    block_id = block_exercise.block_id
    deleted_position = block_exercise.position

    db.delete(block_exercise)
    db.flush()

    later = (
        db.query(BlockExercise)
        .filter(BlockExercise.block_id == block_id, BlockExercise.position > deleted_position)
        .order_by(BlockExercise.position)
        .all()
    )
    for item in later:
        item.position -= 1
        db.flush()

    db.commit()

    return RedirectResponse(url=f"/blocks/{block_id}/exercises", status_code=303)
