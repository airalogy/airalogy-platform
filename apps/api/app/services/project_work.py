"""Member-only project coordination on the existing task/event identity."""

from copy import deepcopy
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from app.models.analysis import AnalysisRun
from app.models.knowledge import ResearchFile
from app.models.lab import Lab
from app.models.project import Project
from app.models.project_work import ProjectWork
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.research import ResearchTask
from app.models.research_document import ResearchDocument
from app.models.research_log import ResearchLogEntry, ResearchLogRevision
from app.routers.permission import check_user_permission
from app.services.browser_paths import project_browser_path
from app.services.knowledge import authorize_research_file
from app.services.project_work_contracts import PUBLIC_STATES, EvidenceLink
from app.services.record_analyses import authorize_snapshot
from app.services.research_runtime import require_research_capability


async def project_context(db, user, project_id, *, write=False, lock=False):
    query = select(Project).where(
        Project.id == project_id, Project.deleted_at.is_(None)
    )
    if lock:
        query = query.with_for_update()
    project = await db.scalar(query.execution_options(populate_existing=True))
    if project is None:
        raise HTTPException(404, "Project not found")
    await require_research_capability(
        db,
        user=user,
        project=project,
        capability="log.write" if write else "research.read",
    )
    return project


async def work_context(db, user, task_id, *, write=False):
    task = await db.get(ResearchTask, task_id)
    detail = await db.get(ProjectWork, task_id)
    if task is None or detail is None or task.archived_at:
        raise HTTPException(404, "Work item not found")
    project = await project_context(db, user, task.project_id, write=write, lock=write)
    if write:
        await db.refresh(task)
        await db.refresh(detail)
    return task, detail, project


async def evidence_view(db, user, project, raw):
    """Link only existing same-project assets; recheck source authorization on reads.

    No source bodies, credentials, or private preview tokens are copied into tasks.
    Personal/Lab assets must first be explicitly published into this Project.
    """
    link = EvidenceLink.model_validate(raw)
    if link.kind == "external":
        return {**link.model_dump(), "href": link.id, "available": True}
    identity = UUID(link.id)
    lab = await db.get(Lab, project.lab_id)
    base = project_browser_path(lab.uid, project.uid)
    label, href = link.label, ""
    if link.kind == "document":
        entry = await db.get(ResearchLogEntry, identity)
        doc = await db.get(ResearchDocument, identity)
        if not entry or not doc or entry.archived_at or entry.project_id != project.id:
            raise HTTPException(404, "Evidence is unavailable in this Project")
        from app.routers.research_documents import _context

        await _context(db, user, identity)
        revision = await db.scalar(
            select(ResearchLogRevision).where(
                ResearchLogRevision.log_entry_id == identity,
                ResearchLogRevision.revision == int(link.version),
            )
        )
        if not revision:
            raise HTTPException(422, "Document revision does not exist")
        label = label or revision.snapshot.get("title", entry.title)
        href = f"/research-documents/{identity}?revision={link.version}"
    elif link.kind in {"protocol", "record"}:
        if link.kind == "record":
            record = await db.get(Record, (identity, int(link.version)))
            if not record or record.deleted_at:
                raise HTTPException(404, "Record evidence unavailable")
            protocol = await db.get(Protocol, record.protocol_id)
        else:
            protocol = await db.get(Protocol, identity)
            record = None
        if not protocol or protocol.deleted_at or protocol.project_id != project.id:
            raise HTTPException(404, "Protocol evidence unavailable in this Project")
        await check_user_permission(
            db,
            project,
            user,
            "read_record" if record else "read_protocol",
            protocol=protocol,
            record=record,
        )
        if record:
            label = label or f"{protocol.name} · #{record.number}"
            href = f"{base}/protocols/{protocol.uid}/v{record.protocol_version}/record/{record.id}/v{record.version}"
        else:
            version = await db.scalar(
                select(ProtocolVersion.id).where(
                    ProtocolVersion.protocol_id == protocol.id,
                    ProtocolVersion.version == link.version,
                )
            )
            if not version:
                raise HTTPException(422, "Protocol version does not exist")
            label = label or protocol.name
            href = f"{base}/protocols/{protocol.uid}/protocol?version={link.version}"
    elif link.kind == "file":
        file = await db.get(ResearchFile, identity)
        if not file or file.project_id != project.id or file.archived_at:
            raise HTTPException(404, "File evidence unavailable")
        await authorize_research_file(db, user, file)
        label = label or file.filename
        href = f"{base}/materials"
    elif link.kind == "analysis":
        run = await db.get(AnalysisRun, identity)
        if not run or run.project_id != project.id:
            raise HTTPException(404, "Analysis evidence unavailable")
        await authorize_snapshot(db, run, user)
        label = label or str(run.id)
        href = f"{base}/analysis?runId={run.id}"
    elif link.kind == "research_task":
        task = await db.get(ResearchTask, identity)
        if not task or task.project_id != project.id or task.archived_at:
            raise HTTPException(404, "Research execution unavailable")
        label = label or task.title
        href = f"/research/tasks/{identity}"
        if await db.get(ProjectWork, identity):
            href = f"{base}/work?item={identity}"
    return {**link.model_dump(), "label": label, "href": href, "available": True}


async def validate_evidence(db, user, project, links):
    for link in links:
        try:
            await evidence_view(
                db,
                user,
                project,
                link.model_dump() if isinstance(link, EvidenceLink) else link,
            )
        except (ValueError, TypeError):
            raise HTTPException(
                422, "Evidence needs a valid identity and exact version"
            ) from None


async def safe_evidence(db, user, project, links):
    result = []
    for link in links:
        try:
            result.append(await evidence_view(db, user, project, link))
        except (HTTPException, ValueError, TypeError):
            # Do not return a now-private label, identifier or link.
            result.append({"kind": "unavailable", "available": False})
    return result


def work_snapshot(task, detail):
    return {
        "id": str(task.id),
        "project_id": str(task.project_id),
        "title": task.title,
        "goal": task.goal,
        "acceptance": "\n".join(task.success_criteria),
        "state": PUBLIC_STATES[task.status],
        "revision": task.revision,
        "created_by_user_id": str(task.created_by_user_id),
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "kind": detail.kind,
        "priority": detail.priority,
        "assignee_user_id": str(detail.assignee_user_id)
        if detail.assignee_user_id
        else None,
        "collaborator_ids": detail.collaborator_ids,
        "planned_start": detail.planned_start.isoformat()
        if detail.planned_start
        else None,
        "planned_end": detail.planned_end.isoformat() if detail.planned_end else None,
        "blocker": detail.blocker,
        "next_step": detail.next_step,
        "dependency_ids": detail.dependency_ids,
        "evidence": detail.evidence,
    }


async def visible_snapshot(db, user, project, snapshot):
    snapshot = deepcopy(snapshot)
    snapshot["evidence"] = await safe_evidence(
        db, user, project, snapshot.get("evidence", [])
    )
    return snapshot
