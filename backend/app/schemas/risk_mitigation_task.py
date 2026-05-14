"""Pydantic schemas for risk mitigation tasks + per-occurrence history."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

RecurrenceUnitLiteral = Literal["none", "days", "weeks", "months", "years"]
OccurrenceStatusLiteral = Literal["open", "done", "skipped"]


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


class MitigationTaskCreate(BaseModel):
    """Payload for ``POST /risks/{risk_id}/mitigation-tasks``."""

    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    owner_id: str | None = None
    due_date: date | None = None
    recurrence_unit: RecurrenceUnitLiteral = "none"
    recurrence_interval: int = Field(default=1, ge=1, le=365)


class MitigationTaskUpdate(BaseModel):
    """Partial update for ``PATCH /mitigation-tasks/{task_id}``.

    ``owner_id`` changes propagate to the **current open occurrence** (its
    ``assigned_owner_id``) so the Todo + notification flow reflects the
    new assignee immediately. Past completed occurrences keep their
    historical owner snapshots and are not modified.

    Recurrence changes apply to **future** occurrences only — the current
    open occurrence keeps its scheduled ``due_date``.
    """

    title: str | None = Field(default=None, max_length=500)
    description: str | None = None
    owner_id: str | None = None
    due_date: date | None = None
    recurrence_unit: RecurrenceUnitLiteral | None = None
    recurrence_interval: int | None = Field(default=None, ge=1, le=365)
    is_active: bool | None = None


class OccurrenceCompleteRequest(BaseModel):
    """Optional notes when marking an occurrence done or skipped."""

    notes: str | None = None


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


class MitigationTaskOccurrenceOut(BaseModel):
    id: str
    task_id: str
    sequence: int

    assigned_owner_id: str | None = None
    assigned_owner_name: str | None = None
    due_date: date | None = None

    status: OccurrenceStatusLiteral

    completed_at: datetime | None = None
    completed_by: str | None = None
    completed_by_name: str | None = None
    owner_at_completion: str | None = None
    owner_at_completion_name: str | None = None
    completion_notes: str | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None


class MitigationTaskOut(BaseModel):
    id: str
    risk_id: str

    title: str
    description: str | None = None

    owner_id: str | None = None
    owner_name: str | None = None

    recurrence_unit: RecurrenceUnitLiteral
    recurrence_interval: int
    is_active: bool

    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # Eagerly include the full occurrence history so the UI can render
    # the audit list in one round-trip. Volume is small (a handful per
    # task) so this stays cheap.
    occurrences: list[MitigationTaskOccurrenceOut] = Field(default_factory=list)
