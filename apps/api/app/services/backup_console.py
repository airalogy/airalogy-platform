"""Host scheduler mailbox. Only the deployment CLI publishes disk/backup results."""
import json
import sqlite3
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

STATE_FILE = Path("log/backup-control/state.sqlite3")


class BackupPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    frequency: Literal["off", "daily", "hourly"] = "daily"
    hour: int = Field(default=2, ge=0, le=23)
    days: int = Field(default=7, ge=1, le=90)
    weeks: int = Field(default=4, ge=0, le=52)
    targets: list[str] = Field(default_factory=list, max_length=8)


class PolicyChange(BackupPolicy):
    revision: int = Field(ge=0)


class BackupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str | None = None


class Conflict(ValueError):
    pass


@contextmanager
def state():
    STATE_FILE.parent.mkdir(mode=0o700, exist_ok=True, parents=True)
    db = sqlite3.connect(STATE_FILE, timeout=5)
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS mailbox (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        row = db.execute("SELECT payload FROM mailbox WHERE id=1").fetchone()
        data = json.loads(row[0]) if row else {
            "policy": BackupPolicy().model_dump(), "revision": 0, "catalog": [],
            "heartbeat": 0, "timezone": "", "pending": None, "running": False,
            "last_slot": "", "last_result": {}, "last_drill": None,
        }
        yield data
        db.execute("INSERT OR REPLACE INTO mailbox VALUES (1, ?)", (json.dumps(data),))
        db.commit()
    finally:
        db.close()


def set_policy(change, data):
    if change.revision != data["revision"]:
        raise Conflict("stale_policy")
    available = {item["id"] for item in data["catalog"]}
    if not change.targets or not set(change.targets) <= available or len(set(change.targets)) != len(change.targets):
        raise Conflict("unknown_target")
    data["policy"] = change.model_dump(exclude={"revision"})
    data["revision"] += 1


def queue(request, data):
    if time.time() - data["heartbeat"] > 180:
        raise Conflict("worker_offline")
    if data["running"] or data["pending"]:
        raise Conflict("already_queued")
    targets = data["policy"]["targets"]
    selected = [request.target] if request.target else targets
    if not selected or not set(selected) <= {item["id"] for item in data["catalog"]}:
        raise Conflict("unknown_target")
    data["pending"] = selected


def claim(report, data):
    data.update(heartbeat=int(time.time()), timezone=report["timezone"], catalog=report["catalog"])
    policy = data["policy"]
    if not data["revision"] and not policy["targets"]:
        policy["targets"] = [report["catalog"][0]["id"]]
    # Only a host process holding the scheduler lock may claim. A running flag
    # here indicates previous process termination before its receipt was delivered.
    if data["running"]:
        for target in data["running"]:
            prior = data["last_result"].get(target, {})
            data["last_result"][target] = {**prior, "code": "interrupted", "time": data["heartbeat"]}
        data["running"] = False
    targets = data["pending"]
    if report.get("now"):
        targets = policy["targets"]
    if policy["frequency"] == "hourly":
        slot = "hour-" + report["utc_hour"]
    elif policy["frequency"] == "daily" and report["hour"] >= policy["hour"]:
        slot = "day-" + report["date"]
    else:
        slot = ""
    if slot and slot != data["last_slot"]:
        targets = list(dict.fromkeys((targets or []) + policy["targets"]))
        data["last_slot"] = slot
    data["pending"] = None
    data["running"] = targets or False
    return {**policy, "targets": targets or []}


def finish(report, data):
    for target, result in report.items():
        prior = data["last_result"].get(target, {})
        data["last_result"][target] = {**prior, **result}
    data.update(running=False, heartbeat=int(time.time()))


def main():
    action = sys.argv[1]
    payload = json.load(sys.stdin)
    with state() as data:
        if action == "heartbeat":
            data["heartbeat"] = int(time.time())
            reply = {}
        elif action == "claim":
            reply = claim(payload, data)
        elif action == "finish":
            finish(payload, data)
            reply = {}
        elif action == "drill":
            data["last_drill"] = {"time": int(time.time()), **payload}
            reply = {}
        else:
            raise ValueError("Unknown backup worker action")
    print(json.dumps(reply))


if __name__ == "__main__":
    main()
