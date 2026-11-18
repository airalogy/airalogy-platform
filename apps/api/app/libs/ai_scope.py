"""Request-local organization capabilities; credentials are resolved only at dispatch."""

from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class OrganizationAIScope:
    organization_id: UUID
    enabled: bool
    model: str
    has_key: bool


active_ai_scope: ContextVar[OrganizationAIScope | None] = ContextVar(
    "organization_ai_scope", default=None
)
