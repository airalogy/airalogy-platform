"""Read-only sharing surfaces. Workspace and Record permissions stay independent."""

from hashlib import sha256
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Literal
from urllib.parse import quote
from uuid import UUID
from zipfile import ZipFile

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from starlette.concurrency import run_in_threadpool

from app.config import config
from app.database import DBSession
from app.models.lab import Lab, LabUser
from app.models.project import Project
from app.models.protocol import Protocol, ProtocolKind
from app.models.protocol_version import ProtocolVersion
from app.models.workspace_publication import WorkspacePublication as Publication
from app.routers.depends import CurrentUser, OptionalCurrentUser
from app.routers.labs import require_lab_manager, require_lab_membership
from app.routers.permission import can_publish_workspace


def sharing_response(response: Response):
    if not config.is_single_organization:
        raise HTTPException(404, "Unavailable")
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"


router = APIRouter(
    prefix="/sharing", tags=["sharing"], dependencies=[Depends(sharing_response)]
)
Audience = Literal["organization", "public"]


class Toggle(BaseModel):
    enabled: bool


class Publish(BaseModel):
    audience: Audience
    preview: str
    materials: list[str] = Field(default_factory=list, max_length=20)


async def organization(db, org_id=None, *, lock=False):
    query = select(Lab).where(Lab.uid == config.SINGLE_LAB_UID)
    if org_id is not None:
        query = query.where(Lab.id == org_id)
    org = await db.scalar(query.with_for_update() if lock else query)
    if org is None:
        raise HTTPException(404, "Unavailable")
    return org


@router.get("/policy/{org_id}")
async def read_policy(org_id: UUID, db_session: DBSession, current_user: CurrentUser):
    org = await organization(db_session, org_id)
    await require_lab_manager(db_session, org.id, current_user.id)
    return {"enabled": org.external_publication_enabled}


@router.put("/policy/{org_id}")
async def change_policy(
    org_id: UUID, data: Toggle, db_session: DBSession, current_user: CurrentUser
):
    org = await organization(db_session, org_id, lock=True)
    await require_lab_manager(db_session, org.id, current_user.id)
    org.external_publication_enabled = data.enabled
    if not data.enabled:
        await db_session.execute(
            delete(Publication).where(
                Publication.audience == "public",
                Publication.project_id.in_(
                    select(Project.id).where(Project.lab_id == org.id)
                ),
            )
        )
    await db_session.commit()
    return {"enabled": data.enabled}


async def target(db, user, project_id, protocol_id, version, *, lock=False):
    org = await organization(db, lock=lock)
    await require_lab_membership(db, org.id, user.id)
    project = await Project.find_by(
        db,
        [
            Project.id == project_id,
            Project.lab_id == org.id,
            Project.deleted_at.is_(None),
        ],
    )
    if not project:
        raise HTTPException(404, "Unavailable")
    protocol = pv = None
    if protocol_id is not None:
        protocol = await Protocol.find_by(
            db,
            [
                Protocol.id == protocol_id,
                Protocol.project_id == project.id,
                Protocol.kind == ProtocolKind.EXPERIMENT,
                Protocol.deleted_at.is_(None),
            ],
        )
        if not protocol or not version:
            raise HTTPException(404, "Unavailable")
        pv = await ProtocolVersion.find_by(
            db,
            [
                ProtocolVersion.protocol_id == protocol.id,
                ProtocolVersion.version == version,
            ],
        )
        if not pv:
            raise HTTPException(404, "Unavailable")
    elif version is not None:
        raise HTTPException(422, "Select a protocol version")
    if not await can_publish_workspace(db, project, user, protocol):
        raise HTTPException(403, "Publication permission required")
    return org, project, protocol, pv


def draft(project, protocol, pv):
    title = ((pv.meta_data or {}).get("name") or protocol.name) if pv else project.name
    body = pv.aimd if pv else project.description
    body = body or ""
    fingerprint = sha256((title + "\0" + body).encode()).hexdigest()
    return {
        "title": title,
        "body": body,
        "version": pv.version if pv else None,
        "preview": fingerprint,
    }


