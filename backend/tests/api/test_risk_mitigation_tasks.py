"""Integration tests for the risk mitigation tasks API.

Covers the full task lifecycle including:

* Create / patch / delete on tasks.
* Per-occurrence complete + skip (one-shot vs. recurring rollover).
* The "assignee can complete their own occurrence without risks.manage" carve-out.
* System Todo lifecycle: created on task create, reassigned on owner change,
  closed on completion, recreated for the next recurring occurrence.
* Owner-at-time snapshot on the audit history when the owner is rotated mid-cycle.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.permissions import MEMBER_PERMISSIONS, VIEWER_PERMISSIONS
from app.models.risk import Risk
from app.models.risk_mitigation_task import (
    RiskMitigationTask,
    RiskMitigationTaskOccurrence,
)
from app.models.todo import Todo
from tests.conftest import auth_headers, create_role, create_user

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _make_risk(db, owner_id=None, title="A risk"):
    risk = Risk(
        id=uuid.uuid4(),
        reference="R-000001",
        title=title,
        description="",
        category="operational",
        source_type="manual",
        initial_probability="medium",
        initial_impact="medium",
        initial_level="medium",
        owner_id=owner_id,
        status="identified",
    )
    db.add(risk)
    await db.flush()
    return risk


@pytest.fixture
async def env(db):
    await create_role(db, key="admin", label="Admin", permissions={"*": True})
    await create_role(db, key="member", label="Member", permissions=MEMBER_PERMISSIONS)
    await create_role(db, key="viewer", label="Viewer", permissions=VIEWER_PERMISSIONS)
    admin = await create_user(db, email="admin@example.com", role="admin")
    member = await create_user(db, email="member@example.com", role="member")
    viewer = await create_user(db, email="viewer@example.com", role="viewer")
    risk = await _make_risk(db, owner_id=admin.id)
    return {
        "admin": admin,
        "member": member,
        "viewer": viewer,
        "risk": risk,
    }


def _api(risk):
    return f"/api/v1/risks/{risk.id}/mitigation-tasks"


# ---------------------------------------------------------------------------
# Create / list
# ---------------------------------------------------------------------------


async def test_create_one_shot_task_seeds_first_occurrence(client, db, env):
    risk = env["risk"]
    resp = await client.post(
        _api(risk),
        json={
            "title": "Apply MFA to all admins",
            "description": "Roll MFA out per finding 42",
            "owner_id": str(env["admin"].id),
            "due_date": "2026-06-30",
        },
        headers=auth_headers(env["admin"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Apply MFA to all admins"
    assert body["recurrence_unit"] == "none"
    assert body["recurrence_interval"] == 1
    assert body["is_active"] is True
    assert body["owner_id"] == str(env["admin"].id)
    assert len(body["occurrences"]) == 1
    occ = body["occurrences"][0]
    assert occ["sequence"] == 1
    assert occ["status"] == "open"
    assert occ["assigned_owner_id"] == str(env["admin"].id)
    assert occ["due_date"] == "2026-06-30"


async def test_create_recurring_task_persists_recurrence_rule(client, db, env):
    risk = env["risk"]
    resp = await client.post(
        _api(risk),
        json={
            "title": "Review access rights",
            "owner_id": str(env["member"].id),
            "due_date": "2026-06-01",
            "recurrence_unit": "months",
            "recurrence_interval": 6,
        },
        headers=auth_headers(env["admin"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["recurrence_unit"] == "months"
    assert body["recurrence_interval"] == 6
    assert len(body["occurrences"]) == 1


async def test_create_task_creates_system_todo_for_assignee(client, db, env):
    risk = env["risk"]
    resp = await client.post(
        _api(risk),
        json={
            "title": "Audit something",
            "owner_id": str(env["member"].id),
        },
        headers=auth_headers(env["admin"]),
    )
    assert resp.status_code == 200
    todos = (
        (
            await db.execute(
                select(Todo).where(Todo.is_system.is_(True), Todo.assigned_to == env["member"].id)
            )
        )
        .scalars()
        .all()
    )
    assert len(todos) == 1
    assert "[Risk R-000001]" in todos[0].description
    assert todos[0].status == "open"


async def test_list_mitigation_tasks_returns_full_history(client, db, env):
    risk = env["risk"]
    await client.post(
        _api(risk),
        json={"title": "First task", "owner_id": str(env["admin"].id)},
        headers=auth_headers(env["admin"]),
    )
    await client.post(
        _api(risk),
        json={"title": "Second task", "owner_id": str(env["admin"].id)},
        headers=auth_headers(env["admin"]),
    )
    resp = await client.get(_api(risk), headers=auth_headers(env["admin"]))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    titles = {t["title"] for t in data}
    assert titles == {"First task", "Second task"}


async def test_viewer_cannot_create_task(client, db, env):
    risk = env["risk"]
    resp = await client.post(
        _api(risk),
        json={"title": "No permission"},
        headers=auth_headers(env["viewer"]),
    )
    assert resp.status_code == 403


async def test_cannot_create_task_on_closed_risk(client, db, env):
    risk = env["risk"]
    risk.status = "closed"
    await db.flush()
    await db.commit()
    resp = await client.post(
        _api(risk),
        json={"title": "Blocked"},
        headers=auth_headers(env["admin"]),
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Complete + recurrence rollover
# ---------------------------------------------------------------------------


async def test_complete_one_shot_deactivates_task_and_closes_todo(client, db, env):
    risk = env["risk"]
    create = await client.post(
        _api(risk),
        json={"title": "One and done", "owner_id": str(env["admin"].id)},
        headers=auth_headers(env["admin"]),
    )
    task = create.json()
    occurrence = task["occurrences"][0]

    resp = await client.post(
        f"/api/v1/mitigation-tasks/{task['id']}/occurrences/{occurrence['id']}/complete",
        json={"notes": "Rolled out"},
        headers=auth_headers(env["admin"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_active"] is False
    assert len(body["occurrences"]) == 1
    closed_occ = body["occurrences"][0]
    assert closed_occ["status"] == "done"
    assert closed_occ["completion_notes"] == "Rolled out"
    assert closed_occ["completed_by"] == str(env["admin"].id)
    assert closed_occ["owner_at_completion"] == str(env["admin"].id)

    todos = (
        (
            await db.execute(
                select(Todo).where(Todo.is_system.is_(True), Todo.assigned_to == env["admin"].id)
            )
        )
        .scalars()
        .all()
    )
    assert len(todos) == 0


async def test_complete_recurring_rolls_next_occurrence_forward(client, db, env):
    risk = env["risk"]
    create = await client.post(
        _api(risk),
        json={
            "title": "Quarterly review",
            "owner_id": str(env["admin"].id),
            "due_date": "2026-01-15",
            "recurrence_unit": "months",
            "recurrence_interval": 3,
        },
        headers=auth_headers(env["admin"]),
    )
    task = create.json()
    first = task["occurrences"][0]

    resp = await client.post(
        f"/api/v1/mitigation-tasks/{task['id']}/occurrences/{first['id']}/complete",
        headers=auth_headers(env["admin"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    # Task stays active (recurring), now has 2 occurrences.
    assert body["is_active"] is True
    assert len(body["occurrences"]) == 2
    by_seq = sorted(body["occurrences"], key=lambda o: o["sequence"])
    assert by_seq[0]["status"] == "done"
    assert by_seq[1]["status"] == "open"
    # Next due date = Jan 15 + 3 months = Apr 15.
    assert by_seq[1]["due_date"] == "2026-04-15"
    # New occurrence is re-assigned to the current task owner.
    assert by_seq[1]["assigned_owner_id"] == str(env["admin"].id)

    # Fresh Todo on owner for the new cycle.
    todos = (
        (
            await db.execute(
                select(Todo).where(Todo.is_system.is_(True), Todo.assigned_to == env["admin"].id)
            )
        )
        .scalars()
        .all()
    )
    assert len(todos) == 1


async def test_complete_recurring_clamps_short_month_correctly(client, db, env):
    """Jan 31 + 1 month → Feb 28 (not March 3)."""
    risk = env["risk"]
    create = await client.post(
        _api(risk),
        json={
            "title": "Monthly review",
            "owner_id": str(env["admin"].id),
            "due_date": "2026-01-31",
            "recurrence_unit": "months",
            "recurrence_interval": 1,
        },
        headers=auth_headers(env["admin"]),
    )
    task = create.json()
    first = task["occurrences"][0]
    resp = await client.post(
        f"/api/v1/mitigation-tasks/{task['id']}/occurrences/{first['id']}/complete",
        headers=auth_headers(env["admin"]),
    )
    body = resp.json()
    new_occ = next(o for o in body["occurrences"] if o["status"] == "open")
    assert new_occ["due_date"] == "2026-02-28"


async def test_cannot_complete_twice(client, db, env):
    risk = env["risk"]
    create = await client.post(
        _api(risk),
        json={"title": "One shot", "owner_id": str(env["admin"].id)},
        headers=auth_headers(env["admin"]),
    )
    task = create.json()
    occ = task["occurrences"][0]
    first = await client.post(
        f"/api/v1/mitigation-tasks/{task['id']}/occurrences/{occ['id']}/complete",
        headers=auth_headers(env["admin"]),
    )
    assert first.status_code == 200
    second = await client.post(
        f"/api/v1/mitigation-tasks/{task['id']}/occurrences/{occ['id']}/complete",
        headers=auth_headers(env["admin"]),
    )
    assert second.status_code == 409


# ---------------------------------------------------------------------------
# Owner-can-complete-own carve-out
# ---------------------------------------------------------------------------


async def test_assignee_without_manage_can_complete_their_own_occurrence(client, db, env):
    """A viewer assigned to an occurrence can still close it without risks.manage."""
    risk = env["risk"]
    # Admin creates the task and assigns it to the viewer (read-only user).
    create = await client.post(
        _api(risk),
        json={
            "title": "Sign off control",
            "owner_id": str(env["viewer"].id),
        },
        headers=auth_headers(env["admin"]),
    )
    task = create.json()
    occ = task["occurrences"][0]

    resp = await client.post(
        f"/api/v1/mitigation-tasks/{task['id']}/occurrences/{occ['id']}/complete",
        headers=auth_headers(env["viewer"]),
    )
    assert resp.status_code == 200


async def test_other_users_cannot_complete_unassigned_occurrence(client, db, env):
    risk = env["risk"]
    create = await client.post(
        _api(risk),
        json={"title": "Not your task", "owner_id": str(env["admin"].id)},
        headers=auth_headers(env["admin"]),
    )
    task = create.json()
    occ = task["occurrences"][0]
    resp = await client.post(
        f"/api/v1/mitigation-tasks/{task['id']}/occurrences/{occ['id']}/complete",
        headers=auth_headers(env["viewer"]),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Owner rotation captures owner_at_completion separately from assignee
# ---------------------------------------------------------------------------


async def test_owner_change_mid_cycle_snapshots_both_owners_on_completion(client, db, env):
    risk = env["risk"]
    create = await client.post(
        _api(risk),
        json={"title": "Audit X", "owner_id": str(env["admin"].id)},
        headers=auth_headers(env["admin"]),
    )
    task = create.json()
    occ = task["occurrences"][0]
    # Admin originally assigned. Now rotate ownership to member.
    patch_resp = await client.patch(
        f"/api/v1/mitigation-tasks/{task['id']}",
        json={"owner_id": str(env["member"].id)},
        headers=auth_headers(env["admin"]),
    )
    assert patch_resp.status_code == 200
    # Member completes the open occurrence.
    resp = await client.post(
        f"/api/v1/mitigation-tasks/{task['id']}/occurrences/{occ['id']}/complete",
        headers=auth_headers(env["member"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    closed = body["occurrences"][0]
    # owner_at_completion is the current owner (member), not the original (admin).
    assert closed["owner_at_completion"] == str(env["member"].id)
    assert closed["completed_by"] == str(env["member"].id)
    # The system Todo follows the owner change.
    todos = (
        (
            await db.execute(
                select(Todo).where(Todo.is_system.is_(True), Todo.assigned_to == env["admin"].id)
            )
        )
        .scalars()
        .all()
    )
    assert todos == []


# ---------------------------------------------------------------------------
# Skip path
# ---------------------------------------------------------------------------


async def test_skip_requires_manage_permission(client, db, env):
    risk = env["risk"]
    create = await client.post(
        _api(risk),
        json={"title": "Skippable", "owner_id": str(env["viewer"].id)},
        headers=auth_headers(env["admin"]),
    )
    task = create.json()
    occ = task["occurrences"][0]
    # Viewer is the assignee but skip needs full risks.manage.
    resp = await client.post(
        f"/api/v1/mitigation-tasks/{task['id']}/occurrences/{occ['id']}/skip",
        headers=auth_headers(env["viewer"]),
    )
    assert resp.status_code == 403


async def test_skip_recurring_still_rolls_next_occurrence(client, db, env):
    risk = env["risk"]
    create = await client.post(
        _api(risk),
        json={
            "title": "Quarterly review",
            "owner_id": str(env["admin"].id),
            "due_date": "2026-01-15",
            "recurrence_unit": "months",
            "recurrence_interval": 3,
        },
        headers=auth_headers(env["admin"]),
    )
    task = create.json()
    occ = task["occurrences"][0]
    resp = await client.post(
        f"/api/v1/mitigation-tasks/{task['id']}/occurrences/{occ['id']}/skip",
        json={"notes": "Out of scope this quarter"},
        headers=auth_headers(env["admin"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    sequences = sorted(o["status"] for o in body["occurrences"])
    assert sequences == ["open", "skipped"]


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


async def test_delete_task_cascades_occurrences_and_removes_todo(client, db, env):
    risk = env["risk"]
    create = await client.post(
        _api(risk),
        json={"title": "Temporary", "owner_id": str(env["admin"].id)},
        headers=auth_headers(env["admin"]),
    )
    task_id = create.json()["id"]
    resp = await client.delete(
        f"/api/v1/mitigation-tasks/{task_id}",
        headers=auth_headers(env["admin"]),
    )
    assert resp.status_code == 200

    # Task row gone.
    remaining = (
        await db.execute(select(RiskMitigationTask).where(RiskMitigationTask.id == task_id))
    ).scalar_one_or_none()
    assert remaining is None
    # Occurrences cascade-deleted.
    occ_rows = (
        (
            await db.execute(
                select(RiskMitigationTaskOccurrence).where(
                    RiskMitigationTaskOccurrence.task_id == task_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert occ_rows == []
    # System Todo cleaned up.
    todos = (await db.execute(select(Todo).where(Todo.is_system.is_(True)))).scalars().all()
    assert todos == []


# ---------------------------------------------------------------------------
# Risk delete cascades to mitigation tasks
# ---------------------------------------------------------------------------


async def test_risk_delete_cascades_to_mitigation_tasks(client, db, env):
    risk = env["risk"]
    create = await client.post(
        _api(risk),
        json={"title": "Will be cascaded", "owner_id": str(env["admin"].id)},
        headers=auth_headers(env["admin"]),
    )
    task_id = create.json()["id"]
    resp = await client.delete(
        f"/api/v1/risks/{risk.id}",
        headers=auth_headers(env["admin"]),
    )
    assert resp.status_code == 200
    remaining = (
        await db.execute(select(RiskMitigationTask).where(RiskMitigationTask.id == task_id))
    ).scalar_one_or_none()
    assert remaining is None
