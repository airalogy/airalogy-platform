"""Daily coordination within one explicit project grant; no membership changes."""

from uuid import UUID

from fastapi import HTTPException
from pydantic import Field

from app.services.external_research_contracts import Strict
from app.services.meetings import MeetingContent
from app.services.project_people import PersonContent
from app.services.project_work_contracts import WorkContent, WorkUpdate


class Empty(Strict):
    pass


class Browse(Strict):
    q: str = Field(default="", max_length=200)
    page: int = Field(default=1, ge=1)


class Identity(Strict):
    id: UUID


class PersonDraft(PersonContent):
    id: UUID


class WorkDraft(WorkContent):
    id: UUID


class WorkEdit(WorkUpdate):
    id: UUID


class MeetingDraft(Strict):
    id: UUID
    content: MeetingContent


class MeetingEdit(MeetingDraft):
    expected_revision: int = Field(ge=1)


class Actions(Strict):
    meeting_id: UUID
    request_id: UUID
    expected_revision: int = Field(ge=1)
    actions: list[WorkDraft] = Field(default_factory=list, max_length=50)
    existing_work_ids: list[UUID] = Field(default_factory=list, max_length=50)


class MeetingAndActions(MeetingDraft):
    request_id: UUID
    actions: list[WorkDraft] = Field(default_factory=list, max_length=50)
    existing_work_ids: list[UUID] = Field(default_factory=list, max_length=50)


COLLABORATION_TOOLS = {
    "create_project_person": (
        "Create a reusable project name with a stable UUID; account association must use project administration.",
        PersonDraft,
        False,
    ),
    "list_projects": (
        "Read the single project explicitly authorized by this connection; never organization-wide discovery.",
        Empty,
        True,
    ),
    "list_project_people": (
        "List reusable project people and account links; names alone grant no access.",
        Empty,
        True,
    ),
    "list_meetings": (
        "Search meetings visible to this account in the authorized project.",
        Browse,
        True,
    ),
    "get_meeting": (
        "Read saved meeting content, revision and current linked work.",
        Identity,
        True,
    ),
    "create_meeting": (
        "Create minutes idempotently using a stable UUID. Do not invent dates or participants.",
        MeetingDraft,
        False,
    ),
    "update_meeting": (
        "Update minutes with expected_revision. Read first; audience/access changes must use the platform.",
        MeetingEdit,
        False,
    ),
    "create_meeting_with_actions": (
        "Atomically save minutes and explicit action rows. Reuse UUIDs on retries; never copy private minutes into project-visible tasks.",
        MeetingAndActions,
        False,
    ),
    "save_meeting_actions": (
        "Atomically create/link action rows with stable IDs and source revision; tasks are project-visible.",
        Actions,
        False,
    ),
    "list_project_work": (
        "Search work in the authorized project before creating duplicates.",
        Browse,
        True,
    ),
    "get_project_work": ("Read current task content and revision.", Identity, True),
    "create_project_work": (
        "Create a work item idempotently using a stable UUID, without a Protocol or AI run.",
        WorkDraft,
        False,
    ),
    "update_project_work": (
        "Update work with an exact revision, request ID and change reason.",
        WorkEdit,
        False,
    ),
}


