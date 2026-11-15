"""Revisioned manual R&D work. No Protocol, AI or execution Run is required."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.database import DBSession
from app.models.lab import Lab, LabUser
from app.models.project_work import ProjectWork
from app.models.research import ResearchEvent, ResearchTask
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.knowledge import canonical_digest
from app.services.project_work import (
    evidence_view,
    project_context,
    safe_evidence,
    validate_evidence,
    visible_snapshot,
    work_context,
    work_snapshot,
)
from app.services.project_work_contracts import (
    STORED_STATES,
    WorkActivity,
    WorkCreate,
    WorkState,
    WorkUpdate,
)
from app.services.research_runtime import (
    has_research_capability,
    require_research_capability,
)

router = APIRouter(prefix="/project-work", tags=["project-work"])


@router.get("/sources")
async def sources(
    current_user: CurrentUser,
    db_session: DBSession,
    project_id: UUID,
    kind: str = "document",
    q: str = Query(default="", max_length=255),
):
    from app.models.analysis import AnalysisRun
    from app.models.knowledge import ResearchFile
    from app.models.protocol import Protocol
    from app.models.record import Record
    from app.models.research_document import ResearchDocument
    from app.models.research_log import ResearchLogEntry

    project = await project_context(db_session, current_user, project_id)
    if kind == "document":
        from app.services.meetings import meeting_read_condition

        query = (
            select(ResearchLogEntry)
            .join(ResearchDocument, ResearchDocument.id == ResearchLogEntry.id)
            .where(
                ResearchLogEntry.project_id == project.id,
                meeting_read_condition(current_user.id),
                ResearchLogEntry.archived_at.is_(None),
                ResearchLogEntry.title.icontains(q, autoescape=True),
            )
            .order_by(ResearchLogEntry.updated_at.desc())
        )
    elif kind == "protocol":
        query = (
            select(Protocol)
            .where(
                Protocol.project_id == project.id,
                Protocol.deleted_at.is_(None),
                Protocol.name.icontains(q, autoescape=True),
            )
            .order_by(Protocol.updated_at.desc())
        )
    elif kind == "record":
        query = (
            select(Record)
            .join(Protocol, Protocol.id == Record.protocol_id)
            .where(
                Protocol.project_id == project.id,
                Record.deleted_at.is_(None),
                Protocol.name.icontains(q, autoescape=True),
            )
            .order_by(Record.created_at.desc(), Record.version.desc())
        )
    elif kind == "file":
        query = (
            select(ResearchFile)
            .where(
                ResearchFile.project_id == project.id,
                ResearchFile.archived_at.is_(None),
                ResearchFile.filename.icontains(q, autoescape=True),
            )
            .order_by(ResearchFile.created_at.desc())
        )
    elif kind == "analysis":
        query = (
            select(AnalysisRun)
            .where(AnalysisRun.project_id == project.id)
            .order_by(AnalysisRun.created_at.desc())
        )
    elif kind == "research_task":
        query = (
            select(ResearchTask)
            .where(
                ResearchTask.project_id == project.id,
                ResearchTask.archived_at.is_(None),
                ResearchTask.title.icontains(q, autoescape=True),
            )
            .order_by(ResearchTask.updated_at.desc())
        )
    else:
        raise HTTPException(422, "Unsupported evidence type")
    candidates = (await db_session.scalars(query.limit(100))).all()
    result = []
    for source in candidates:
        version = (
            str(source.revision)
            if kind == "document"
            else source.latest_version
            if kind == "protocol"
            else str(source.version)
            if kind == "record"
            else ""
        )
        try:
            result.append(
                await evidence_view(
                    db_session,
                    current_user,
                    project,
                    {"kind": kind, "id": str(source.id), "version": version},
                )
            )
        except HTTPException as error:
            if error.status_code not in {400, 403, 404, 422}:
                raise
    return {"items": result, "limited": len(candidates) == 100}


@router.get("/document-snapshot/{document_id}/{revision}")
async def document_snapshot(
    document_id: UUID,
    revision: int,
    project_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    from app.models.research_log import ResearchLogRevision

    project = await project_context(db_session, current_user, project_id)
    await evidence_view(
        db_session,
        current_user,
        project,
        {"kind": "document", "id": str(document_id), "version": str(revision)},
    )
    row = await db_session.scalar(
        select(ResearchLogRevision).where(
            ResearchLogRevision.log_entry_id == document_id,
            ResearchLogRevision.revision == revision,
        )
    )
    # Reuse document attachment authorization, including historical file grants.
    from app.models.research_log import ResearchLogEntry
    from app.routers.research_documents import _files

    entry = await db_session.get(ResearchLogEntry, document_id)
    await _files(
        db_session,
        current_user,
        entry,
        row.snapshot.get("document", {}).get("file_ids", []),
    )
    return {"snapshot": row.snapshot, "revision": revision}


@router.get("/protocol-snapshot/{protocol_id}/{version}")
async def protocol_snapshot(
    protocol_id: UUID,
    version: str,
    project_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    from app.models.protocol_version import ProtocolVersion

    project = await project_context(db_session, current_user, project_id)
    link = await evidence_view(
        db_session,
        current_user,
        project,
        {"kind": "protocol", "id": str(protocol_id), "version": version},
    )
    row = await db_session.scalar(
        select(ProtocolVersion).where(
            ProtocolVersion.protocol_id == protocol_id,
            ProtocolVersion.version == version,
        )
    )
    return {"snapshot": {"title": link["label"], "body": row.aimd}, "version": version}


async def validate_content(db, user, project, data, task_id):
    for identity in set(
        data.collaborator_ids
        + ([data.assignee_user_id] if data.assignee_user_id else [])
    ):
        member = await db.get(User, identity)
        if member is None or not await has_research_capability(
            db, user=member, project=project, capability="log.write"
        ):
            raise HTTPException(
                422,
                "Assignees and collaborators must have current Project write access",
            )
    await validate_evidence(db, user, project, data.evidence)
    rows = (
        await db.execute(
            select(ResearchTask, ProjectWork)
            .join(ProjectWork, ProjectWork.task_id == ResearchTask.id)
            .where(
                ResearchTask.project_id == project.id,
                ResearchTask.archived_at.is_(None),
            )
        )
    ).all()
    graph = {str(t.id): list(d.dependency_ids) for t, d in rows}
    states = {str(t.id): t.status for t, _ in rows}
    dependencies = [str(identity) for identity in data.dependency_ids]
    if any(identity not in graph for identity in dependencies):
        raise HTTPException(
            422, "Dependencies must be existing work items in this Project"
        )
    if data.state == "done" and any(
        states[identity] != "completed" for identity in dependencies
    ):
        raise HTTPException(
            409, "Complete dependencies before completing this work item"
        )
    if (
        data.state != "done"
        and states.get(str(task_id)) == "completed"
        and any(
            states[child] == "completed" and str(task_id) in parents
            for child, parents in graph.items()
        )
    ):
        raise HTTPException(
            409,
            "Reopen completed dependent work before reopening this prerequisite",
        )
    graph[str(task_id)] = dependencies
    visited, active = set(), set()

    def visit(identity):
        if identity in active:
            raise HTTPException(422, "Dependencies cannot form a cycle")
        if identity in visited:
            return
        active.add(identity)
        for parent in graph.get(identity, []):
            visit(parent)
        active.remove(identity)
        visited.add(identity)

    visit(str(task_id))


def apply_content(task, detail, data):
    previous = task.status
    task.title, task.goal = data.title, data.goal
    task.success_criteria = [data.acceptance] if data.acceptance else []
    task.status = STORED_STATES[data.state]
    task.updated_at = datetime.now(UTC)
    if data.state == "done" and previous != "completed":
        task.completed_at = datetime.now(UTC)
    elif data.state != "done":
        task.completed_at = None
    for key in (
        "kind",
        "priority",
        "assignee_user_id",
        "planned_start",
        "planned_end",
        "blocker",
        "next_step",
    ):
        setattr(detail, key, getattr(data, key))
    detail.collaborator_ids = [str(x) for x in data.collaborator_ids]
    detail.dependency_ids = [str(x) for x in data.dependency_ids]
    detail.evidence = [x.model_dump(mode="json") for x in data.evidence]


def event_key(user, request_id):
    return f"project-work:{user.id}:{request_id}"


async def replay(db, user, request_id, task_id, digest):
    event = await db.scalar(
        select(ResearchEvent).where(
            ResearchEvent.idempotency_key == event_key(user, request_id)
        )
    )
    if event:
        if event.task_id != task_id or event.payload.get("request_digest") != digest:
            raise HTTPException(409, "Request ID already used for different content")
        return True
    return False


async def append_event(db, user, task, kind, payload, request_id):
    event = ResearchEvent(
        id=uuid4(),
        task_id=task.id,
        kind=f"work.{kind}",
        actor_user_id=user.id,
        payload=payload,
        idempotency_key=event_key(user, request_id),
    )
    db.add(event)
    await db.flush()
    return event


@router.get("/members")
async def members(current_user: CurrentUser, db_session: DBSession, project_id: UUID):
    project = await project_context(db_session, current_user, project_id)
    candidates = (
        await db_session.scalars(
            select(User)
            .join(LabUser, LabUser.user_id == User.id)
            .where(LabUser.lab_id == project.lab_id)
            .order_by(User.name, User.id)
        )
    ).all()
    result = []
    for user in candidates:
        if await has_research_capability(
            db_session, user=user, project=project, capability="log.write"
        ):
            result.append(
                {"id": str(user.id), "name": user.name, "username": user.username}
            )
    return {"members": result}


@router.get("")
async def list_work(
    current_user: CurrentUser,
    db_session: DBSession,
    project_id: UUID | None = None,
    state: WorkState | None = None,
    mine: bool = False,
    active_only: bool = False,
    q: str = Query(default="", max_length=255),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=40, ge=1, le=100),
):
    project = (
        await project_context(db_session, current_user, project_id)
        if project_id
        else None
    )
    conditions = [ResearchTask.archived_at.is_(None)]
    if project:
        conditions.append(ResearchTask.project_id == project.id)
    else:
        # Home is only an assignment inbox, never a global asset search.
        mine = True
    if mine:
        conditions.append(ProjectWork.assignee_user_id == current_user.id)
    if active_only:
        conditions.append(ResearchTask.status.not_in(["completed", "cancelled"]))
    if state:
        conditions.append(ResearchTask.status == STORED_STATES[state])
    if q.strip():
        conditions.append(ResearchTask.title.icontains(q.strip(), autoescape=True))
    base_query = (
        select(ResearchTask, ProjectWork)
        .join(ProjectWork, ProjectWork.task_id == ResearchTask.id)
        .where(*conditions)
    )
    contexts = {project.id: project} if project else {}
    if not project:
        identities = (
            await db_session.scalars(
                select(ResearchTask.project_id)
                .join(ProjectWork, ProjectWork.task_id == ResearchTask.id)
                .where(*conditions)
                .distinct()
            )
        ).all()
        for identity in identities:
            try:
                contexts[identity] = await project_context(
                    db_session, current_user, identity
                )
            except HTTPException as error:
                if error.status_code not in {403, 404}:
                    raise
    base_query = base_query.where(ResearchTask.project_id.in_(contexts))
    total = await db_session.scalar(
        select(func.count()).select_from(base_query.subquery())
    )
    rows = (
        await db_session.execute(
            base_query.order_by(ResearchTask.updated_at.desc(), ResearchTask.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    result = []
    for task, detail in rows:
        context = contexts[task.project_id]
        lab = await db_session.get(Lab, context.lab_id)
        data = await visible_snapshot(
            db_session, current_user, context, work_snapshot(task, detail)
        )
        data.update(project_name=context.name, project_uid=context.uid, lab_uid=lab.uid)
        result.append(data)
    return {
        "items": result,
        "total": total,
        "page": page,
        "can_write": bool(
            project
            and await has_research_capability(
                db_session, user=current_user, project=project, capability="log.write"
            )
        ),
    }


@router.post("")
async def create_work(
    data: WorkCreate, current_user: CurrentUser, db_session: DBSession
):
    project = await project_context(
        db_session, current_user, data.project_id, write=True, lock=True
    )
    digest = canonical_digest(data.model_dump(mode="json"))
    existing = await db_session.get(ResearchTask, data.id)
    if existing:
        detail = await db_session.get(ProjectWork, data.id)
        if (
            not detail
            or existing.project_id != project.id
            or existing.created_by_user_id != current_user.id
            or detail.create_digest != digest
        ):
            raise HTTPException(409, "Work item ID is already in use")
        return await visible_snapshot(
            db_session, current_user, project, work_snapshot(existing, detail)
        )
    await validate_content(db_session, current_user, project, data, data.id)
    task = ResearchTask(
        id=data.id,
        lab_id=project.lab_id,
        project_id=project.id,
        title=data.title,
        goal=data.goal,
        owner_user_id=current_user.id,
        created_by_user_id=current_user.id,
        revision=1,
    )
    detail = ProjectWork(task_id=data.id, create_digest=digest)
    apply_content(task, detail, data)
    db_session.add(task)
    await db_session.flush()
    db_session.add(detail)
    await db_session.flush()
    snapshot = work_snapshot(task, detail)
    await append_event(
        db_session,
        current_user,
        task,
        "created",
        {"snapshot": snapshot, "request_digest": digest},
        data.id,
    )
    await db_session.commit()
    return await visible_snapshot(db_session, current_user, project, snapshot)


@router.get("/{task_id}")
async def get_work(task_id: UUID, current_user: CurrentUser, db_session: DBSession):
    task, detail, project = await work_context(db_session, current_user, task_id)
    result = await visible_snapshot(
        db_session, current_user, project, work_snapshot(task, detail)
    )
    result["can_write"] = await has_research_capability(
        db_session, user=current_user, project=project, capability="log.write"
    )
    result["can_approve"] = await has_research_capability(
        db_session, user=current_user, project=project, capability="research.approve"
    )
    return result


@router.put("/{task_id}")
async def update_work(
    task_id: UUID, data: WorkUpdate, current_user: CurrentUser, db_session: DBSession
):
    task, detail, project = await work_context(
        db_session, current_user, task_id, write=True
    )
    digest = canonical_digest(data.model_dump(mode="json"))
    if await replay(db_session, current_user, data.request_id, task_id, digest):
        return await visible_snapshot(
            db_session, current_user, project, work_snapshot(task, detail)
        )
    if task.revision != data.expected_revision:
        raise HTTPException(
            409,
            "Work changed in another window. Your edits were not saved; compare the current version before retrying.",
        )
    await validate_content(db_session, current_user, project, data, task_id)
    state_changed = task.status != STORED_STATES[data.state]
    apply_content(task, detail, data)
    task.revision += 1
    await db_session.flush()
    snapshot = work_snapshot(task, detail)
    await append_event(
        db_session,
        current_user,
        task,
        "updated",
        {
            "snapshot": snapshot,
            "reason": data.change_reason,
            "state_changed": state_changed,
            "request_digest": digest,
        },
        data.request_id,
    )
    await db_session.commit()
    return await visible_snapshot(db_session, current_user, project, snapshot)


@router.get("/{task_id}/activity")
async def activity(
    task_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    page: int = Query(default=1, ge=1),
):
    task, _, project = await work_context(db_session, current_user, task_id)
    conditions = [ResearchEvent.task_id == task.id, ResearchEvent.kind.like("work.%")]
    total = await db_session.scalar(
        select(func.count()).select_from(ResearchEvent).where(*conditions)
    )
    events = (
        await db_session.scalars(
            select(ResearchEvent)
            .where(*conditions)
            .order_by(ResearchEvent.created_at.desc(), ResearchEvent.id.desc())
            .offset((page - 1) * 30)
            .limit(30)
        )
    ).all()
    result = []
    for event in events:
        payload = dict(event.payload)
        payload.pop("request_digest", None)
        if "snapshot" in payload:
            payload["snapshot"] = await visible_snapshot(
                db_session, current_user, project, payload["snapshot"]
            )
        if "evidence" in payload:
            payload["evidence"] = await safe_evidence(
                db_session, current_user, project, payload["evidence"]
            )
        actor = (
            await db_session.get(User, event.actor_user_id)
            if event.actor_user_id
            else None
        )
        result.append(
            {
                "id": str(event.id),
                "kind": event.kind.removeprefix("work."),
                "actor": actor.name if actor else None,
                "created_at": event.created_at,
                "payload": payload,
            }
        )
    return {"events": result, "total": total}


@router.post("/{task_id}/activity")
async def add_activity(
    task_id: UUID, data: WorkActivity, current_user: CurrentUser, db_session: DBSession
):
    task, _detail, project = await work_context(
        db_session, current_user, task_id, write=True
    )
    digest = canonical_digest(data.model_dump(mode="json"))
    if await replay(db_session, current_user, data.request_id, task_id, digest):
        return {"revision": task.revision, "replayed": True}
    if task.revision != data.expected_revision:
        raise HTTPException(
            409, "Work changed. Reload the current version; your text is retained."
        )
    if data.kind == "acceptance" or data.outcome == "adopted":
        await require_research_capability(
            db_session,
            user=current_user,
            project=project,
            capability="research.approve",
        )
    await validate_evidence(db_session, current_user, project, data.evidence)
    if data.supersedes:
        old = await db_session.get(ResearchEvent, data.supersedes)
        if not old or old.task_id != task_id or old.kind != "work.decision":
            raise HTTPException(
                422, "Only a decision in this work item can be superseded"
            )
        if old.payload.get("outcome") == "adopted" and data.outcome != "adopted":
            raise HTTPException(
                422, "Replacing an adopted decision requires a new adopted decision"
            )
        superseding = await db_session.scalar(
            select(ResearchEvent.id).where(
                ResearchEvent.task_id == task_id,
                ResearchEvent.kind == "work.decision",
                ResearchEvent.payload["supersedes"].as_string() == str(data.supersedes),
            )
        )
        if superseding:
            raise HTTPException(409, "This decision has already been superseded")
    payload = data.model_dump(
        mode="json", exclude={"request_id", "expected_revision", "kind"}
    )
    payload.update(request_digest=digest, source_revision=task.revision)
    task.revision += 1
    task.updated_at = datetime.now(UTC)
    event = await append_event(
        db_session, current_user, task, data.kind, payload, data.request_id
    )
    await db_session.commit()
    return {"id": str(event.id), "revision": task.revision, "replayed": False}
