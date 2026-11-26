"""Single-organization host backup worker. Repository paths and keys stay on the host."""
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from backup_files import require_checksum_entries, snapshot

CTL = Path(__file__).resolve().parents[1] / "platformctl"
TAG = "airalogy-managed"
PENDING = "airalogy-candidate"
MIB = 1024**2


class Failure(Exception):
    """Short code safe for the web dashboard."""


def run(args, **kwargs):
    return subprocess.run(args, text=True, check=True, stdout=subprocess.PIPE, **kwargs).stdout


def bridge(action, payload):
    return json.loads(run([CTL, "backup-bridge", action], input=json.dumps(payload)))


def load_config(path, *, require_staging=True):
    config = json.loads(path.read_text())
    targets = config["targets"]
    if not isinstance(targets, dict) or not 1 <= len(targets) <= 8:
        raise ValueError("Register between one and eight repositories")
    repos = set()
    for key, target in targets.items():
        if not re.fullmatch(r"[a-z0-9_-]{1,32}", key):
            raise ValueError("Invalid backup target identifier")
        if not isinstance(target["name"], str) or not 1 <= len(target["name"]) <= 80:
            raise ValueError("Invalid target display name")
        if not all(Path(target[k]).is_absolute() for k in ("repository", "password_file")):
            raise ValueError("Repository and password file must be absolute paths")
        repo_id = target["config_sha256"]
        if not re.fullmatch(r"[0-9a-f]{64}", repo_id) or repo_id in repos:
            raise ValueError("Each target needs a distinct registered restic config checksum")
        repos.add(repo_id)
    if not require_staging:
        return config
    staging = Path(config["staging"])
    if not staging.is_absolute() or not staging.is_dir():
        raise ValueError("Private staging directory is unavailable")
    if staging.stat().st_mode & 0o077:
        raise ValueError("Restrict the staging directory to the deployment operator (0700)")
    if not isinstance(config.get("reserve_mib", 256), int) or config.get("reserve_mib", 256) < 1:
        raise ValueError("A positive free-space reserve is required")
    if marker := config.get("staging_disk_id"):
        if (staging / ".airalogy-backup-disk").read_text().strip() != marker:
            raise ValueError("Unexpected staging disk identity")
    return config


def inspect_target(key, target, *, for_backup=True):
    item = {"id": key, "name": target["name"], "code": "disk_missing", "free": None, "total": None}
    try:
        repo = Path(target["repository"])
        if hashlib.sha256((repo / "config").read_bytes()).hexdigest() != target["config_sha256"]:
            return item
        password = Path(target["password_file"])
        if not password.is_file() or password.stat().st_mode & 0o077:
            item["code"] = "key_unavailable"
            return item
        space = shutil.disk_usage(repo)
        code = "ready"
        if for_backup and (not os.access(repo, os.W_OK) or os.statvfs(repo).f_flag & os.ST_RDONLY):
            code = "read_only"
        item.update(code=code, total=space.total, free=space.free)
    except (OSError, ValueError, KeyError):
        pass
    return item


def restic(target, *args, **kwargs):
    return run(["restic", "--repo", target["repository"], "--password-file",
                target["password_file"], *args], **kwargs)


def points(target, host):
    rows = json.loads(restic(target, "snapshots", "--json", "--host", host, "--tag", TAG))
    return sorted(({"id": row["id"], "time": row["time"]} for row in rows), key=lambda row: row["time"], reverse=True)


def verify_uploaded_point(target, candidate, source):
    # Stream the new point back before rotating older points. This uses no
    # second staging directory and does not pause the live application.
    expected = {}
    for path in source.iterdir():
        if path.is_file():
            with path.open("rb") as file:
                expected[path.name] = stream_hash(file)
    with (source / "objects.jsonl").open() as index:
        for line in index:
            name, digest = json.loads(line)
            expected["objects/" + name] = digest
    args = ["restic", "--repo", target["repository"], "--password-file", target["password_file"],
            "dump", "--archive", "tar", candidate, "/"]
    with subprocess.Popen(args, stdout=subprocess.PIPE) as child:
        try:
            with tarfile.open(fileobj=child.stdout, mode="r|") as tar:
                for member in tar:
                    if member.isdir():
                        continue
                    name = Path(member.name.lstrip("/")).as_posix()
                    if not member.isfile() or name not in expected:
                        raise Failure("backup_failed")
                    if stream_hash(tar.extractfile(member)) != expected.pop(name):
                        raise Failure("backup_failed")
            if child.wait() or expected:
                raise Failure("backup_failed")
        finally:
            child.stdout.close()
            if child.poll() is None:
                child.terminate()


