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
