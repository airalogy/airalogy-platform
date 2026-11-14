"""Generator compatibility without starting services or publishing artifacts."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy/single-lab/scripts/generate-env.sh"


class OrganizationDeploymentTests(unittest.TestCase):
    def generate(self, *args):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            result = subprocess.run(
                ["bash", str(SCRIPT), *args],
                cwd=ROOT,
                env={**os.environ, "AIRALOGY_ENV_FILE": str(path)},
                capture_output=True,
                text=True,
            )
            # Never print generator output: it includes the setup secret.
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            return dict(
                line.split("=", 1)
                for line in path.read_text().splitlines()
                if line and not line.startswith("#") and "=" in line
            )

    def test_company_config_is_canonical_and_uses_generic_defaults(self):
        values = self.generate(
            "--organization-name", "Synthetic R&D", "--organization-type", "company"
        )
        self.assertEqual(values["DEPLOYMENT_MODE"], "single_organization")
        self.assertEqual(values["SINGLE_ORGANIZATION_NAME"], "Synthetic R&D")
        self.assertEqual(values["SINGLE_ORGANIZATION_TYPE"], "company")
        self.assertEqual(values["SINGLE_ORGANIZATION_DEFAULT_PROJECT_UID"], "workspace")
        self.assertEqual(values["SINGLE_ORGANIZATION_DEFAULT_PROJECT_NAME"], "General")
        self.assertNotIn("SINGLE_LAB_UID", values)
        self.assertEqual(values["SIGNUP_MODE"], "invite_only")

    def test_old_generator_arguments_remain_compatible(self):
        values = self.generate(
            "--lab-name", "Synthetic Lab", "--lab-uid", "existing_lab"
        )
        self.assertEqual(values["DEPLOYMENT_MODE"], "single_lab")
        self.assertEqual(values["SINGLE_LAB_UID"], "existing_lab")
        self.assertEqual(values["SINGLE_LAB_DEFAULT_PROJECT_UID"], "lab_protocols")
        self.assertEqual(values["SINGLE_LAB_DEFAULT_PROJECT_NAME"], "General")
        self.assertNotIn("SINGLE_ORGANIZATION_UID", values)

    def test_mixed_arguments_and_unknown_type_fail_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            for args in [
                ["--lab-name", "Original Lab", "--organization-name", "Other Company"],
                ["--organization-type", "unsupported"],
            ]:
                result = subprocess.run(
                    ["bash", str(SCRIPT), *args],
                    cwd=ROOT,
                    env={**os.environ, "AIRALOGY_ENV_FILE": str(path)},
                    capture_output=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(path.exists())
