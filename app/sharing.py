import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.block_exercises import group_by_superset
from app.database import get_db
from app.dependencies import get_current_user, require_user
from app.models import Block, BlockExercise, DayTemplate, Program, SharedLink, User
from app.program_sessions import get_day_content
from app.programs import get_own_day_template, get_own_program
from app.templates import templates

router = APIRouter()


def _get_or_create_share_token(
    db: Session, user_id: int, *, program_id: int | None = None, day_template_id: int | None = None
) -> str:
    query = db.query(SharedLink).filter(SharedLink.user_id == user_id)
    query = (
        query.filter(SharedLink.program_id == program_id)
        if program_id is not None
        else query.filter(SharedLink.day_template_id == day_template_id)
    )
    existing = query.first()
    if existing is not None:
        return existing.token

    token = secrets.token_urlsafe(12)
    db.add(SharedLink(token=token, user_id=user_id, program_id=program_id, day_template_id=day_template_id))
    db.commit()
    return token


def _clone_day_template(db: Session, source_day: DayTemplate, new_program_id: int, day_number: int) -> DayTemplate:
    new_day = DayTemplate(program_id=new_program_id, day_number=day_number, subtitle=source_day.subtitle)
    db.add(new_day)
    db.flush()

    blocks = (
        db.query(Block)
        .filter(Block.day_template_id == source_day.id)
        .order_by(Block.position)
        .all()
    )
    for block in blocks:
        new_block = Block(
            day_template_id=new_day.id,
            type=block.type,
            muscle_group=block.muscle_group,
            variant=block.variant,
            position=block.position,
            num_exercises=block.num_exercises,
            num_sets=block.num_sets,
            rest_seconds=block.rest_seconds,
        )
        db.add(new_block)
        db.flush()

        block_exercises = (
            db.query(BlockExercise)
            .filter(BlockExercise.block_id == block.id)
            .order_by(BlockExercise.position)
            .all()
        )
        for be in block_exercises:
            db.add(BlockExercise(
                block_id=new_block.id,
                exercise_id=be.exercise_id,
                pending_name=be.pending_name,
                position=be.position,
                modo_registro=be.modo_registro,
                reps_min=be.reps_min,
                reps_max=be.reps_max,
                duracion_segundos=be.duracion_segundos,
                target_weight=be.target_weight,
                is_superset_with_next=be.is_superset_with_next,
            ))
    return new_day


def _clone_program_for_user(db: Session, source_program: Program, target_user_id: int) -> Program:
    """Independent copy, same spirit as importing a JSON program: the
    recipient gets their own editable rows referencing the same (shared,
    global) Exercise catalog -- nothing here stays linked back to the
    original, so the sharer changing their routine later never affects it."""
    new_program = Program(
        user_id=target_user_id,
        name=f"{source_program.name} (copia)",
        cycle_days=source_program.cycle_days,
        is_active=False,
    )
    db.add(new_program)
    db.flush()

    source_days = (
        db.query(DayTemplate)
        .filter(DayTemplate.program_id == source_program.id)
        .order_by(DayTemplate.day_number)
        .all()
    )
    for source_day in source_days:
        _clone_day_template(db, source_day, new_program.id, source_day.day_number)
    return new_program


def _clone_day_as_program_for_user(db: Session, source_day: DayTemplate, target_user_id: int) -> Program:
    """A shared single day has no program of its own once copied -- wraps
    it in a fresh 1-day program so it's something the recipient can
    actually activate and train from."""
    label = f"Día {source_day.day_number}"
    if source_day.subtitle:
        label += f" — {source_day.subtitle}"
    new_program = Program(user_id=target_user_id, name=label, cycle_days=1, is_active=False)
    db.add(new_program)
    db.flush()
    _clone_day_template(db, source_day, new_program.id, 1)
    return new_program


@router.post("/programs/{program_id}/share")
async def share_program(
    program_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    program = get_own_program(db, program_id, user.id)
    token = _get_or_create_share_token(db, user.id, program_id=program.id)
    share_url = str(request.url_for("view_shared_link", token=token))
    return templates.TemplateResponse(
        request=request,
        name="sharing/share_result.html",
        context={"share_url": share_url, "title": program.name},
    )


@router.post("/days/{day_template_id}/share")
async def share_day(
    day_template_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    day_template = get_own_day_template(db, day_template_id, user.id)
    token = _get_or_create_share_token(db, user.id, day_template_id=day_template.id)
    share_url = str(request.url_for("view_shared_link", token=token))
    title = f"Día {day_template.day_number}"
    if day_template.subtitle:
        title += f" — {day_template.subtitle}"
    return templates.TemplateResponse(
        request=request,
        name="sharing/share_result.html",
        context={"share_url": share_url, "title": title},
    )


@router.get("/shared/{token}", name="view_shared_link")
async def view_shared_link(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Public: no login required to view. Personal data (ratings, weight
    targets, substitutions) never appears here -- only the routine's own
    structure, which belongs to whoever shared it, not to any one
    trainee's history."""
    link = db.query(SharedLink).filter(SharedLink.token == token).first()
    if link is None:
        raise HTTPException(status_code=404)

    if link.program_id is not None:
        program = db.get(Program, link.program_id)
        if program is None:
            raise HTTPException(status_code=404)
        day_templates = (
            db.query(DayTemplate)
            .filter(DayTemplate.program_id == program.id)
            .order_by(DayTemplate.day_number)
            .all()
        )
        day_summaries = {}
        for day_template in day_templates:
            blocks, _ = get_day_content(db, day_template.id)
            parts = []
            for block in blocks:
                label = block.type
                if block.muscle_group:
                    label += f" · {block.muscle_group}"
                label += f" ({block.num_exercises} ej.)"
                parts.append(label)
            day_summaries[day_template.id] = ", ".join(parts) if parts else "Sin bloques todavía"

        return templates.TemplateResponse(
            request=request,
            name="sharing/view_program.html",
            context={
                "token": token,
                "program": program,
                "day_templates": day_templates,
                "day_summaries": day_summaries,
                "viewer_logged_in": user is not None,
            },
        )

    day_template = db.get(DayTemplate, link.day_template_id)
    if day_template is None:
        raise HTTPException(status_code=404)
    blocks, exercises_by_block = get_day_content(db, day_template.id)
    exercise_groups_by_block = {
        block_id: group_by_superset(attached) for block_id, attached in exercises_by_block.items()
    }
    return templates.TemplateResponse(
        request=request,
        name="sharing/view_day.html",
        context={
            "token": token,
            "day_template": day_template,
            "blocks": blocks,
            "exercise_groups_by_block": exercise_groups_by_block,
            "viewer_logged_in": user is not None,
        },
    )


@router.post("/shared/{token}/copy")
async def copy_shared_link(
    token: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    link = db.query(SharedLink).filter(SharedLink.token == token).first()
    if link is None:
        raise HTTPException(status_code=404)

    if link.program_id is not None:
        source_program = db.get(Program, link.program_id)
        if source_program is None:
            raise HTTPException(status_code=404)
        new_program = _clone_program_for_user(db, source_program, user.id)
    else:
        source_day = db.get(DayTemplate, link.day_template_id)
        if source_day is None:
            raise HTTPException(status_code=404)
        new_program = _clone_day_as_program_for_user(db, source_day, user.id)

    db.commit()
    return RedirectResponse(url=f"/programs/{new_program.id}", status_code=303)
