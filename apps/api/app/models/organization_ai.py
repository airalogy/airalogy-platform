from uuid import UUID

from sqlalchemy import JSON, ForeignKey, ForeignKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class OrganizationAIService(Base):
    __tablename__ = "organization_ai_services"
    json_exclude_fields = ["encrypted_key"]

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), primary_key=True
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str]
    provider: Mapped[str]
    base_url: Mapped[str]
    models: Mapped[list[str]] = mapped_column(JSON)
    encrypted_key: Mapped[str | None]


class OrganizationAI(Base):
    __tablename__ = "organization_ai"
    json_exclude_fields = ["encrypted_key"]

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool]
    model: Mapped[str]
    encrypted_key: Mapped[str | None]
    revision: Mapped[int]
    default_service_id: Mapped[UUID | None]
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "default_service_id"],
            ["organization_ai_services.organization_id", "organization_ai_services.id"],
            name="fk_ai_default_service",
        ),
    )
    service: Mapped[OrganizationAIService | None] = relationship(
        lazy="joined", viewonly=True
    )
