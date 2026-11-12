"""Authorization and live aggregation: no cached private counters cross scopes."""

from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.models.project import Project
from app.models.protocol import Protocol
from app.models.protocol_rating import (
    ProtocolRating,
    ProtocolRatingRevision,
    ProtocolUse,
    ProtocolUseRecord,
)
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.research import ResearchAction, ResearchProtocolRun
from app.models.user import User
from app.routers.permission import check_user_permission
from app.services.access_control import resolve_structured_access
from app.services.protocol_rating_score import ALGORITHM, POLICY, recommendation


class RatingContext:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.permissions = {}
        self.memberships = {}
        self.contexts = {}
        self.receipts = {}

    async def context(self, protocol_id):
        if protocol_id not in self.contexts:
            protocol = await self.db.get(Protocol, protocol_id)
            project = (
                await self.db.get(Project, protocol.project_id) if protocol else None
            )
            if not protocol or protocol.deleted_at or not project or project.deleted_at:
                raise HTTPException(404, "Protocol not found")
            self.contexts[protocol_id] = (protocol, project)
        return self.contexts[protocol_id]

    async def allowed(self, user, protocol, project, record=None):
        key = (
            user.id if user else None,
            protocol.id,
            record.user_id if record else None,
        )
        if key not in self.permissions:
            try:
                await check_user_permission(
                    self.db,
                    project,
                    user,
                    "read_record" if record else "read_protocol",
                    protocol,
                    record,
                )
                self.permissions[key] = True
            except HTTPException:
                self.permissions[key] = False
        return self.permissions[key]

    async def member(self, user, protocol, project):
        if not user:
            return False
        key = (user.id, protocol.id)
        if key not in self.memberships:
            access = await resolve_structured_access(
                self.db, user.id, project.lab_id, project, protocol
            )
            self.memberships[key] = access.allows(
                "protocol.read"
            ) and await self.allowed(user, protocol, project)
        return self.memberships[key]

    async def version(self, protocol_id, version, user):
        protocol, project = await self.context(protocol_id)
        if not await self.allowed(user, protocol, project):
            raise HTTPException(404, "Protocol not found")
        result = await self.db.scalar(
            select(ProtocolVersion).where(
                ProtocolVersion.protocol_id == protocol_id,
                ProtocolVersion.version == version,
            )
        )
        if not result:
            raise HTTPException(404, "Protocol version not found")
        return protocol, project, result

    async def receipt(self, use):
        """Invalidate withdrawn, deleted, revoked or incompatible evidence on every read."""
        if use.id in self.receipts:
            return self.receipts[use.id]
        result = None
        version = await self.db.get(ProtocolVersion, use.protocol_version_id)
        try:
            protocol, project = await self.context(version.protocol_id)
        except HTTPException:
            self.receipts[use.id] = None
            return None
        actor = await self.db.get(User, use.user_id)
        links = list(
            (
                await self.db.scalars(
                    select(ProtocolUseRecord).where(ProtocolUseRecord.use_id == use.id)
                )
            ).all()
        )
        records = []
        valid = (
            use.active
            and bool(links)
            and actor is not None
            and await self.allowed(actor, protocol, project)
        )
        for link in links:
            record = await self.db.get(
                Record,
                (link.record_id, link.record_version),
                options=[
                    load_only(
                        Record.id,
                        Record.version,
                        Record.user_id,
                        Record.protocol_id,
                        Record.protocol_version,
                        Record.deleted_at,
                    )
                ],
            )
            latest = await self.db.scalar(
                select(Record)
                .options(load_only(Record.id, Record.version, Record.deleted_at))
                .where(Record.id == link.record_id)
                .order_by(Record.version.desc())
                .limit(1)
            )
            if (
                not record
                or record.deleted_at
                or not latest
                or latest.deleted_at
                or record.protocol_id != protocol.id
                or record.protocol_version != version.version
            ):
                valid = False
                break
            if not await self.allowed(actor, protocol, project, record):
                valid = False
                break
            records.append(record)
        if use.research_run_id:
            run = await self.db.get(ResearchProtocolRun, use.research_run_id)
            action = await self.db.get(ResearchAction, run.action_id) if run else None
            if (
                not action
                or action.status != "completed"
                or not run.record_id
                or run.record_id not in {r.id for r in records}
            ):
                valid = False
        if valid:
            result = (protocol, project, records)
        self.receipts[use.id] = result
        return result

    async def visible_use(self, use, user, *, public_only=False):
        evidence = await self.receipt(use)
        if not evidence:
            return False
        protocol, project, records = evidence
        public = (
            use.public
            and await self.allowed(None, protocol, project)
            and all([await self.allowed(None, protocol, project, r) for r in records])
        )
        if public_only:
            return public
        if public:
            return True
        if not user or not (
            user.id == use.user_id or await self.member(user, protocol, project)
        ):
            return False
        return all([await self.allowed(user, protocol, project, r) for r in records])


