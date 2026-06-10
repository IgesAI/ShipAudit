"""fail-closed refactor: rate cards, rejected rows, verdicts, provenance

Revision ID: 0002_fail_closed
Revises: 0001_initial
Create Date: 2026-06-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app import models  # noqa: F401
from app.core.database import Base

revision: str = "0002_fail_closed"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VERDICT_ENUM = sa.Enum(
    "PASS", "FAIL_MISSING_SOURCE", "DISCREPANCY", "REVIEW", "NO_CLAIM", name="auditverdict"
)
CONFIDENCE_ENUM = sa.Enum(
    "PROVEN", "STRONG", "CONFLICTED", "INSUFFICIENT", name="confidenceclass"
)
STANDARDIZATION_ENUM = sa.Enum(
    "STANDARDIZED", "INTERPOLATED", "UNKNOWN", "CONFLICT", name="standardizationstatus"
)

NEW_COLUMNS: dict[str, list[sa.Column]] = {
    "addresses": [
        sa.Column("dpv_confirmed", sa.Boolean(), nullable=True),
        sa.Column("standardization_status", STANDARDIZATION_ENUM, nullable=True),
        sa.Column("validator_results", sa.JSON(), nullable=True),
    ],
    "invoices": [
        sa.Column("billing_period", sa.String(40), nullable=True),
        sa.Column("source_file_hash", sa.String(64), nullable=True),
    ],
    "invoice_lines": [
        sa.Column("delivery_date", sa.Date(), nullable=True),
        sa.Column("charge_code", sa.String(80), nullable=True),
        sa.Column("origin_zip", sa.String(20), nullable=True),
        sa.Column("destination_zip", sa.String(20), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=True),
        sa.Column("suspicion_score", sa.Integer(), nullable=True),
        sa.Column("suspicion_detail", sa.JSON(), nullable=True),
    ],
    "shipments": [
        sa.Column("declared_residential_flag", sa.Boolean(), nullable=True),
    ],
    "rule_versions": [
        sa.Column("parsed_by", sa.String(120), nullable=True),
        sa.Column("approved_by", sa.String(120), nullable=True),
    ],
    "findings": [
        sa.Column("verdict", VERDICT_ENUM, nullable=True),
        sa.Column("confidence_class", CONFIDENCE_ENUM, nullable=True),
    ],
    "cases": [
        sa.Column("dispute_deadline", sa.Date(), nullable=True),
        sa.Column("evidence_document", sa.Text(), nullable=True),
    ],
}


def upgrade() -> None:
    bind = op.get_bind()
    # Creates any tables (rate_cards, rate_card_entries, rejected_rows) that do
    # not exist yet; no-op for existing tables.
    Base.metadata.create_all(bind=bind)

    inspector = sa.inspect(bind)
    for table, columns in NEW_COLUMNS.items():
        existing = {col["name"] for col in inspector.get_columns(table)}
        for column in columns:
            if column.name not in existing:
                if isinstance(column.type, sa.Enum):
                    column.type.create(bind, checkfirst=True)
                op.add_column(table, column)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table, columns in NEW_COLUMNS.items():
        existing = {col["name"] for col in inspector.get_columns(table)}
        for column in columns:
            if column.name in existing:
                op.drop_column(table, column.name)
    op.drop_table("rate_card_entries")
    op.drop_table("rate_cards")
    op.drop_table("rejected_rows")
