import hashlib
import json
import os
import subprocess
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / "deploy/single-lab/scripts"
sys.path.insert(0, str(SCRIPTS))
import backup_files
import managed_backup as worker


class BackupRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.objects = self.source / "objects"
        self.objects.mkdir(parents=True)
        (self.objects / "attachment.bin").write_bytes(os.urandom(2 * 1024**2))
        (self.source / "database.dump").write_bytes(b"test database")
        (self.source / "manifest.env").write_text("BACKUP_FORMAT_VERSION=2\n")
        (self.source / "secrets.env").write_text("test-only")
        backup_files.snapshot(self.source, verify=False)
        self.write_checksums()
        self.policy = {"frequency": "daily", "days": 7, "weeks": 4, "targets": ["disk"]}
        self.target = {"name": "B", "repository": str(self.root / "repo"),
                       "password_file": str(self.root / "key"), "config_sha256": "f" * 64}
        self.config = {"targets": {"disk": self.target}, "staging": str(self.root / "stage")}
        Path(self.config["staging"]).mkdir(mode=0o700)

    def write_checksums(self):
        names = ("database.dump", "objects.jsonl", "manifest.env", "secrets.env")
        (self.source / "SHA256SUMS").write_text("".join(
            f"{hashlib.sha256((self.source / name).read_bytes()).hexdigest()}  {name}\n" for name in names
        ))

    def test_missing_disk_does_not_create_directory_or_capture(self):
        item = worker.inspect_target("disk", self.target)
        with patch.object(worker, "run", side_effect=AssertionError("no capture allowed")):
            result = worker.capture(self.config, "test-instance", self.policy, [item])
        self.assertEqual(result["disk"]["code"], "disk_missing")
        self.assertFalse(Path(self.target["repository"]).exists())

    def test_reject_low_space_before_capture(self):
        with patch.object(worker, "run", return_value=str(2**60)) as run:
            result = worker.capture(self.config, "test-instance", self.policy, [
                {"id": "disk", "code": "ready", "free": 2**40}])
        self.assertEqual(result["disk"]["code"], "low_staging_space")
        self.assertEqual(run.call_count, 1)

    def test_one_missing_target_does_not_prevent_other_target_from_completing(self):
        self.policy["targets"].append("other")
        catalog = [{"id": "disk", "code": "ready", "free": 2**40},
                   {"id": "other", "code": "disk_missing"}]
        with patch.object(worker, "run", side_effect=["0", str(self.source)]), \
                patch.object(worker, "store_point", return_value={"code": "ok"}) as save:
            result = worker.capture(self.config, "fixture", self.policy, catalog)
        self.assertEqual(save.call_count, 1)
        self.assertEqual(result["disk"]["code"], "ok")
        self.assertEqual(result["other"]["code"], "disk_missing")

    def test_abandoned_staging_is_reclaimed_without_touching_other_files(self):
        staging = Path(self.config["staging"])
        untouched = staging / "operator-file"
        untouched.write_text("keep")
        with worker.capture_workspace(staging, "fixture") as (work, _):
            with self.assertRaises(BlockingIOError):
                with worker.capture_workspace(staging, "fixture"):
                    self.fail("simultaneous capture")
        work.mkdir()
        (work / "interrupted.dump").touch()
        with worker.capture_workspace(staging, "fixture") as (new, _):
            self.assertEqual(list(new.iterdir()), [])
        self.assertTrue(untouched.is_file())

    def test_reject_missing_extra_and_changed_object(self):
        backup_files.snapshot(self.source, verify=True)
        for name in ["extra", "attachment.bin"]:
            path = self.objects / name
            path.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                backup_files.snapshot(self.source, verify=True)
            path.unlink()
        with self.assertRaises(ValueError):
            backup_files.snapshot(self.source, verify=True)

    @unittest.skipUnless(shutil.which("restic"), "restic is required for encrypted repository integration")
    def test_encrypted_dedup_export_and_failed_backup_preserves_points(self):
        key = Path(self.target["password_file"])
        key.write_text("isolated integration fixture only")
        key.chmod(0o600)
        cache = self.root / "cache"
        with patch.dict(os.environ, {"RESTIC_CACHE_DIR": str(cache)}):
            worker.restic(self.target, "init")
            config = Path(self.target["repository"]) / "config"
            self.target["config_sha256"] = hashlib.sha256(config.read_bytes()).hexdigest()
            self.assertEqual(worker.inspect_target("disk", self.target)["code"], "ready")
            a = worker.store_point(self.target, "fixture", self.source, self.policy, 0)
            (self.source / "database.dump").write_bytes(b"updated database")
            self.write_checksums()
            b = worker.store_point(self.target, "fixture", self.source, self.policy, 0)
            self.assertLess(b["added"], a["added"] // 4)
            new_id = b["points"][0]["id"]
            with self.assertRaises(worker.Failure):
                worker.store_point(self.target, "fixture", self.source, self.policy, 2**60)
            with patch.object(worker, "verify_uploaded_point", side_effect=worker.Failure("backup_failed")):
                with self.assertRaises(worker.Failure):
                    worker.store_point(self.target, "fixture", self.source, self.policy, 0)
            self.assertEqual(worker.points(self.target, "fixture"), b["points"])
            with self.assertRaises(ValueError):
                worker.export_point(self.target, "other-instance", new_id, self.root / "denied")
            restored = self.root / "restored"
            cfg = self.root / "targets.json"
            # An off-site export works even after loss of the original staging disk.
            cfg.write_text(json.dumps({"targets": self.config["targets"]}))
            env_file = self.root / "deployment.env"
            env_file.write_text(f"AIRALOGY_STATE_DIR={self.root}/state\nAIRALOGY_DEPLOYMENT_ID=fixture\n")
            subprocess.run([worker.CTL, "backup-export", cfg, "disk", new_id, restored],
                           env={**os.environ, "AIRALOGY_ENV_FILE": str(env_file)}, check=True)
            self.assertEqual((restored / "database.dump").read_bytes(), b"updated database")
            self.assertEqual((restored / "objects/attachment.bin").read_bytes(), (self.objects / "attachment.bin").read_bytes())


class LifecycleLockTests(unittest.TestCase):
    def test_owner_can_reenter_and_independent_process_is_excluded(self):
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp) / "maintenance.lock"
            script = Path(temp) / "nested.sh"
            script.write_text('set -eu\npython3 "$1" --inherited "$2"\n'
                              'if env -u PLATFORM_MAINTENANCE_FD python3 "$1" "$2" /dev/null; then exit 1; fi\n')
            helper = SCRIPTS / "operation_lock.py"
            subprocess.run([sys.executable, helper, lock, script, helper, lock], check=True)
            subprocess.run([sys.executable, helper, lock, "/dev/null"], check=True)

    def test_existing_registration_rejects_cleared_root_or_missing_disk(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "state").mkdir()
            data = base / "disk"
            data.mkdir()
            (base / "state/data-root").write_text(str(data))
            envfile = base / "deployment.env"
            envfile.write_text(f"AIRALOGY_STATE_DIR={base}/state\nAIRALOGY_DEPLOYMENT_ID=test\n")
            command = ["bash", "-c", 'source "$1"; storage_root_check', "test", SCRIPTS / "lib.sh"]
            env = {**os.environ, "AIRALOGY_ENV_FILE": str(envfile), "AIRALOGY_DATA_ROOT": ""}
            self.assertNotEqual(subprocess.run(command, env=env, capture_output=True).returncode, 0)
            env["AIRALOGY_DATA_ROOT"] = str(data)
            self.assertNotEqual(subprocess.run(command, env=env, capture_output=True).returncode, 0)
            (data / ".airalogy-instance").write_text("test\n")
            subprocess.run(command, env=env, check=True)
