from datetime import datetime
from enum import StrEnum
from typing import ClassVar
from uuid import UUID

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AccountTokenType(StrEnum):
    INVITATION = "invitation"
    PASSWORD_RESET = "password_reset"


class AccountToken(Base):
    """Single-use hashed tokens for invitations and account recovery."""

    __tablename__ = "account_tokens"

    id: Mapped[UUID] = mapped_column(
        nullable=False,
        primary_key=True,
        index=True,
        server_default=func.uuid_generate_v7(),
    )
    token_hash: Mapped[str] = mapped_column(
        nullable=False,
        unique=True,
        index=True,
    )
    token_type: Mapped[str] = mapped_column(nullable=False, index=True)
    email: Mapped[str] = mapped_column(nullable=False, default="", index=True)
    invitation_display_name: Mapped[str | None] = mapped_column(String(255))
    invitation_note: Mapped[str | None] = mapped_column(String(120))
    invitation_outcome: Mapped[str | None] = mapped_column(String(8))
    lab_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    lab_role: Mapped[int | None] = mapped_column(nullable=True)
    project_role: Mapped[int | None] = mapped_column(nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow
    )

    def claim_invitation(self, user_id: UUID, when: datetime) -> None:
        self.user_id = user_id
        self.consumed_at = when
        self.invitation_outcome = "claimed"

    def invitation_status(self, now: datetime) -> str:
        if self.consumed_at is not None:
            # Earlier versions used the same timestamp for acceptance and invalidation.
            return self.invitation_outcome or "closed"
        return "expired" if self.expires_at <= now else "pending"

    json_exclude_fields: ClassVar[list[str]] = [
        "token_hash",
        "invitation_display_name",
        "invitation_note",
    ]
