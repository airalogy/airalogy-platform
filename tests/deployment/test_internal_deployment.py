import importlib.util
import io
import json
import tarfile
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "internal",
    Path(__file__).resolve().parents[2] / "deploy/internal/platform-internal.py",
)
internal = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(internal)


class InternalDeploymentTests(unittest.TestCase):
    def test_same_schema_fast_path_rejects_changed_migration_bytes(self):
        with (
            patch.object(internal, "run"),
            patch.object(
                internal,
                "output",
                return_value="apps/api/migrations/versions/0086_project_work.py",
            ),
        ):
            with self.assertRaisesRegex(ValueError, "separate migration"):
                internal.assert_fast_path("a" * 40, "b" * 40)
        with self.assertRaisesRegex(ValueError, "full deployed"):
            internal.assert_fast_path("main", "b" * 40)

    def test_reviewed_migration_requires_exact_plan_and_extra_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = {
                "base_commit": "a" * 40,
                "target_commit": "b" * 40,
                "source_revision": "0086_project_work",
                "target_revision": "0087_project_meetings",
                "changed_paths": [
                    "apps/api/migrations/versions/0087_project_meetings.py"
                ],
                "backup_plan": "Independent encrypted backup and restored database",
                "migration_validation": "Restore source then migrate exact artifacts",
                "rollback_policy": "Old application allowed only before meeting writes",
                "write_impact": "Never restore over post-cutover writes",
            }
            path = root / "plan.json"
            path.write_text(json.dumps(plan))
            outputs = [
                plan["changed_paths"][0],
                "A\t" + plan["changed_paths"][0],
                plan["target_revision"],
            ]
            with (
                patch.object(internal, "run"),
                patch.object(internal, "output", side_effect=outputs),
            ):
                self.assertEqual(
                    internal.assert_fast_path("a" * 40, "b" * 40, path), plan
                )
            plan["target_commit"] = "c" * 40
            path.write_text(json.dumps(plan))
            with (
                patch.object(internal, "run"),
                patch.object(internal, "output", return_value=outputs[0]),
            ):
                with self.assertRaisesRegex(ValueError, "exact deployed"):
                    internal.assert_fast_path("a" * 40, "b" * 40, path)
            plan["target_commit"] = "b" * 40
            path.write_text(json.dumps(plan))
            with (
                patch.object(internal, "run"),
                patch.object(
                    internal,
                    "output",
                    side_effect=[outputs[0], "M\t" + plan["changed_paths"][0]],
                ),
            ):
                with self.assertRaisesRegex(ValueError, "only permits added"):
                    internal.assert_fast_path("a" * 40, "b" * 40, path)
            self.fixture(root)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["migration_plan"] = plan
            internal.write_json(manifest_path, manifest)
            with self.assertRaisesRegex(ValueError, "checks cannot be removed"):
                internal.load_bundle(root)
            manifest["required_checks"].append("migration")
            internal.write_json(manifest_path, manifest)
            self.assertIn("migration", internal.required_checks(manifest))
            self.assertEqual(internal.load_bundle(root)[1]["migration_plan"], plan)

    def test_reused_executor_cannot_hide_changed_inputs_or_wrong_architecture(self):
        image = {
            "Id": "sha256:" + "c" * 64,
            "Architecture": "amd64",
            "Os": "linux",
            "Config": {"Labels": {"org.opencontainers.image.revision": "a" * 40}},
        }
        with (
            patch.object(internal, "image_info", return_value=image),
            patch.object(internal, "fingerprint", side_effect=["old", "new"]),
        ):
            with self.assertRaisesRegex(ValueError, "rebuild executor"):
                internal.reusable_image("example:old", "executor", "b" * 40, "amd64")
        with self.assertRaisesRegex(ValueError, "architecture"):
            internal.assert_image(image, "arm64")
        with self.assertRaisesRegex(ValueError, "source commit"):
            internal.assert_image(image, "amd64", "b" * 40)

    def fixture(self, root):
        manifest = {
            "schema": "airalogy.internal-deployment.v1",
            "github_release": False,
            "version": "0.5.0-beta.1",
            "commit": "a" * 40,
            "platform": "linux/amd64",
            "images": {name: {} for name in internal.INPUTS},
            "required_checks": sorted(internal.REQUIRED_CHECKS),
        }
        with tarfile.open(root / "source.tar.gz", "w:gz") as archive:
            item = tarfile.TarInfo("apps/api/example.py")
            item.size = 4
            archive.addfile(item, io.BytesIO(b"pass"))
        (root / "images.tar").write_bytes(b"synthetic image archive")
        manifest.update(
            source_sha256=internal.digest(root / "source.tar.gz"),
            images_archive_sha256=internal.digest(root / "images.tar"),
        )
        internal.write_json(root / "manifest.json", manifest)
        for name in internal.REQUIRED_CHECKS:
            (root / f"check-{name}.log").write_text("Synthetic check passed\n")
            internal.write_json(
                root / f"check-{name}.json",
                {
                    "status": "passed",
                    "exit_code": 0,
                    "commit": manifest["commit"],
                    "manifest_sha256": internal.digest(root / "manifest.json"),
                    "log_sha256": internal.digest(root / f"check-{name}.log"),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                },
            )

    def test_missing_failed_stale_or_other_candidate_evidence_blocks_readiness(self):
        for mutation in (
            {"status": "failed", "exit_code": 1},
            {"commit": "b" * 40},
            {"manifest_sha256": "b" * 64},
            {
                "finished_at": (
                    datetime.now(timezone.utc) - timedelta(days=2)
                ).isoformat()
            },
        ):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.fixture(root)
                receipt = root / "check-source.json"
                value = json.loads(receipt.read_text())
                value.update(mutation)
                internal.write_json(receipt, value)
                with (
                    patch.object(internal, "verify_images") as verify,
                    self.assertRaisesRegex(ValueError, "mismatched"),
                ):
                    internal.ready(root)
                verify.assert_not_called()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            (root / "check-recovery.json").unlink()
            with self.assertRaises(FileNotFoundError):
                internal.ready(root)

    def test_changed_artifact_or_log_cannot_reuse_pass_receipt(self):
        for changed in ("images.tar", "check-source.log"):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.fixture(root)
                (root / changed).write_text("changed")
                with self.assertRaises(ValueError):
                    internal.ready(root)

    def test_api_reuse_accounts_for_embedded_ai_source(self):
        self.assertIn("packages/masterbrain", internal.INPUTS["api"])
        self.assertIn(".dockerignore", internal.INPUTS["api"])

    def test_archive_accepts_embedded_ai_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.tar.gz"
            with tarfile.open(path, "w:gz") as archive:
                for name in ("packages", "packages/masterbrain", "packages/masterbrain/src/masterbrain/configs.py", ".dockerignore"):
                    archive.addfile(tarfile.TarInfo(name))
            internal.validate_archive(path)

    def test_archive_rejects_private_files_links_and_traversal(self):
        for name, link in (
            (".private/config", False),
            ("../../escape", False),
            ("apps/api/link", True),
            ("packages/masterbrain/link", True),
            ("packages/other/source.py", False),
        ):
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "source.tar.gz"
                with tarfile.open(path, "w:gz") as archive:
                    item = tarfile.TarInfo(name)
                    if link:
                        item.type = tarfile.SYMTYPE
                        item.linkname = "/etc/passwd"
                    archive.addfile(item)
                with self.assertRaises(ValueError):
                    internal.validate_archive(path)


if __name__ == "__main__":
    unittest.main()
