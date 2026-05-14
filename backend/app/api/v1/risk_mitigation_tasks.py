"""Risk mitigation tasks API — task CRUD + per-occurrence complete / skip.

Endpoints land under two prefixes:

* ``/risks/{risk_id}/mitigation-tasks`` — list / create (risk-scoped)
* ``/mitigation-tasks/...`` — task & occurrence-scoped operations

Permission model:

* ``risks.view`` — read tasks and occurrence history.
* ``risks.manage`` — create / edit / delete tasks, complete / skip any
  occurrence on any task.
* **Carve-out**: a user without ``risks.manage`` who is the
  ``assigned_owner_id`` of an open occurrence can still complete that
  occurrence. This means assignees don't have to escalate just to mark
  their own control review done.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.risk import Risk
from app.models.risk_mitigation_task import (
    RiskMitigationTask,
    RiskMitigationTaskOccurrence,
)
from app.models.user import User
from app.schemas.risk_mitigation_task import (
    MitigationTaskCreate,
    MitigationTaskOccurrenceOut,
    MitigationTaskOut,
    MitigationTaskUpdate,
    OccurrenceCompleteRequest,
)
from app.services.permission_service import PermissionService
from app.services.risk_mitigation_task_service import (
    RECURRENCE_UNITS,
    apply_task_owner_change,
    complete_occurrence,
    create_task_with_first_occurrence,
    delete_task_todo,
    occurrence_to_dict,
    open_occurrence,
    publish_task_event,
    skip_occurrence,
    task_to_dict,
    tasks_for_risk,
)

logger = logging.getLogger(__name__)

# Sub-route on /risks for risk-scoped operations (list, create).
risks_router = APIRouter(prefix="/risks", tags=["Risks"])
# Stand-alone router for task / occurrence operations.
tasks_router = APIRouter(prefix="/mitigation-tasks", tags=["Risks"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_uuid(value: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(400, f"Invalid {label}") from exc


async def _load_risk(db: AsyncSession, risk_id: str) -> Risk:
    risk = await db.get(Risk, _parse_uuid(risk_id, "risk id"))
    if risk is None:
        raise HTTPException(404, "Risk not found")
    return risk


async def _load_task(db: AsyncSession, task_id: str) -> RiskMitigationTask:
    task = await db.get(RiskMitigationTask, _parse_uuid(task_id, "task id"))
    if task is None:
        raise HTTPException(404, "Mitigation task not found")
    return task


async def _load_occurrence(
    db: AsyncSession, task: RiskMitigationTask, occurrence_id: str
) -> RiskMitigationTaskOccurrence:
    occ = await db.get(RiskMitigationTaskOccurrence, _parse_uuid(occurrence_id, "occurrence id"))
    if occ is None or occ.task_id != task.id:
        raise HTTPException(404, "Occurrence not found")
    return occ


def _parse_optional_owner(value: str | None) -> uuid.UUID | None:
    if value is None or value == "":
        return None
    return _parse_uuid(value, "owner_id")


# ---------------------------------------------------------------------------
# List / create — risk-scoped
# ---------------------------------------------------------------------------


@risks_router.get("/{risk_id}/mitigation-tasks", response_model=list[MitigationTaskOut])
async def list_mitigation_tasks(
    risk_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MitigationTaskOut]:
    await PermissionService.require_permission(db, user, "risks.view")
    await _load_risk(db, risk_id)
    tasks = await tasks_for_risk(db, _parse_uuid(risk_id, "risk id"))
    return [MitigationTaskOut.model_validate(await task_to_dict(db, t)) for t in tasks]


@risks_router.post("/{risk_id}/mitigation-tasks", response_model=MitigationTaskOut)
async def create_mitigation_task(
    risk_id: str,
    body: MitigationTaskCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MitigationTaskOut:
    await PermissionService.require_permission(db, user, "risks.manage")
    risk = await _load_risk(db, risk_id)
    if risk.status == "closed":
        raise HTTPException(409, "Risk is closed and read-only. Reopen it first to add tasks.")

    if body.recurrence_unit not in RECURRENCE_UNITS:
        raise HTTPException(400, f"Invalid recurrence_unit: {body.recurrence_unit}")

    task, _ = await create_task_with_first_occurrence(
        db,
        risk=risk,
        title=body.title,
        description=body.description,
        owner_id=_parse_optional_owner(body.owner_id),
        due_date=body.due_date,
        recurrence_unit=body.recurrence_unit,
        recurrence_interval=body.recurrence_interval,
        actor_id=user.id,
    )
    await db.commit()
    await db.refresh(task)
    return MitigationTaskOut.model_validate(await task_to_dict(db, task))


# ---------------------------------------------------------------------------
# Task-scoped operations
# ---------------------------------------------------------------------------


@tasks_router.patch("/{task_id}", response_model=MitigationTaskOut)
async def update_mitigation_task(
    task_id: str,
    body: MitigationTaskUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MitigationTaskOut:
    await PermissionService.require_permission(db, user, "risks.manage")
    task = await _load_task(db, task_id)
    risk = await db.get(Risk, task.risk_id)
    if risk is None:
        raise HTTPException(404, "Parent risk not found")
    if risk.status == "closed":
        raise HTTPException(409, "Risk is closed and read-only. Reopen it first to edit tasks.")

    data = body.model_dump(exclude_unset=True)
    previous_owner = task.owner_id

    if "title" in data:
        title = (data["title"] or "").strip()
        if not title:
            raise HTTPException(400, "title cannot be empty")
        task.title = title[:500]
    if "description" in data:
        task.description = data["description"]
    if "owner_id" in data:
        task.owner_id = _parse_optional_owner(data["owner_id"])
    if "recurrence_unit" in data and data["recurrence_unit"] is not None:
        if data["recurrence_unit"] not in RECURRENCE_UNITS:
            raise HTTPException(400, "Invalid recurrence_unit")
        task.recurrence_unit = data["recurrence_unit"]
    if "recurrence_interval" in data and data["recurrence_interval"] is not None:
        task.recurrence_interval = max(1, int(data["recurrence_interval"]))
    if "is_active" in data and data["is_active"] is not None:
        task.is_active = bool(data["is_active"])

    if "due_date" in data:
        # Apply to the current open occurrence only — past occurrences
        # are immutable per the audit contract.
        current = await open_occurrence(db, task.id)
        if current is not None:
            current.due_date = data["due_date"]

    await db.flush()

    if "owner_id" in data:
        await apply_task_owner_change(
            db,
            risk=risk,
            task=task,
            previous_owner=previous_owner,
            actor_id=user.id,
        )

    await publish_task_event(
        db,
        risk=risk,
        task=task,
        event_type="risk_mitigation_task.updated",
        actor_id=user.id,
        extra={"fields": sorted(data.keys())},
    )

    await db.commit()
    await db.refresh(task)
    return MitigationTaskOut.model_validate(await task_to_dict(db, task))


@tasks_router.delete("/{task_id}")
async def delete_mitigation_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, bool]:
    await PermissionService.require_permission(db, user, "risks.manage")
    task = await _load_task(db, task_id)
    risk = await db.get(Risk, task.risk_id)
    if risk is None:
        raise HTTPException(404, "Parent risk not found")
    if risk.status == "closed":
        raise HTTPException(409, "Risk is closed and read-only. Reopen it first to delete tasks.")

    await publish_task_event(
        db,
        risk=risk,
        task=task,
        event_type="risk_mitigation_task.deleted",
        actor_id=user.id,
    )
    await delete_task_todo(db, risk=risk, task=task)
    await db.delete(task)
    await db.commit()
    return {"ok": True}


@tasks_router.get("/{task_id}/occurrences", response_model=list[MitigationTaskOccurrenceOut])
async def list_task_occurrences(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MitigationTaskOccurrenceOut]:
    await PermissionService.require_permission(db, user, "risks.view")
    task = await _load_task(db, task_id)
    res = await db.execute(
        select(RiskMitigationTaskOccurrence)
        .where(RiskMitigationTaskOccurrence.task_id == task.id)
        .order_by(RiskMitigationTaskOccurrence.sequence.desc())
    )
    occurrences = list(res.scalars().all())
    return [
        MitigationTaskOccurrenceOut.model_validate(await occurrence_to_dict(db, o))
        for o in occurrences
    ]


# ---------------------------------------------------------------------------
# Occurrence-scoped: complete / skip
# ---------------------------------------------------------------------------


async def _ensure_can_terminate(
    db: AsyncSession,
    *,
    user: User,
    occurrence: RiskMitigationTaskOccurrence,
    require_full_manage: bool,
) -> None:
    """Permission gate for complete/skip.

    * Skip always requires ``risks.manage``.
    * Complete is allowed for ``risks.manage`` OR for the user who is
      currently ``assigned_owner_id`` on the open occurrence.
    """
    if require_full_manage:
        await PermissionService.require_permission(db, user, "risks.manage")
        return

    if occurrence.assigned_owner_id == user.id:
        await PermissionService.require_permission(db, user, "risks.view")
        return

    await PermissionService.require_permission(db, user, "risks.manage")


@tasks_router.post(
    "/{task_id}/occurrences/{occurrence_id}/complete",
    response_model=MitigationTaskOut,
)
async def complete_task_occurrence(
    task_id: str,
    occurrence_id: str,
    body: OccurrenceCompleteRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MitigationTaskOut:
    task = await _load_task(db, task_id)
    occurrence = await _load_occurrence(db, task, occurrence_id)
    if occurrence.status != "open":
        raise HTTPException(409, f"Occurrence is already {occurrence.status}")

    await _ensure_can_terminate(db, user=user, occurrence=occurrence, require_full_manage=False)

    risk = await db.get(Risk, task.risk_id)
    if risk is None:
        raise HTTPException(404, "Parent risk not found")
    if risk.status == "closed":
        raise HTTPException(409, "Risk is closed and read-only. Reopen it first to update tasks.")

    notes = (body.notes if body else None) or None
    await complete_occurrence(
        db,
        risk=risk,
        task=task,
        occurrence=occurrence,
        actor_id=user.id,
        notes=notes,
    )
    await db.commit()
    await db.refresh(task)
    return MitigationTaskOut.model_validate(await task_to_dict(db, task))


@tasks_router.post(
    "/{task_id}/occurrences/{occurrence_id}/skip",
    response_model=MitigationTaskOut,
)
async def skip_task_occurrence(
    task_id: str,
    occurrence_id: str,
    body: OccurrenceCompleteRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MitigationTaskOut:
    task = await _load_task(db, task_id)
    occurrence = await _load_occurrence(db, task, occurrence_id)
    if occurrence.status != "open":
        raise HTTPException(409, f"Occurrence is already {occurrence.status}")

    await _ensure_can_terminate(db, user=user, occurrence=occurrence, require_full_manage=True)

    risk = await db.get(Risk, task.risk_id)
    if risk is None:
        raise HTTPException(404, "Parent risk not found")
    if risk.status == "closed":
        raise HTTPException(409, "Risk is closed and read-only. Reopen it first to update tasks.")

    notes = (body.notes if body else None) or None
    await skip_occurrence(
        db,
        risk=risk,
        task=task,
        occurrence=occurrence,
        actor_id=user.id,
        notes=notes,
    )
    await db.commit()
    await db.refresh(task)
    return MitigationTaskOut.model_validate(await task_to_dict(db, task))


__all__ = ["risks_router", "tasks_router"]