async def tool_call(db, access, name, args):
    from app.config import config
    from app.models.lab import Lab
    from app.routers import meetings, project_work
    from app.services.browser_paths import project_browser_path
    from app.services.external_access import fail, scope
    from app.services.project_people import list_people
    from app.services.project_work import project_context, work_context

    readonly = COLLABORATION_TOOLS[name][2]
    scope(access, "collaboration:read" if readonly else "collaboration:write")
    project = await project_context(
        db, access.user, access.project.id, write=not readonly
    )
    lab = await db.get(Lab, project.lab_id)
    base = config.SITE_URL.rstrip("/") + project_browser_path(lab.uid, project.uid)
    if name == "list_projects":
        return {
            "items": [
                {
                    "id": str(project.id),
                    "uid": project.uid,
                    "name": project.name,
                    "url": base + "/overview",
                }
            ],
            "scope": "authorized_project_only",
        }
    if name == "create_project_person":
        if args.user_id:
            fail("associate_account_in_platform", 403)
        from app.services.project_people import PersonCreate, create_person

        result = await create_person(
            db, access.user, PersonCreate(project_id=project.id, **args.model_dump())
        )
        return {**result, "saved": True, "url": base + "/work"}
    if name == "list_project_people":
        return await list_people(db, access.user, project.id)
    if name == "list_meetings":
        result = await meetings.list_meetings(
            access.user,
            db,
            project.id,
            q=args.q,
            participant_id=None,
            status=None,
            date_from=None,
            date_to=None,
            time_zone="UTC",
            page=args.page,
            page_size=20,
        )
    elif name == "list_project_work":
        result = await project_work.list_work(
            access.user,
            db,
            project_id=project.id,
            state=None,
            mine=False,
            person_id=None,
            active_only=False,
            q=args.q,
            page=args.page,
            page_size=40,
        )
    else:
        identity = args.meeting_id if name == "save_meeting_actions" else args.id
        if name in {"get_meeting", "update_meeting", "save_meeting_actions"}:
            _, _, target = await meetings.context(db, access.user, identity)
            if target.id != project.id:
                fail("object_outside_authorized_project", 404)
        if name in {"get_project_work", "update_project_work"}:
            _, _, target = await work_context(db, access.user, identity)
            if target.id != project.id:
                fail("object_outside_authorized_project", 404)
        if name == "get_meeting":
            result = await meetings.get_meeting(identity, access.user, db)
        elif name == "get_project_work":
            result = await project_work.get_work(identity, access.user, db)
        elif name == "create_meeting":
            result = await meetings.create_meeting_impl(
                meetings.Create(
                    id=args.id, project_id=project.id, **args.content.model_dump()
                ),
                access.user,
                db,
            )
        elif name == "update_meeting":
            current = await meetings.get_meeting(identity, access.user, db)
            # Daily content scopes do not delegate access management.
            incoming = args.content.model_dump(mode="json")
            from fastapi.encoders import jsonable_encoder

            current = jsonable_encoder(current)
            if (
                incoming["visibility"] != current["visibility"]
                or incoming["access"] != current["access"]
            ):
                fail("manage_meeting_access_in_platform", 403)
            result = await meetings.update_meeting_impl(
                identity,
                meetings.Update(
                    expected_revision=args.expected_revision,
                    **args.content.model_dump(),
                ),
                access.user,
                db,
            )
        elif name == "create_meeting_with_actions":
            data = meetings.MeetingWithActions(
                meeting=meetings.Create(
                    id=args.id, project_id=project.id, **args.content.model_dump()
                ),
                actions=meetings.ActionBatch(
                    request_id=args.request_id,
                    expected_revision=1,
                    actions=[a.model_dump() for a in args.actions],
                    existing_work_ids=args.existing_work_ids,
                ),
            )
            result = await meetings.create_with_actions_impl(data, access.user, db)
        elif name == "save_meeting_actions":
            result = await meetings.action_batch_impl(
                identity,
                meetings.ActionBatch(**args.model_dump(exclude={"meeting_id"})),
                access.user,
                db,
            )
        elif name == "create_project_work":
            result = await project_work.create_work_impl(
                project_work.WorkCreate(project_id=project.id, **args.model_dump()),
                access.user,
                db,
            )
        elif name == "update_project_work":
            result = await project_work.update_work_impl(
                identity, WorkUpdate(**args.model_dump(exclude={"id"})), access.user, db
            )
        else:
            raise HTTPException(404, "Unknown collaboration tool")
    meeting_tool = "meeting" in name

    def attach(item):
        return {
            **item,
            "url": base
            + (
                f"/meetings?meeting={item['id']}"
                if meeting_tool
                else f"/work?item={item['id']}"
            ),
        }

    if "items" in result:
        return {**result, "items": [attach(item) for item in result["items"]]}
    return {**attach(result), "saved": not readonly, "project_id": str(project.id)}
