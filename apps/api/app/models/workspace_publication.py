from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class WorkspacePublication(Base):
    """A reviewed project cover or an exact protocol version. Public IDs rotate on withdrawal."""

    __tablename__ = "workspace_publications"
    __table_args__ = (
        CheckConstraint(
            "audience IN ('organization','public') AND (version_id IS NOT NULL OR audience='public')",
            name="ck_publication_audience",
        ),
        Index(
            "uq_published_project",
            "project_id",
            unique=True,
            postgresql_where=text("version_id IS NULL"),
        ),
        Index("uq_published_version_audience", "version_id", "audience", unique=True),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("protocol_versions.id", ondelete="CASCADE")
    )
    audience: Mapped[str] = mapped_column()
    title: Mapped[str] = mapped_column()
    body: Mapped[str] = mapped_column(Text)
    materials: Mapped[list] = mapped_column(JSON)
    publisher_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
