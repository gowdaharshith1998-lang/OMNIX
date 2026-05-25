"""SQLAlchemy 2.0 ORM models for the cloud orchestrator.

Multi-tenant scheme:
  - tier="smb"      shared schema, row-level security on tenant_id
  - tier="banking"  database-per-tenant; tenant_id retained for join coherence

Receipts are append-only. The `created_at` is the signing instant; updates are forbidden
at the ORM layer (no `updated_at`, no setters in code paths). DB-side trigger optional.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class TenantTier(str, enum.Enum):
    SMB = "smb"
    TEAM = "team"
    BANKING = "banking"


class JobState(str, enum.Enum):
    QUEUED = "queued"
    INGESTING = "ingesting"
    PARSING = "parsing"
    SPEC_MINING = "spec_mining"
    GENERATING = "generating"
    VERIFYING = "verifying"
    AWAITING_CUTOVER = "awaiting_cutover"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IngestionMode(str, enum.Enum):
    TUS_UPLOAD = "tus_upload"
    GIT_CLONE = "git_clone"
    LIVE_OBSERVE = "live_observe"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    tier: Mapped[TenantTier] = mapped_column(
        Enum(TenantTier, name="tenant_tier", values_callable=lambda e: [m.value for m in e]),
        default=TenantTier.SMB,
        nullable=False,
    )
    region: Mapped[str] = mapped_column(String(32), default="us-east-1", nullable=False)
    cmk_key_arn: Mapped[str | None] = mapped_column(String(512), nullable=True)
    workos_org_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    storage_backend: Mapped[str] = mapped_column(String(16), default="r2", nullable=False)
    quota_monthly_runs: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    users: Mapped[list["User"]] = relationship(back_populates="tenant")
    projects: Mapped[list["Project"]] = relationship(back_populates="tenant")
    jobs: Mapped[list["Job"]] = relationship(back_populates="tenant")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="member", nullable=False)
    workos_user_id: Mapped[str | None] = mapped_column(String(128))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    tenant: Mapped[Tenant] = relationship(back_populates="users")


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("tenant_id", "slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_language: Mapped[str | None] = mapped_column(String(32))
    target_language: Mapped[str | None] = mapped_column(String(32))
    github_installation_id: Mapped[int | None] = mapped_column(BigInteger)
    github_repo: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    tenant: Mapped[Tenant] = relationship(back_populates="projects")
    jobs: Mapped[list["Job"]] = relationship(back_populates="project")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_tenant_state", "tenant_id", "state"),
        Index("ix_jobs_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    mode: Mapped[IngestionMode] = mapped_column(
        Enum(
            IngestionMode,
            name="ingestion_mode",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    state: Mapped[JobState] = mapped_column(
        Enum(JobState, name="job_state", values_callable=lambda e: [m.value for m in e]),
        default=JobState.QUEUED,
        nullable=False,
    )
    source_descriptor: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    workspace_path: Mapped[str | None] = mapped_column(String(512))
    artifacts_uri: Mapped[str | None] = mapped_column(String(512))
    sha256_manifest: Mapped[str | None] = mapped_column(String(64))
    bytes_total: Mapped[int | None] = mapped_column(BigInteger)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    tenant: Mapped[Tenant] = relationship(back_populates="jobs")
    project: Mapped[Project | None] = relationship(back_populates="jobs")
    events: Mapped[list["JobEvent"]] = relationship(back_populates="job")
    receipts: Mapped[list["Receipt"]] = relationship(back_populates="job")


class JobEvent(Base):
    __tablename__ = "job_events"
    __table_args__ = (Index("ix_job_events_job_seq", "job_id", "seq"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    gate: Mapped[str | None] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16), default="info", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    job: Mapped[Job] = relationship(back_populates="events")


class Receipt(Base):
    """Append-only signed receipt. ML-DSA-65 (FIPS 204).

    INVARIANT: Receipts are never updated after creation. The ORM exposes no
    mutators; callers should treat instances as frozen. R1, R3.
    """

    __tablename__ = "receipts"
    __table_args__ = (Index("ix_receipts_job", "job_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    receipt_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_canonical: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    signature: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    public_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    rekor_log_index: Mapped[int | None] = mapped_column(BigInteger)
    rekor_inclusion_proof: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    job: Mapped[Job] = relationship(back_populates="receipts")


class CutoverShift(Base):
    """Receipt-gated traffic-shift authorization (Layer 6, strangler fig)."""

    __tablename__ = "cutover_shifts"
    __table_args__ = (
        Index("ix_cutover_unit", "tenant_id", "unit_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    unit_id: Mapped[str] = mapped_column(String(128), nullable=False)
    previous_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    target_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    authorized_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    receipt_id: Mapped[str] = mapped_column(ForeignKey("receipts.id"), nullable=False)
    is_rollback: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
