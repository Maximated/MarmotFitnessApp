from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_user
from app.models import Block, BlockExercise, DayTemplate, Program, User
from app.templates import templates

router = APIRouter()


def get_own_program(db: Session, program_id: int, user_id: int) -> Program:
    program = (
        db.query(Program)
        .filter(Program.id == program_id, Program.user_id == user_id)
        .first()
    )
    if program is None:
        raise HTTPException(status_code=404)
    return program


def get_own_day_template(db: Session, day_template_id: int, user_id: int) -> DayTemplate:
    day_template = (
        db.query(DayTemplate)
        .join(Program, DayTemplate.program_id == Program.id)
        .filter(DayTemplate.id == day_template_id, Program.user_id == user_id)
        .first()
    )
    if day_template is None:
        raise HTTPException(status_code=404)
    return day_template


def sync_day_templates(db: Session, program: Program) -> None:
    existing = {
        dt.day_number: dt
        for dt in db.query(DayTemplate).filter(DayTemplate.program_id == program.id).all()
    }
    for day_number in range(1, program.cycle_days + 1):
        if day_number not in existing:
            db.add(DayTemplate(program_id=program.id, day_number=day_number))
    for day_number, day_template in existing.items():
        if day_number > program.cycle_days:
            db.delete(day_template)


