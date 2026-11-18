"""Prepare an editable meeting proposal from text provided in this conversation."""

import json
from datetime import date
from typing import Annotated
from uuid import UUID

from masterbrain.usage import UsageContext
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.libs.masterbrain import aira_structured_proposal

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ActionTitle = Annotated[Text, Field(max_length=255)]


class MeetingProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[Text, Field(max_length=512)]
    body: Annotated[Text, Field(max_length=40000)]
    occurred_on: date | None = None
    actions: list[ActionTitle] = Field(max_length=50)


class ConversationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: Annotated[Text, Field(max_length=16000)]
    reply: Annotated[Text, Field(max_length=1500)]


class DraftTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    history: list[ConversationTurn] = Field(default_factory=list, max_length=7)
    message: Annotated[Text, Field(max_length=16000)]
    previous: MeetingProposal | None = None


class DraftReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: Annotated[Text, Field(max_length=1500)]
    draft: MeetingProposal | None


async def draft_meeting(turn: DraftTurn, model: str, usage: UsageContext) -> DraftReply:
    prompt = (
        "You are Aira helping draft a NEW project meeting. Reply in the user's "
        "language. Return exactly one JSON object with message (a short reply) and "
        "draft (null to ask for missing meeting material, otherwise an object with "
        "title, body (formal Markdown minutes), occurred_on (explicit full ISO date "
        "or null), and actions (list of explicit task titles)). Use only the supplied "
        "conversation and draft; apply requested corrections. Distinguish plans, "
        "decisions and completed work. Preserve explicit names and relative deadlines. "
        "Never invent people, dates, assignments or decisions. Do not claim to have "
        "saved or executed anything. Omit editorial commentary from the minutes.\n"
        + json.dumps(
            turn.model_dump(mode="json", exclude={"project_id"}), ensure_ascii=False
        )
    )
    result = await aira_structured_proposal(
        prompt, model, usage_context=usage, max_response_bytes=240000
    )
    return DraftReply.model_validate(result)
