"""Widen migration source-id columns from VARCHAR(255) to TEXT.

Migration 092 widened the (then ``leanix_id``) columns from 64 to 255
chars to cope with composite ids built by the LeanIX adapter. Migration
093 renamed the columns to ``source_id`` / ``parent_source_id`` as part
of the source-pluggable refactor but kept the 255-char cap. Real
snapshots still produce composite ids that exceed 255 chars on common
shapes:

- Subscriptions ``{fs_uuid}:{role_type}:{role_name}:{email}`` blow past
  255 the moment ``role_name`` is long or the email is on a verbose
  enterprise domain (see GitHub issue #599).
- Documents ``{fs_uuid}:{document_name}`` overflow on attachment titles
  with long descriptive filenames.
- Tag groups currently use the raw group ``name`` as the id when the
  source export omits a uuid — overflows on long group names.

Widening to TEXT is permissive and source-agnostic, so future Ardoq /
HOPEX / BiZZdesign adapters inherit the headroom without revisiting
this column shape. Postgres ``TEXT`` and ``VARCHAR`` have identical
performance characteristics and storage; the only practical difference
is the absence of the length constraint.

Revision ID: 095
Revises: 094
Create Date: 2026-05-25
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "095"
down_revision: Union[str, None] = "094"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "staged_records",
        "source_id",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "staged_records",
        "parent_source_id",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "migration_identity_map",
        "source_id",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Truncation guard mirrors 092's pattern: any row that landed during
    # the TEXT window may legitimately exceed 255, so substring-on-cast
    # so the migration succeeds. Information loss for over-long rows is
    # accepted because they could not have existed pre-upgrade anyway.
    op.alter_column(
        "migration_identity_map",
        "source_id",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=False,
        postgresql_using="substring(source_id, 1, 255)",
    )
    op.alter_column(
        "staged_records",
        "parent_source_id",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=True,
        postgresql_using="substring(parent_source_id, 1, 255)",
    )
    op.alter_column(
        "staged_records",
        "source_id",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=False,
        postgresql_using="substring(source_id, 1, 255)",
    )