@router.get("/programs")
async def list_programs(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    programs = (
        db.query(Program)
        .filter(Program.user_id == user.id)
        .order_by(Program.name)
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="programs/list.html",
        context={"programs": programs},
    )


@router.get("/programs/new")
async def new_program_form(
    request: Request,
    user: User = Depends(require_user),
):
    return templates.TemplateResponse(
        request=request,
        name="programs/new.html",
        context={},
    )


@router.post("/programs")
async def create_program(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    name: str = Form(...),
    cycle_days: int = Form(...),
):
    program = Program(user_id=user.id, name=name, cycle_days=cycle_days)
    db.add(program)
    db.flush()
    sync_day_templates(db, program)
    db.commit()

    return RedirectResponse(url=f"/programs/{program.id}", status_code=303)


@router.get("/programs/{program_id}")
async def view_program(
    program_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    copy_from: int | None = None,
):
    program = get_own_program(db, program_id, user.id)
    day_templates = (
        db.query(DayTemplate)
        .filter(DayTemplate.program_id == program.id)
        .order_by(DayTemplate.day_number)
        .all()
    )

    blocks = (
        db.query(Block)
        .join(DayTemplate, Block.day_template_id == DayTemplate.id)
        .filter(DayTemplate.program_id == program.id)
        .order_by(Block.day_template_id, Block.position)
        .all()
    )
    blocks_by_day: dict[int, list[Block]] = {}
    for block in blocks:
        blocks_by_day.setdefault(block.day_template_id, []).append(block)

    day_summaries = {}
    for day_template in day_templates:
        parts = []
        for block in blocks_by_day.get(day_template.id, []):
            label = block.type
            if block.muscle_group:
                label += f" · {block.muscle_group}"
            label += f" ({block.num_exercises} ej.)"
            parts.append(label)
        day_summaries[day_template.id] = ", ".join(parts) if parts else "Sin bloques todavía"

    return templates.TemplateResponse(
        request=request,
        name="programs/view.html",
        context={
            "program": program,
            "day_templates": day_templates,
            "day_summaries": day_summaries,
            "copy_from": copy_from,
        },
    )


@router.get("/programs/{program_id}/edit")
async def edit_program_form(
    program_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    program = get_own_program(db, program_id, user.id)
    return templates.TemplateResponse(
        request=request,
        name="programs/edit.html",
        context={"program": program},
    )


@router.post("/programs/{program_id}/edit")
async def edit_program_submit(
    program_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    name: str = Form(...),
    cycle_days: int = Form(...),
):
    program = get_own_program(db, program_id, user.id)
    program.name = name
    program.cycle_days = cycle_days
    db.flush()
    sync_day_templates(db, program)
    db.commit()

    return RedirectResponse(url=f"/programs/{program.id}", status_code=303)


@router.post("/programs/{program_id}/activate")
async def activate_program(
    program_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    starting_day_number: int = Form(1),
):
    program = get_own_program(db, program_id, user.id)
    if not (1 <= starting_day_number <= program.cycle_days):
        raise HTTPException(status_code=400, detail="Número de jornada inválido")

    db.query(Program).filter(Program.user_id == user.id, Program.id != program.id).update(
        {"is_active": False}
    )
    program.is_active = True
    program.current_day_number = starting_day_number
    program.next_due_date = date.today()
    db.commit()

    return RedirectResponse(url=f"/programs/{program.id}", status_code=303)


@router.post("/programs/{program_id}/archive")
async def archive_program(
    program_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    program = get_own_program(db, program_id, user.id)
    program.is_active = False
    db.commit()

    return RedirectResponse(url="/programs", status_code=303)


@router.post("/days/{day_template_id}/delete")
async def delete_day_template(
    day_template_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    day_template = get_own_day_template(db, day_template_id, user.id)
    program = db.get(Program, day_template.program_id)
    deleted_day_number = day_template.day_number

    db.delete(day_template)
    db.flush()

    later_days = (
        db.query(DayTemplate)
        .filter(
            DayTemplate.program_id == program.id,
            DayTemplate.day_number > deleted_day_number,
        )
        .order_by(DayTemplate.day_number)
        .all()
    )
    for later_day in later_days:
        later_day.day_number -= 1
        db.flush()

    program.cycle_days -= 1
    db.commit()

    return RedirectResponse(url=f"/programs/{program.id}", status_code=303)


@router.post("/days/{day_template_id}/subtitle")
async def set_day_subtitle(
    day_template_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    subtitle: str = Form(""),
):
    day_template = get_own_day_template(db, day_template_id, user.id)
    day_template.subtitle = subtitle.strip() or None
    db.commit()

    return RedirectResponse(url=f"/days/{day_template.id}", status_code=303)


@router.post("/days/{day_template_id}/paste")
async def paste_day(
    day_template_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    copy_from: int = Form(...),
):
    target = get_own_day_template(db, day_template_id, user.id)
    source = get_own_day_template(db, copy_from, user.id)

    if source.program_id != target.program_id:
        raise HTTPException(status_code=400, detail="Los días deben pertenecer al mismo programa.")

    target.subtitle = source.subtitle

    db.query(Block).filter(Block.day_template_id == target.id).delete()
    db.flush()

    source_blocks = (
        db.query(Block)
        .filter(Block.day_template_id == source.id)
        .order_by(Block.position)
        .all()
    )
    for source_block in source_blocks:
        new_block = Block(
            day_template_id=target.id,
            type=source_block.type,
            muscle_group=source_block.muscle_group,
            variant=source_block.variant,
            position=source_block.position,
            num_exercises=source_block.num_exercises,
            num_sets=source_block.num_sets,
            rest_seconds=source_block.rest_seconds,
        )
        db.add(new_block)
        db.flush()

        source_exercises = (
            db.query(BlockExercise)
            .filter(BlockExercise.block_id == source_block.id)
            .order_by(BlockExercise.position)
            .all()
        )
        for source_exercise in source_exercises:
            db.add(
                BlockExercise(
                    block_id=new_block.id,
                    exercise_id=source_exercise.exercise_id,
                    position=source_exercise.position,
                    reps_min=source_exercise.reps_min,
                    reps_max=source_exercise.reps_max,
                    target_weight=source_exercise.target_weight,
                    is_superset_with_next=source_exercise.is_superset_with_next,
                )
            )

    db.commit()

    return RedirectResponse(url=f"/programs/{target.program_id}", status_code=303)