def is_author(actor, protocol, version):
    linked = {str(actor.id), actor.username, f"airalogy.id.user.{actor.username}"}
    identities = [
        entry.get("airalogy_user_id")
        for key in ("authors", "maintainers")
        for entry in (version.meta_data or {}).get(key, []) or []
        if isinstance(entry, dict)
    ]
    return actor.id == protocol.user_id or bool(linked.intersection(identities))


def fields(obj):
    if isinstance(obj, ProtocolRating):
        keys = ("score", "comment", "conditions", "public", "active", "use_id")
    else:
        keys = ("outcome", "is_real", "comment", "public", "active", "research_run_id")
    return {
        k: str(getattr(obj, k))
        if isinstance(getattr(obj, k), UUID)
        else getattr(obj, k)
        for k in keys
    }


async def audit(db, obj, user, *, extra=None):
    await db.flush()
    db.add(
        ProtocolRatingRevision(
            kind="rating" if isinstance(obj, ProtocolRating) else "use",
            object_id=obj.id,
            revision=obj.revision,
            actor_id=user.id,
            payload={
                **fields(obj),
                "algorithm": ALGORITHM,
                "policy": POLICY,
                **(extra or {}),
            },
        )
    )


async def summary(ctx, protocol_id, version, user, *, public_only=False):
    protocol, project, pv = await ctx.version(protocol_id, version, user)
    related = list(
        (
            await ctx.db.scalars(
                select(Protocol).where(
                    Protocol.deleted_at.is_(None),
                    Protocol.parent_protocol_id == protocol.id,
                    Protocol.parent_protocol_version == version,
                )
            )
        ).all()
    )
    direct_versions = [pv.id]
    child_ids = {p.id for p in related}
    child_versions = (
        list(
            (
                await ctx.db.scalars(
                    select(ProtocolVersion.id).where(
                        ProtocolVersion.protocol_id.in_(child_ids)
                    )
                )
            ).all()
        )
        if child_ids
        else []
    )
    uses = list(
        (
            await ctx.db.scalars(
                select(ProtocolUse).where(
                    ProtocolUse.protocol_version_id.in_(
                        direct_versions + child_versions
                    ),
                    ProtocolUse.active.is_(True),
                )
            )
        ).all()
    )
    visible = {
        u.id: u for u in uses if await ctx.visible_use(u, user, public_only=public_only)
    }
    actual = {
        key: u for key, u in visible.items() if u.is_real and u.outcome != "unknown"
    }
    direct = [u for u in actual.values() if u.protocol_version_id == pv.id]
    use_labs = Counter()
    adopted = set()
    reuse_labs = set()
    for u in actual.values():
        source, source_project, _ = await ctx.receipt(u)
        if source.id == protocol.id:
            use_labs[str(source_project.lab_id)] += 1
        elif (
            source.user_id != protocol.user_id
            and source_project.lab_id != project.lab_id
        ):
            adopted.add((str(source_project.lab_id), str(source.user_id)))
            reuse_labs.add(str(source_project.lab_id))
    ratings = list(
        (
            await ctx.db.scalars(
                select(ProtocolRating)
                .where(
                    ProtocolRating.protocol_version_id == pv.id,
                    ProtocolRating.active.is_(True),
                )
                .order_by(ProtocolRating.updated_at.desc())
            )
        ).all()
    )
    entries, eligible = [], []
    for r in ratings:
        actor = await ctx.db.get(User, r.user_id)
        if not actor or not await ctx.allowed(actor, protocol, project):
            continue
        public = r.public and await ctx.allowed(None, protocol, project)
        if r.use_id:
            use = visible.get(r.use_id)
            if not use:
                continue
            if public and not await ctx.visible_use(use, None, public_only=True):
                public = False
        if public_only and not public:
            continue
        if not public and not (
            user and (r.user_id == user.id or await ctx.member(user, protocol, project))
        ):
            continue
        kind = (
            "author"
            if is_author(actor, protocol, pv)
            else "use"
            if r.use_id in actual
            else "reading"
        )
        if kind == "use":
            _, evidence_project, _ = await ctx.receipt(actual[r.use_id])
            eligible.append(
                {
                    "score": r.score,
                    "user_id": str(r.user_id),
                    "lab_id": str(evidence_project.lab_id),
                }
            )
        entries.append(
            {
                "id": str(r.id),
                "score": r.score,
                "comment": r.comment,
                "conditions": r.conditions,
                "kind": kind,
                "public": public,
                "revision": r.revision,
                "author": actor.name or actor.username,
                "updated_at": r.updated_at.isoformat(),
                "mine": bool(user and r.user_id == user.id),
            }
        )
    metrics = recommendation(eligible, dict(use_labs), list(reuse_labs))
    # Raw Record counts are independently permission-filtered. They never become uses.
    rows = list(
        (
            await ctx.db.scalars(
                select(Record)
                .options(
                    load_only(
                        Record.id,
                        Record.version,
                        Record.user_id,
                        Record.protocol_version,
                        Record.deleted_at,
                    )
                )
                .where(Record.protocol_id == protocol.id)
                .distinct(Record.id)
                .order_by(Record.id, Record.version.desc())
            )
        ).all()
    )
    records = [
        r
        for r in rows
        if r.protocol_version == version
        and not r.deleted_at
        and await ctx.allowed(None if public_only else user, protocol, project, r)
    ]
    covered_ids = (
        set(
            (
                await ctx.db.scalars(
                    select(ProtocolUseRecord.record_id).where(
                        ProtocolUseRecord.use_id.in_([u.id for u in direct])
                    )
                )
            ).all()
        )
        if direct
        else set()
    )
    copies = 0
    for child in related:
        try:
            _, cp = await ctx.context(child.id)
            if await ctx.allowed(None, child, cp) or (
                not public_only and await ctx.member(user, child, cp)
            ):
                copies += 1
        except HTTPException:
            pass
    labs = set(use_labs) | reuse_labs | {r["lab_id"] for r in eligible}
    return {
        **metrics,
        "protocol_id": str(protocol.id),
        "version": version,
        "scope": "public" if public_only or user is None else "accessible",
        "generated_at": datetime.now(UTC).isoformat(),
        "window": "all_time_current_eligible_evidence",
        "records_count": len(records),
        "unclassified_records": sum(r.id not in covered_ids for r in records),
        "use_count": len(direct),
        "copies_count": copies,
        "effective_reuse_count": len(adopted),
        "lab_count": len(labs),
        "reviews": entries,
        "feedback": [
            {
                "id": str(u.id),
                "outcome": u.outcome,
                "comment": u.comment,
                "is_real": u.is_real,
                "revision": u.revision,
                "mine": bool(user and u.user_id == user.id),
            }
            for u in visible.values()
            if u.protocol_version_id == pv.id
        ],
        "versions": list(
            (
                await ctx.db.scalars(
                    select(ProtocolVersion.version)
                    .where(ProtocolVersion.protocol_id == protocol.id)
                    .order_by(ProtocolVersion.created_at.desc())
                )
            ).all()
        ),
        "technical_check": "not_assessed",
        "expert_review": "not_available",
    }


