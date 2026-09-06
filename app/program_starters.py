import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.default_programs import list_starter_groups, resolve_starter_file
from app.dependencies import require_user
from app.models import User
from app.program_import import import_program_data
from app.templates import templates

router = APIRouter()


@router.get("/programs/starter")
async def starter_programs(
    request: Request,
    user: User = Depends(require_user),
):
    return templates.TemplateResponse(
        request=request,
        name="programs/starter.html",
        context={"groups": list_starter_groups()},
    )


@router.get("/programs/starter/{group}/{level}")
async def starter_program_preview(
    group: str,
    level: str,
    request: Request,
    user: User = Depends(require_user),
):
    """Read-only look at what a starter routine actually contains, straight
    from its JSON file -- no DB write at all, so just browsing several
    levels to compare them can never create a Program. Only the "Cargar
    esta rutina" button at the bottom (starter_program_import below) does
    that, and only once per tap."""
    path = resolve_starter_file(group, level)
    if path is None:
        raise HTTPException(status_code=404)
    data = json.loads(path.read_text())
    return templates.TemplateResponse(
        request=request,
        name="programs/starter_preview.html",
        context={"group": group, "level": level, "data": data},
    )


@router.post("/programs/starter/import")
async def starter_program_import(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    group: str = Form(...),
    level: str = Form(...),
):
    path = resolve_starter_file(group, level)
    if path is None:
        raise HTTPException(status_code=404)

    data = json.loads(path.read_text())
    try:
        program, counts, detail_rows, pending_list = import_program_data(db, user, data)
        db.commit()
    except Exception as exc:
        db.rollback()
        return templates.TemplateResponse(
            request=request,
            name="programs/new.html",
            context={"error": f"No se pudo importar la rutina: {exc}"},
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
