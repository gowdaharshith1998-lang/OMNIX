"""Initial cloud schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("tier", sa.String(16), nullable=False, server_default="smb"),
        sa.Column("region", sa.String(32), nullable=False, server_default="us-east-1"),
        sa.Column("cmk_key_arn", sa.String(512)),
        sa.Column("workos_org_id", sa.String(128)),
        sa.Column("storage_backend", sa.String(16), nullable=False, server_default="r2"),
        sa.Column("quota_monthly_runs", sa.Integer, nullable=False, server_default="5"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255)),
        sa.Column("role", sa.String(32), nullable=False, server_default="member"),
        sa.Column("workos_user_id", sa.String(128)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "email"),
    )

    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("source_language", sa.String(32)),
        sa.Column("target_language", sa.String(32)),
        sa.Column("github_installation_id", sa.BigInteger),
        sa.Column("github_repo", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "slug"),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id")),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("source_descriptor", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("workspace_path", sa.String(512)),
        sa.Column("artifacts_uri", sa.String(512)),
        sa.Column("sha256_manifest", sa.String(64)),
        sa.Column("bytes_total", sa.BigInteger),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_jobs_tenant_state", "jobs", ["tenant_id", "state"])
    op.create_index("ix_jobs_created_at", "jobs", ["created_at"])

    op.create_table(
        "job_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("seq", sa.BigInteger, nullable=False),
        sa.Column("gate", sa.String(64)),
        sa.Column("severity", sa.String(16), nullable=False, server_default="info"),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("payload", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_job_events_job_seq", "job_events", ["job_id", "seq"])

    op.create_table(
        "receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("receipt_kind", sa.String(64), nullable=False),
        sa.Column("payload_canonical", sa.LargeBinary, nullable=False),
        sa.Column("payload_json", sa.JSON, nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("signature", sa.LargeBinary, nullable=False),
        sa.Column("public_key", sa.LargeBinary, nullable=False),
        sa.Column("rekor_log_index", sa.BigInteger),
        sa.Column("rekor_inclusion_proof", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_receipts_job", "receipts", ["job_id"])

    op.create_table(
        "cutover_shifts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("unit_id", sa.String(128), nullable=False),
        sa.Column("previous_percentage", sa.Integer, nullable=False),
        sa.Column("target_percentage", sa.Integer, nullable=False),
        sa.Column("authorized_by", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("receipt_id", sa.String(36), sa.ForeignKey("receipts.id"), nullable=False),
        sa.Column("is_rollback", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_cutover_unit", "cutover_shifts", ["tenant_id", "unit_id"])


def downgrade() -> None:
    op.drop_index("ix_cutover_unit", table_name="cutover_shifts")
    op.drop_table("cutover_shifts")
    op.drop_index("ix_receipts_job", table_name="receipts")
    op.drop_table("receipts")
    op.drop_index("ix_job_events_job_seq", table_name="job_events")
    op.drop_table("job_events")
    op.drop_index("ix_jobs_created_at", table_name="jobs")
    op.drop_index("ix_jobs_tenant_state", table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("projects")
    op.drop_table("users")
    op.drop_table("tenants")
