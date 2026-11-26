import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers import instance_backup
from app.services import backup_console as console


@pytest.fixture
def mailbox(tmp_path, monkeypatch):
    monkeypatch.setattr(console, "STATE_FILE", tmp_path / "private/state.sqlite3")
    return {"catalog": [{"id": "disk", "name": "Backup B"}], "hour": 2,
            "date": "2026-01-01", "utc_hour": "2026010102", "timezone": "UTC"}


def test_scheduler_persistent_slots_manual_retry_and_revision(mailbox):
    with console.state() as state:
        plan = console.claim(mailbox, state)
        assert plan == {"frequency": "daily", "hour": 2, "days": 7, "weeks": 4, "targets": ["disk"]}
        with pytest.raises(console.Conflict):
            console.queue(console.BackupRequest(), state)
        console.finish({"disk": {"code": "ok", "time": 100, "success": 100}}, state)
    with console.state() as state:
        assert not console.claim(mailbox, state)["targets"]
        console.set_policy(console.PolicyChange(revision=0, frequency="off", targets=["disk"]), state)
        with pytest.raises(console.Conflict):
            console.set_policy(console.PolicyChange(revision=0, targets=["disk"]), state)
        with pytest.raises(console.Conflict):
            console.queue(console.BackupRequest(target="unknown"), state)
        console.queue(console.BackupRequest(target="disk"), state)
    with console.state() as state:
        assert console.claim(mailbox, state)["targets"] == ["disk"]
        console.finish({"disk": {"code": "capture_failed", "time": 110}}, state)
        assert state["last_result"]["disk"]["success"] == 100
        assert not console.claim({**mailbox, "date": "2026-01-02"}, state)["targets"]
        state["heartbeat"] = time.time() - 181
        with pytest.raises(console.Conflict, match="offline"):
            console.queue(console.BackupRequest(), state)


def test_policy_rejects_removed_and_duplicate_targets(mailbox):
    with console.state() as state:
        console.claim(mailbox, state)
        for targets in ([], ["unknown"], ["disk", "disk"]):
            with pytest.raises(console.Conflict):
                console.set_policy(console.PolicyChange(revision=0, targets=targets), state)


def test_access_requires_single_org_operator_and_management(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    db = object()
    authorized = AsyncMock()
    monkeypatch.setattr(instance_backup, "require_single_lab_manager", authorized)
    from app.config import config

    monkeypatch.setattr(config, "DEPLOYMENT_MODE", "community")
    monkeypatch.setenv("BACKUP_OPERATOR_IDS", str(user.id))
    with pytest.raises(HTTPException) as blocked:
        asyncio.run(instance_backup.require_backup_operator(user, db))
    assert blocked.value.status_code == 404
    monkeypatch.setattr(config, "DEPLOYMENT_MODE", "single_organization")
    monkeypatch.setenv("BACKUP_OPERATOR_IDS", "")
    with pytest.raises(HTTPException) as blocked:
        asyncio.run(instance_backup.require_backup_operator(user, db))
    assert blocked.value.status_code == 403
    authorized.assert_not_awaited()
    monkeypatch.setenv("BACKUP_OPERATOR_IDS", str(user.id))
    authorized.side_effect = HTTPException(403)
    with pytest.raises(HTTPException):
        asyncio.run(instance_backup.require_backup_operator(user, db))
    authorized.side_effect = None
    asyncio.run(instance_backup.require_backup_operator(user, db))
    authorized.assert_awaited_with(db, user)