def publication_query(project, pv):
    return select(Publication).where(
        Publication.project_id == project.id,
        Publication.version_id == (pv.id if pv else None),
    )


def link(row):
    return {
        "id": row.id,
        "audience": row.audience,
        "path": f"/shared/{row.id}",
        "materials": [m["name"] for m in row.materials],
    }


@router.put("/project/{project_id}/organization-reading")
async def change_reading(
    project_id: UUID, data: Toggle, db_session: DBSession, current_user: CurrentUser
):
    _, project, _, _ = await target(
        db_session, current_user, project_id, None, None, lock=True
    )
    project.organization_readable = data.enabled
    await db_session.commit()
    return {"enabled": data.enabled}


@router.get("/manage/{project_id}")
async def sharing_options(
    project_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    protocol_id: UUID | None = None,
    version: str | None = None,
):
    org, project, proto, pv = await target(
        db_session, current_user, project_id, protocol_id, version
    )
    rows = await db_session.scalars(publication_query(project, pv))
    versions = (
        []
        if not proto
        else list(
            await db_session.scalars(
                select(ProtocolVersion.version)
                .where(ProtocolVersion.protocol_id == proto.id)
                .order_by(ProtocolVersion.created_at.desc(), ProtocolVersion.id.desc())
            )
        )
    )
    return {
        **draft(project, proto, pv),
        "versions": versions,
        "public_enabled": org.external_publication_enabled,
        "links": [link(row) for row in rows],
    }


# Only participant-facing documents are offered; code, package manifests and raw Records
# are never implicitly attached. Each selected file is pinned to its content digest.
def material_data(path, prefix, names):
    with ZipFile(path) as archive:
        candidates = {}
        for item in archive.infolist():
            name = item.filename.removeprefix(prefix + "/")
            posix = PurePosixPath(name)
            if (
                item.is_dir()
                or posix.is_absolute()
                or name != str(posix)
                or any(part.startswith(".") for part in posix.parts)
                or "\\" in name
                or any(ord(c) < 32 for c in name)
                or posix.suffix.lower()
                not in {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".csv", ".txt"}
                or item.file_size > 16 * 1024 * 1024
            ):
                continue
            if name in candidates:
                raise HTTPException(422, "Duplicate package material")
            candidates[name] = item
        if names is None:
            return sorted(candidates)
        if len(set(names)) != len(names) or any(n not in candidates for n in names):
            raise HTTPException(422, "Unknown package material")
        if sum(candidates[n].file_size for n in names) > 32 * 1024 * 1024:
            raise HTTPException(422, "Selected materials are too large")
        return {name: archive.read(candidates[name]) for name in sorted(names)}


async def materials(pv, names=None):
    if not pv:
        raise HTTPException(422, "Select a protocol version")
    with TemporaryDirectory() as directory:
        path = Path(directory) / "package.zip"
        await pv.download_package(str(path))
        return await run_in_threadpool(material_data, path, pv.package_name, names)


@router.get("/manage/{project_id}/materials")
async def list_materials(
    project_id: UUID,
    protocol_id: UUID,
    version: str,
    db_session: DBSession,
    current_user: CurrentUser,
):
    _, _, _, pv = await target(
        db_session, current_user, project_id, protocol_id, version
    )
    return await materials(pv)


