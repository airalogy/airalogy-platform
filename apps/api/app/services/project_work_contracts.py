"""Bounded, deterministic project coordination contracts (AI is optional)."""

from datetime import UTC, date, datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

WorkState = Literal[
    "pending", "in_progress", "blocked", "in_review", "done", "cancelled"
]
STORED_STATES = {
    "pending": "draft",
    "in_progress": "active",
    "blocked": "paused",
    "in_review": "review_required",
    "done": "completed",
    "cancelled": "cancelled",
}
PUBLIC_STATES = {value: key for key, value in STORED_STATES.items()}


class EvidenceLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal[
        "document",
        "protocol",
        "record",
        "file",
        "analysis",
        "research_task",
        "external",
    ]
    id: str = Field(min_length=1, max_length=2000)
    version: str = Field(default="", max_length=128)
    label: str = Field(default="", max_length=255)

    @model_validator(mode="after")
    def valid_reference(self):
        if self.kind == "external":
            url = urlsplit(self.id)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
            ):
                raise ValueError("Evidence URL must be HTTP(S), without credentials")
        else:
            UUID(self.id)
        if self.kind in {"document", "protocol", "record"} and not self.version:
            raise ValueError(
                "A document, Protocol or Record reference requires an exact version"
            )
        return self


class WorkContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=255)
    kind: Literal["requirement", "task", "bug", "milestone"] = "task"
    state: WorkState = "pending"
    goal: str = Field(default="", max_length=20000)
    acceptance: str = Field(default="", max_length=10000)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    assignee_user_id: UUID | None = None
    collaborator_ids: list[UUID] = Field(default_factory=list, max_length=50)
    assignee_person_id: UUID | None = None
    collaborator_person_ids: list[UUID] = Field(default_factory=list, max_length=50)
    deadline_note: str = Field(default="", max_length=1000)
    planned_start: date | None = None
    planned_end: date | None = None
    blocker: str = Field(default="", max_length=4000)
    next_step: str = Field(default="", max_length=4000)
    dependency_ids: list[UUID] = Field(default_factory=list, max_length=50)
    evidence: list[EvidenceLink] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def coherent(self):
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("Title is required")
        if (
            self.planned_start
            and self.planned_end
            and self.planned_start > self.planned_end
        ):
            raise ValueError("Planned end cannot precede planned start")
        if self.state == "blocked" and not self.blocker.strip():
            raise ValueError("Explain the blocker and what is needed next")
        if self.state == "done" and not self.acceptance.strip():
            raise ValueError("Record the acceptance conditions before completing work")
        if self.assignee_person_id and self.assignee_user_id:
            raise ValueError("Choose one responsible person or account")
        for key in ("collaborator_ids", "collaborator_person_ids", "dependency_ids"):
            if len(set(getattr(self, key))) != len(getattr(self, key)):
                raise ValueError(f"Duplicate {key}")
        return self


class WorkCreate(WorkContent):
    id: UUID
    project_id: UUID


class WorkUpdate(WorkContent):
    expected_revision: int = Field(ge=1)
    request_id: UUID
    change_reason: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def meaningful_change(self):
        if not self.change_reason.strip():
            raise ValueError("Explain the change")
        return self


class WorkStateChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: WorkState
    expected_revision: int = Field(ge=1)
    request_id: UUID
    change_reason: str = Field(min_length=1, max_length=4000)
    blocker: str | None = Field(default=None, max_length=4000)
    acceptance: str | None = Field(default=None, max_length=10000)

    @model_validator(mode="after")
    def relevant_fields(self):
        if not self.change_reason.strip():
            raise ValueError("Explain the change")
        if self.blocker is not None and self.state != "blocked":
            raise ValueError("Only a blocked move can change the blocker")
        if self.acceptance is not None and self.state != "done":
            raise ValueError("Only completion can supply acceptance conditions")
        return self


class WorkActivity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    expected_revision: int = Field(ge=1)
    kind: Literal["comment", "progress", "decision", "test", "acceptance"]
    body: str = Field(min_length=1, max_length=20000)
    occurred_at: datetime | None = None
    outcome: (
        Literal[
            "proposed",
            "adopted",
            "passed",
            "failed",
            "inconclusive",
            "accepted",
            "rejected",
        ]
        | None
    ) = None
    rationale: str = Field(default="", max_length=10000)
    scope: str = Field(default="", max_length=4000)
    supersedes: UUID | None = None
    evidence: list[EvidenceLink] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def coherent(self):
        self.body = self.body.strip()
        if not self.body:
            raise ValueError("Content is required")
        outcomes = {
            "decision": {"proposed", "adopted"},
            "test": {"passed", "failed", "inconclusive"},
            "acceptance": {"accepted", "rejected"},
        }
        if self.kind in outcomes:
            if self.outcome not in outcomes[self.kind]:
                raise ValueError("Select an explicit result for this activity")
            if not self.rationale.strip() or not self.evidence:
                raise ValueError(
                    "Decision, test and acceptance require reasoning and linked evidence"
                )
        elif self.outcome is not None:
            raise ValueError(
                "Comments/progress cannot declare an approval or test outcome"
            )
        if self.supersedes and self.kind != "decision":
            raise ValueError("Only a decision can supersede another decision")
        if self.occurred_at and self.occurred_at.tzinfo is None:
            raise ValueError("Actual occurrence time requires a timezone")
        if self.occurred_at and self.occurred_at > datetime.now(UTC) + timedelta(
            minutes=5
        ):
            raise ValueError("Actual occurrence time cannot be in the future")
        if self.kind in {"test", "acceptance"} and self.occurred_at is None:
            raise ValueError("Enter the actual test or acceptance time")
        return self