async def delete_lab_rating_data(db, lab_id):
    """Explicit Lab hard-deletion only; foreign review lineage fails closed."""
    from sqlalchemy import delete

    versions = (
        select(ProtocolVersion.id)
        .join(Protocol, Protocol.id == ProtocolVersion.protocol_id)
        .join(Project, Project.id == Protocol.project_id)
        .where(Project.lab_id == lab_id)
    )
    use_ids = select(ProtocolUse.id).where(
        ProtocolUse.protocol_version_id.in_(versions)
    )
    foreign = await db.scalar(
        select(ProtocolRating.id)
        .where(
            ProtocolRating.use_id.in_(use_ids),
            ProtocolRating.protocol_version_id.not_in(versions),
        )
        .limit(1)
    )
    if foreign:
        raise ValueError(
            "Lab deletion is blocked by Protocol ratings in another scope that reference its use evidence"
        )
    rating_ids = select(ProtocolRating.id).where(
        ProtocolRating.protocol_version_id.in_(versions)
    )
    await db.execute(
        delete(ProtocolRatingRevision).where(
            or_(
                and_(
                    ProtocolRatingRevision.kind == "rating",
                    ProtocolRatingRevision.object_id.in_(rating_ids),
                ),
                and_(
                    ProtocolRatingRevision.kind == "use",
                    ProtocolRatingRevision.object_id.in_(use_ids),
                ),
            )
        )
    )
    await db.execute(
        delete(ProtocolRating).where(ProtocolRating.protocol_version_id.in_(versions))
    )
    await db.execute(
        delete(ProtocolUseRecord).where(ProtocolUseRecord.use_id.in_(use_ids))
    )
    await db.execute(
        delete(ProtocolUse).where(ProtocolUse.protocol_version_id.in_(versions))
    )