def stream_hash(file):
    digest = hashlib.sha256()
    for chunk in iter(lambda: file.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def store_point(target, host, source, policy, reserve):
    repo = Path(target["repository"])
    code = inspect_target("target", target)["code"]
    if code != "ready":
        raise Failure(code)
    free = shutil.disk_usage(repo).free
    if free <= reserve:
        raise Failure("low_space")
    command = ["backup", "--json", "--host", host, "--tag", PENDING, "."]
    # Restic reuses previously uploaded blobs across snapshots, including files
    # with a different name. Capture directories are disposable.
    size = sum(path.stat().st_size for path in source.rglob("*") if path.is_file())
    if free < reserve + size * 1.05 + 16 * MIB:
        # Near capacity, measure actual new content so unchanged attachments
        # do not need their full size available again.
        preview = restic(target, *command[:-1], "--dry-run", ".", cwd=source)
        planned = json.loads(preview.splitlines()[-1])
        added = planned.get("data_added")
        if type(added) is not int or free < reserve + added * 1.05 + 16 * MIB:
            raise Failure("low_space")
    output = restic(target, *command, cwd=source)
    summary = json.loads(output.splitlines()[-1]) if output.strip() else {}
    candidate = summary.get("snapshot_id", "")
    if not isinstance(candidate, str) or not re.fullmatch(r"[0-9a-f]{8,64}", candidate):
        raise Failure("backup_failed")
    try:
        verify_uploaded_point(target, candidate, source)
    except Exception:
        restic(target, "forget", candidate)
        raise
    restic(target, "tag", "--add", TAG, "--remove", PENDING, candidate)
    retain = ["--keep-last", "1", "--keep-daily", str(policy["days"])]
    if policy["weeks"]:
        retain += ["--keep-weekly", str(policy["weeks"])]
    if policy["frequency"] == "hourly":
        retain += ["--keep-hourly", "24"]
    result = {"code": "ok", "success": int(time.time()), "added": summary.get("data_added", 0)}
    try:
        restic(target, "forget", "--host", host, "--tag", TAG, "--group-by", "host,tags",
               *retain, "--prune")
    except subprocess.CalledProcessError:
        result["code"] = "retention_failed"
    result["points"] = points(target, host)
    return result


def export_point(target, host, point_id, dest):
    if not re.fullmatch(r"[0-9a-f]{64}", point_id) or not any(p["id"] == point_id for p in points(target, host)):
        raise ValueError("Select a full snapshot ID from this deployment's verified recovery points")
    if dest.exists() or not dest.parent.is_dir():
        raise ValueError("Supply a new directory in an existing parent")
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        output = Path(tmp) / "point"
        restic(target, "restore", point_id, "--target", str(output), "--verify")
        require_checksum_entries(output)
        for line in (output / "SHA256SUMS").read_text().splitlines():
            digest, name = line.split("  ")
            with (output / name).open("rb") as file:
                if stream_hash(file) != digest:
                    raise ValueError("Exported file checksum mismatch")
        snapshot(output, verify=True)
        output.rename(dest)


@contextmanager
def capture_workspace(staging, host):
    # Reclaim only the directory created by this deployment's worker. A child
    # still mirroring objects inherits the lock if its parent is interrupted.
    root = staging / (".airalogy-capture-" + host)
    marker = root / "owner"
    try:
        root.mkdir(mode=0o700)
    except FileExistsError:
        if root.is_symlink() or marker.is_symlink() or marker.read_text() != host:
            raise ValueError("Unrecognized managed capture directory")
    else:
        marker.write_text(host)
    with (root / "capture.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        work = root / "active"
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(mode=0o700)
        try:
            yield work, lock.fileno()
        finally:
            shutil.rmtree(work)


def capture(config, host, policy, catalog):
    targets = config["targets"]
    reserve = config.get("reserve_mib", 256) * MIB
    results = {}
    active = []
    for key in policy["targets"]:
        item = next((row for row in catalog if row["id"] == key), {})
        code = item.get("code", "unknown_target")
        if code == "ready" and item["free"] > reserve:
            active.append(key)
        else:
            results[key] = {"code": "low_space" if code == "ready" else code}
    if active:
        staging = Path(config["staging"])
        try:
            with capture_workspace(staging, host) as (tmp, lock_fd):
                estimate = int(run([CTL, "backup-estimate"]).strip())
                if shutil.disk_usage(staging).free < estimate + reserve:
                    raise Failure("low_staging_space")
                env = {**os.environ, "BACKUP_DIR": str(tmp), "BACKUP_DISK_ID": "",
                       "BACKUP_RESERVE_MIB": str(config.get("reserve_mib", 256)), "AIRALOGY_CAPTURE_FORMAT": "2"}
                source = Path(run([CTL, "backup", "managed"], env=env, pass_fds=(lock_fd,)).strip())
                for key in active:
                    try:
                        results[key] = store_point(targets[key], host, source, policy, reserve)
                    except Failure as exc:
                        results[key] = {"code": str(exc)}
                    except (OSError, ValueError, subprocess.SubprocessError) as exc:
                        print(f"Backup target {key}: {exc}", file=sys.stderr)
                        results[key] = {"code": "backup_failed"}
        except (OSError, ValueError, subprocess.SubprocessError, Failure) as exc:
            print(f"Backup capture: {exc}", file=sys.stderr)
            for key in active:
                results.setdefault(key, {"code": str(exc) if isinstance(exc, Failure) else "capture_failed"})
    return {key: {**value, "time": int(time.time())} for key, value in results.items()}


def tick(state_dir, config, host, immediate=False):
    # The OS releases the lock on exit, including after an interrupted worker.
    with (state_dir / "backup-worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # During capture the API can be offline. The active worker reports
            # its result when the API has resumed.
            try:
                bridge("heartbeat", {})
            except subprocess.CalledProcessError:
                pass
            return
        if (state_dir / "backup-paused-api").exists():
            run([CTL, "backup-resume"])
        receipt = state_dir / "backup-receipt.json"
        if receipt.exists():
            bridge("finish", json.loads(receipt.read_text()))
            receipt.unlink()
        catalog = [inspect_target(key, target) for key, target in config["targets"].items()]
        now = datetime.now().astimezone()
        plan = bridge("claim", {"catalog": catalog, "now": immediate, "date": now.date().isoformat(), "hour": now.hour,
                                "utc_hour": now.astimezone(timezone.utc).strftime("%Y%m%d%H"), "timezone": now.tzname()})
        if not plan["targets"]:
            return
        # Treat the API's mailbox solely as a request for registered targets and
        # bounded retention. It never controls a host command, path or credential.
        if (not isinstance(plan["targets"], list) or not 1 <= len(plan["targets"]) <= 8
                or not all(isinstance(item, str) and re.fullmatch(r"[a-z0-9_-]{1,32}", item) for item in plan["targets"])
                or type(plan["days"]) is not int or not 1 <= plan["days"] <= 90
                or type(plan["weeks"]) is not int or not 0 <= plan["weeks"] <= 52
                or plan["frequency"] not in ("off", "daily", "hourly")):
            raise ValueError("Invalid backup policy")
        result = capture(config, host, plan, catalog)
        pending = receipt.with_suffix(".tmp")
        pending.write_text(json.dumps(result))
        pending.replace(receipt)
        bridge("finish", result)
        receipt.unlink()
        if any(item["code"] != "ok" for item in result.values()):
            raise Failure("Some backup targets need attention")


def main():
    os.umask(0o077)
    command, state_dir, host, config_path, *args = sys.argv[1:]
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,128}", host):
        raise ValueError("Missing or invalid deployment ID")
    config = load_config(Path(config_path), require_staging=command == "backup-tick")
    if command == "backup-tick" and args in ([], ["--now"]):
        path = Path(state_dir)
        path.mkdir(parents=True, exist_ok=True)
        tick(path, config, host, immediate=bool(args))
    elif command == "backup-drill" and len(args) == 2:
        target = config["targets"][args[0]]
        if inspect_target(args[0], target, for_backup=False)["code"] != "ready" or not any(
            item["id"] == args[1] for item in points(target, host)
        ):
            raise ValueError("Select an existing verified snapshot")
        bridge("drill", {"target": args[0], "snapshot": args[1]})
    elif command == "backup-export" and len(args) == 3:
        target = config["targets"][args[0]]
        if inspect_target(args[0], target, for_backup=False)["code"] != "ready":
            raise Failure("disk_missing")
        export_point(target, host, args[1], Path(args[2]).absolute())
    else:
        raise ValueError("Usage: backup-tick CONFIG or backup-export CONFIG TARGET FULL_SNAPSHOT_ID NEW_DIRECTORY or backup-drill CONFIG TARGET FULL_SNAPSHOT_ID")


if __name__ == "__main__":
    main()