@router.post("/manage/{project_id}")
async def publish(
    project_id: UUID,
    data: Publish,
    db_session: DBSession,
    current_user: CurrentUser,
    protocol_id: UUID | None = None,
    version: str | None = None,
):
    org, project, proto, pv = await target(
        db_session, current_user, project_id, protocol_id, version, lock=True
    )
    if data.audience == "public" and not org.external_publication_enabled:
        raise HTTPException(403, "External publication disabled")
    if pv is None and data.audience != "public":
        raise HTTPException(422, "Use project organization visibility")
    content = draft(project, proto, pv)
    if content["preview"] != data.preview:
        raise HTTPException(409, "Refresh the publication preview")
    files = await materials(pv, data.materials) if data.materials else {}
    manifest = [
        {"name": name, "digest": sha256(value).hexdigest()}
        for name, value in files.items()
    ]
    old = await db_session.scalar(
        publication_query(project, pv).where(Publication.audience == data.audience)
    )
    if old:
        if (old.title, old.body, old.materials) != (
            content["title"],
            content["body"],
            manifest,
        ):
            raise HTTPException(
                409, "Withdraw the existing publication before replacing it"
            )
        return link(old)
    row = Publication(
        project_id=project.id,
        version_id=pv.id if pv else None,
        audience=data.audience,
        title=content["title"],
        body=content["body"],
        materials=manifest,
        publisher_id=current_user.id,
    )
    db_session.add(row)
    await db_session.flush()
    result = link(row)
    await db_session.commit()
    return result


@router.delete("/manage/{project_id}/{publication_id}", status_code=204)
async def withdraw(
    project_id: UUID,
    publication_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    protocol_id: UUID | None = None,
    version: str | None = None,
):
    _, project, _, pv = await target(
        db_session, current_user, project_id, protocol_id, version, lock=True
    )
    row = await db_session.scalar(
        publication_query(project, pv).where(Publication.id == publication_id)
    )
    if row:
        await db_session.delete(row)
    await db_session.commit()


async def readable(db, user, share_id):
    row = await db.get(Publication, share_id)
    if row:
        org = await organization(db)
        project = await Project.find_by(
            db,
            [
                Project.id == row.project_id,
                Project.lab_id == org.id,
                Project.deleted_at.is_(None),
            ],
        )
        allowed = (
            org.external_publication_enabled
            if row.audience == "public"
            else user
            and await LabUser.exists(
                db, [LabUser.user_id == user.id, LabUser.lab_id == org.id]
            )
        )
        if project and allowed:
            if row.version_id is None:
                return row, None
            pv = await db.get(ProtocolVersion, row.version_id)
            if pv and await Protocol.find_by(
                db,
                [
                    Protocol.id == pv.protocol_id,
                    Protocol.project_id == project.id,
                    Protocol.deleted_at.is_(None),
                ],
            ):
                return row, pv
    raise HTTPException(404, "Unavailable")


@router.get("/read/{publication_id}")
async def read_publication(
    publication_id: UUID, db_session: DBSession, current_user: OptionalCurrentUser
):
    row, pv = await readable(db_session, current_user, publication_id)
    children = []
    if pv is None:
        published = await db_session.execute(
            select(Publication, ProtocolVersion.version)
            .join(ProtocolVersion, ProtocolVersion.id == Publication.version_id)
            .join(Protocol, Protocol.id == ProtocolVersion.protocol_id)
            .where(
                Publication.project_id == row.project_id,
                Publication.audience == "public",
                Protocol.deleted_at.is_(None),
            )
            .order_by(Publication.title, ProtocolVersion.version)
        )
        children = [
            {"title": entry.title, "version": version, "path": f"/shared/{entry.id}"}
            for entry, version in published
        ]
    return {
        **link(row),
        "title": row.title,
        "body": row.body,
        "version": pv.version if pv else None,
        "protocols": children,
    }


@router.get("/read/{publication_id}/material")
async def read_material(
    publication_id: UUID,
    name: str,
    db_session: DBSession,
    current_user: OptionalCurrentUser,
):
    row, pv = await readable(db_session, current_user, publication_id)
    item = next((m for m in row.materials if m["name"] == name), None)
    if not item:
        raise HTTPException(404, "Unavailable")
    value = (await materials(pv, [name]))[name]
    if sha256(value).hexdigest() != item["digest"]:
        raise HTTPException(404, "Unavailable")
    return Response(
        value,
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "attachment; filename*=UTF-8''"
            + quote(PurePosixPath(name).name, safe=""),
        },
    )
