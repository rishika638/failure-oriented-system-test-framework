"""Create tenant-scoped incident and replay tables."""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "incidents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("scenario", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "fingerprint"),
    )
    op.create_index("ix_incidents_organization_id", "incidents", ["organization_id"])
    op.create_index("ix_incident_org_updated", "incidents", ["organization_id", "updated_at"])
    op.create_table(
        "captures",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("incident_id", sa.String(length=36), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("organization_id", sa.String(length=128), nullable=False),
        sa.Column("scenario", sa.String(length=32), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_captures_incident_id", "captures", ["incident_id"])
    op.create_index("ix_captures_organization_id", "captures", ["organization_id"])
    op.create_table(
        "replay_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("incident_id", sa.String(length=36), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("capture_id", sa.String(length=36), sa.ForeignKey("captures.id"), nullable=False),
        sa.Column("organization_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("original_artifact", sa.JSON(), nullable=False),
        sa.Column("replay_artifact", sa.JSON(), nullable=True),
        sa.Column("comparison", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "incident_id", "idempotency_key"),
    )
    op.create_index("ix_replay_jobs_incident_id", "replay_jobs", ["incident_id"])
    op.create_index("ix_replay_jobs_organization_id", "replay_jobs", ["organization_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.String(length=128), nullable=False),
        sa.Column("incident_id", sa.String(length=36), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_organization_id", "audit_events", ["organization_id"])
    op.create_index("ix_audit_events_incident_id", "audit_events", ["incident_id"])


def downgrade():
    op.drop_index("ix_audit_events_incident_id", table_name="audit_events")
    op.drop_index("ix_audit_events_organization_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_replay_jobs_organization_id", table_name="replay_jobs")
    op.drop_index("ix_replay_jobs_incident_id", table_name="replay_jobs")
    op.drop_table("replay_jobs")
    op.drop_index("ix_captures_organization_id", table_name="captures")
    op.drop_index("ix_captures_incident_id", table_name="captures")
    op.drop_table("captures")
    op.drop_index("ix_incident_org_updated", table_name="incidents")
    op.drop_index("ix_incidents_organization_id", table_name="incidents")
    op.drop_table("incidents")
