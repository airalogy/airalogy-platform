from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


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
