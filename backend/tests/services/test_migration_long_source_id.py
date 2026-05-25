"""Regression test for GitHub issue #599.

Composite ``source_id`` values built by source adapters (subscriptions,
documents, relations, comments, …) regularly exceed 255 chars on real-
world snapshots. The staging + identity-map columns must accommodate
them without truncation.

Pre-fix this test failed with ``StringDataRightTruncationError`` on
both the ``staged_records`` insert and the ``migration_identity_map``
insert. Post-fix (TEXT columns) both succeed.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.migration import IdentityMap, Migration, StagedRecord

# 400 chars — well over the legacy 255-char cap. Shape mirrors the
# overflowing subscription id from issue #599:
# ``{fact_sheet_uuid}:{role_type}:{role_name}:{email}``.
_LONG_ID = (
    "74ccc25f-9672-4a65-a9b8-0a470caaf68f:RESPONSIBLE:"
    "Application Owner With An Unusually Verbose Title For This Particular "
    "Business Unit That Exceeds The Legacy Char Cap:"
    "business.owner.with.a.long.routing.address@some-long-customer-domain.example.com" + ("x" * 80)
)


@pytest.mark.asyncio
async def test_staged_record_accepts_long_source_id(db) -> None:
    assert len(_LONG_ID) > 255, "guard: composite id must exceed legacy width"

    migration = Migration(
        name="snapshot.xlsx",
        source_type="leanix",
        file_hash="a" * 64,
        status="parsed",
    )
    db.add(migration)
    await db.flush()

    staged = StagedRecord(
        migration_id=migration.id,
        source_type="leanix",
        entity_kind="subscription",
        source_id=_LONG_ID,
        parent_source_id=_LONG_ID,
        action="create",
    )
    db.add(staged)
    await db.flush()

    fetched = (
        await db.execute(select(StagedRecord).where(StagedRecord.id == staged.id))
    ).scalar_one()
    assert fetched.source_id == _LONG_ID
    assert fetched.parent_source_id == _LONG_ID


@pytest.mark.asyncio
async def test_identity_map_accepts_long_source_id(db) -> None:
    import uuid

    entry = IdentityMap(
        source_type="leanix",
        source_id=_LONG_ID,
        entity_kind="subscription",
        target_id=uuid.uuid4(),
    )
    db.add(entry)
    await db.flush()

    fetched = (await db.execute(select(IdentityMap).where(IdentityMap.id == entry.id))).scalar_one()
    assert fetched.source_id == _LONG_ID
