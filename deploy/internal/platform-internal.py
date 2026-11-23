#!/usr/bin/env python3
"""Prepare and qualify a private, single-architecture application deployment.

Only publish-ghcr uploads images. Instance cutover is a separate operation.
Instance-specific backup, acceptance and cutover commands stay in private ops.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUTS = {
    "api": ["apps/api", "packages/masterbrain", ".dockerignore"],
    "web": [
        "apps/web",
        "packages",
        "docs",
        "package.json",
        "pnpm-lock.yaml",
        "pnpm-workspace.yaml",
        "tsconfig.base.json",
        "uno.config.ts",
        "deploy/single-lab/web.Dockerfile",
        "deploy/single-lab/Caddyfile",
    ],
    "executor": [
        "apps/api/protocol_executor.py",
        "apps/api/protocol_assigners.py",
        "apps/api/protocol_executor.Dockerfile",
        "apps/api/protocol_requirements.txt",
    ],
}
# This first fast path deliberately supports application-only, same-schema updates.
PROTECTED = [
    "apps/api/migrations",
    "apps/api/postgresql.Dockerfile",
    "deploy/object-storage",
    "deploy/single-lab/compose.yml",
]
REQUIRED_CHECKS = {"source", "artifact-acceptance", "recovery"}
DEFAULT_INTERNAL_REPOSITORY = "ghcr.io/airalogy/airalogy-platform"
DIGEST = r"sha256:[0-9a-f]{64}"


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def output(args, cwd=ROOT):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    temp.chmod(0o600)
    os.replace(temp, path)


def source_identity():
    if output(["git", "status", "--porcelain"]):
        raise ValueError("Commit all candidate changes before preparing deployment")
    commit = output(["git", "rev-parse", "HEAD"])
    version = (ROOT / "VERSION").read_text().strip()
    run(["node", "scripts/check-version.mjs"], cwd=ROOT)
    return commit, version


def fingerprint(commit, paths):
    return hashlib.sha256(
        output(["git", "ls-tree", "-r", commit, "--", *paths]).encode()
    ).hexdigest()


def assert_fast_path(base, target, migration_plan=None):
    if not re.fullmatch(r"[a-f0-9]{40}", base):
        raise ValueError("Base must be a full deployed commit SHA")
    run(["git", "merge-base", "--is-ancestor", base, target], cwd=ROOT)
    changed = output(["git", "diff", "--name-only", base, target, "--", *PROTECTED])
    if changed and not migration_plan:
        raise ValueError(
            "Schema/infrastructure changes require a separate migration/recovery plan: "
            + changed
        )

    if not migration_plan:
        return None
    plan = json.loads(Path(migration_plan).read_text())
    if plan.get("base_commit") != base or plan.get("target_commit") != target:
        raise ValueError(
            "Migration plan must identify the exact deployed and candidate commits"
        )
    for key in (
        "source_revision",
        "target_revision",
        "backup_plan",
        "migration_validation",
        "rollback_policy",
        "write_impact",
    ):
        if not isinstance(plan.get(key), str) or not plan[key].strip():
            raise ValueError("Migration plan is missing " + key)
    paths = changed.splitlines()
    if not paths or sorted(plan.get("changed_paths", [])) != sorted(paths):
        raise ValueError("Migration plan must cover every protected changed path")
    statuses = output(
        ["git", "diff", "--name-status", base, target, "--", *PROTECTED]
    ).splitlines()
    for line in statuses:
        status, path = line.split("\t", 1)
        if path == "apps/api/migrations/model_registry.py" and status == "M":
            continue
        if status != "A" or not re.fullmatch(
            r"apps/api/migrations/versions/[a-zA-Z0-9_]+\.py", path
        ):
            raise ValueError(
                "Reviewed migration delivery only permits added migrations and model registration; infrastructure or old migration edits need a separate procedure"
            )
    head = output(
        ["python3", "scripts/release-migration-head.py", "apps/api/migrations/versions"]
    )
    if head != plan["target_revision"]:
        raise ValueError("Migration plan target revision does not match candidate")
    return plan


def required_checks(manifest):
    return REQUIRED_CHECKS | (
        {"migration"} if manifest.get("migration_plan") else set()
    )


def image_info(reference):
    return json.loads(output(["docker", "image", "inspect", reference]))[0]


def assert_image(info, architecture, commit=None, version=None):
    if info["Architecture"] != architecture or info.get("Os") != "linux":
        raise ValueError("Image target architecture/OS does not match")
    labels = info.get("Config", {}).get("Labels") or {}
    if commit and labels.get("org.opencontainers.image.revision") != commit:
        raise ValueError("Image source commit does not match")
    if version and labels.get("org.opencontainers.image.version") != version:
        raise ValueError("Image product version does not match")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", info["Id"]):
        raise ValueError("Missing immutable image ID")


def reusable_image(reference, role, target, architecture):
    info = image_info(reference)
    assert_image(info, architecture)
    commit = (info.get("Config", {}).get("Labels") or {}).get(
        "org.opencontainers.image.revision", ""
    )
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("Reused image needs a verifiable source commit label")
    if fingerprint(commit, INPUTS[role]) != fingerprint(target, INPUTS[role]):
        raise ValueError("Reused image inputs differ; rebuild " + role)
    return info, commit


def validate_archive(path):
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            name = Path(member.name)
            if (
                name.is_absolute()
                or ".." in name.parts
                or not (member.isfile() or member.isdir())
            ):
                raise ValueError(
                    "Source archive must contain only safe regular files/directories"
                )
            if not (
                member.name.startswith("apps/api/")
                or member.name.startswith("deploy/single-lab/")
                or member.name.startswith("packages/masterbrain/")
                or member.name in {"apps", "apps/api", "deploy", "deploy/single-lab", "packages", "packages/masterbrain", ".dockerignore"}
            ):
                raise ValueError("Unexpected source archive path")


def prepare(args):
    commit, version = source_identity()
    migration_plan = assert_fast_path(args.base, commit, args.migration_plan)
    target = Path(args.output).resolve()
    target.mkdir(parents=True, exist_ok=False, mode=0o700)
    architecture = args.platform.split("/")[1]
    created = datetime.now(timezone.utc).isoformat()
    images = {}
    for role in INPUTS:
        reuse = args.reuse_executor if role == "executor" else None
        tag = f"airalogy-platform-internal-{role}:{version}-{commit}"
        source_commit = commit
        if reuse:
            info, source_commit = reusable_image(reuse, role, commit, architecture)
            reference = reuse
        else:
            # Never replace bytes already associated with an internal build identity.
            present = subprocess.run(
                ["docker", "image", "inspect", tag],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if present.returncode == 0:
                raise ValueError(
                    "Image already exists; select its verified bytes with --reuse-"
                    + role
                )
            command = [
                "docker",
                "buildx",
                "build",
                "--platform",
                args.platform,
                "--load",
                "--progress",
                "plain",
                "-t",
                tag,
            ]
            for key, value in {
                "PLATFORM_VERSION": version,
                "GIT_COMMIT": commit,
                "GIT_TAG": "",
                "BUILD_TIME": created,
                "BUILD_DIRTY": "false",
            }.items():
                command += ["--build-arg", f"{key}={value}"]
            if role == "web":
                for key, value in {
                    "VITE_DEPLOYMENT_MODE": "single_organization",
                    "VITE_APP_TITLE": args.web_title,
                    "VITE_SITE_ORIGIN": args.web_origin,
                    "VITE_DOCS_URL": "/docs/",
                }.items():
                    command += ["--build-arg", f"{key}={value}"]
                command += ["-f", "deploy/single-lab/web.Dockerfile", "."]
            else:
                if role == "executor" and args.executor_python_repository:
                    command += [
                        "--build-arg",
                        f"EXECUTOR_PYTHON_REPOSITORY={args.executor_python_repository}",
                    ]
                command += [
                    "-f",
                    "apps/api/"
                    + (
                        "Dockerfile"
                        if role == "api"
                        else "protocol_executor.Dockerfile"
                    ),
                    "." if role == "api" else "apps/api",
                ]
            with (target / f"build-{role}.log").open("w") as log:
                run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            info = image_info(tag)
            assert_image(info, architecture, commit, version)
            reference = tag
        images[role] = {
            "reference": reference,
            "image_id": info["Id"],
            "source_commit": source_commit,
            "inputs_sha256": fingerprint(commit, INPUTS[role]),
            "reused": bool(reuse),
        }
        print(f"{role}: {'reused' if reuse else 'built'} {info['Id']}", flush=True)
    archive = target / "source.tar.gz"
    run(
        [
            "git",
            "archive",
            "--format=tar.gz",
            "--output=" + str(archive),
            commit,
            "apps/api",
            "packages/masterbrain",
            ".dockerignore",
            "deploy/single-lab",
        ],
        cwd=ROOT,
    )
    validate_archive(archive)
    # Export only the selected images, not daemon data or workstation files.
    image_archive = target / "images.tar"
    run(
        [
            "docker",
            "image",
            "save",
            "-o",
            str(image_archive),
            *sorted({image["reference"] for image in images.values()}),
        ]
    )
    schema = output(
        ["python3", "scripts/release-migration-head.py", "apps/api/migrations/versions"]
    )
    manifest = {
        "schema": "airalogy.internal-deployment.v1",
        "version": version,
        "commit": commit,
        "base_commit": args.base,
        "created_at": created,
        "platform": args.platform,
        "database_revision": schema,
        "migration_inputs_sha256": fingerprint(commit, ["apps/api/migrations"]),
        "images": images,
        "source_sha256": digest(archive),
        "images_archive_sha256": digest(image_archive),
        "required_checks": sorted(
            REQUIRED_CHECKS | ({"migration"} if migration_plan else set())
        ),
        "migration_plan": migration_plan,
        "github_release": False,
    }
    if source_identity() != (commit, version):
        raise ValueError("Source changed while building")
    write_json(target / "manifest.json", manifest)
    print("Private bundle prepared; validation and deployment have not been performed.")


def load_bundle(directory, *, require_image_archive=True):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text())
    if (
        manifest.get("schema") != "airalogy.internal-deployment.v1"
        or manifest.get("github_release") is not False
    ):
        raise ValueError("Unsupported internal manifest")
    if set(manifest.get("required_checks", [])) != required_checks(manifest):
        raise ValueError("Required checks cannot be removed")
    if set(manifest["images"]) != set(INPUTS):
        raise ValueError("Incomplete application image set")
    files = [("source.tar.gz", "source_sha256")]
    if require_image_archive or (directory / "images.tar").exists():
        files.append(("images.tar", "images_archive_sha256"))
    for name, key in files:
        if digest(directory / name) != manifest[key]:
            raise ValueError("Artifact bytes changed: " + name)
    validate_archive(directory / "source.tar.gz")
    return directory, manifest


def verify_images(manifest, references=None):
    for role, item in manifest["images"].items():
        reference = references[role] if references is not None else item["reference"]
        info = image_info(reference)
        assert_image(
            info,
            manifest["platform"].split("/")[1],
            item["source_commit"],
            None if item["reused"] else manifest["version"],
        )
        if info["Id"] != item["image_id"]:
            raise ValueError("Image bytes changed: " + role)


def check(args):
    directory, manifest = load_bundle(args.bundle)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise ValueError("An actual validation command is required")
    if args.name == "source" and source_identity() != (
        manifest["commit"],
        manifest["version"],
    ):
        raise ValueError("Source checks must run on the exact clean candidate")
    receipt = directory / f"check-{args.name}.json"
    # A failed retry replaces the previous success; old successes cannot hide failures.
    value = {
        "name": args.name,
        "manifest_sha256": digest(directory / "manifest.json"),
        "commit": manifest["commit"],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
    }
    write_json(receipt, value)
    with (directory / f"check-{args.name}.log").open("w") as log:
        result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    if args.name == "source" and source_identity() != (
        manifest["commit"],
        manifest["version"],
    ):
        raise ValueError(
            "Source changed during checks; running receipt remains unqualified"
        )
    value.update(
        status="passed" if result.returncode == 0 else "failed",
        exit_code=result.returncode,
        finished_at=datetime.now(timezone.utc).isoformat(),
        log_sha256=digest(directory / f"check-{args.name}.log"),
    )
    write_json(receipt, value)
    if result.returncode:
        raise ValueError(f"{args.name} failed; inspect its private log")
    print(args.name + ": passed")


def verify_receipts(directory, manifest, now=None):
    expected = digest(directory / "manifest.json")
    now = now or datetime.now(timezone.utc)
    for name in required_checks(manifest):
        receipt = json.loads((directory / f"check-{name}.json").read_text())
        age = (now - datetime.fromisoformat(receipt["finished_at"])).total_seconds()
        if (
            receipt.get("status") != "passed"
            or receipt.get("exit_code") != 0
            or receipt.get("manifest_sha256") != expected
            or receipt.get("commit") != manifest["commit"]
            or not 0 <= age <= 86400
            or digest(directory / f"check-{name}.log") != receipt.get("log_sha256")
        ):
            raise ValueError("Missing, failed, stale or mismatched check: " + name)


def ready(directory, now=None):
    directory, manifest = load_bundle(directory)
    verify_receipts(directory, manifest, now)
    verify_images(manifest)
    return manifest


def ghcr_repository(value):
    if not re.fullmatch(r"ghcr\.io/[a-z0-9]+(?:-[a-z0-9]+)*/[a-z0-9]+(?:[._-][a-z0-9]+)*", value):
        raise ValueError("Expected ghcr.io/<organization>/<package> without a tag or digest")
    return value


def pull_verified_images(manifest, references):
    for reference in references.values():
        run(["docker", "image", "pull", "--platform", manifest["platform"], reference])
    verify_images(manifest, references)


def publish_ghcr(directory, repository):
    repository = ghcr_repository(repository)
    directory = Path(directory).resolve()
    manifest = ready(directory)
    _, owner, package = repository.split("/")
    try:
        visibility = output([
            "gh", "api", "--hostname", "github.com",
            f"/orgs/{owner}/packages/container/{package}", "--jq", ".visibility",
        ])
    except subprocess.CalledProcessError as exc:
        raise ValueError(
            f"Cannot verify {repository}: check that the package exists and gh can read its metadata"
        ) from exc
    if visibility != "private":
        raise ValueError("Internal images require a private organization package")

    references = {}
    for role, item in manifest["images"].items():
        # Independent builds of the same source can have different image IDs.
        tag = f"{role}-{manifest['version']}-{manifest['commit']}-{item['image_id'][7:31]}"
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", tag):
            raise ValueError("Invalid internal image tag: " + tag)
        target = f"{repository}:{tag}"
        run(["docker", "image", "tag", item["image_id"], target])
        pushed = output(["docker", "image", "push", target])
        digests = re.findall(rf"^{re.escape(tag)}: digest: ({DIGEST}) size: \d+\s*$", pushed, re.M)
        if len(digests) != 1:
            raise ValueError("Registry did not return a unique digest for " + role)
        references[role] = f"{repository}@{digests[0]}"
    pull_verified_images(manifest, references)
    write_json(directory / "ghcr.json", {
        "manifest_sha256": digest(directory / "manifest.json"),
        "images": references,
    })
    print("Private image references saved to ghcr.json")


def pull_ghcr(directory, repository):
    repository = ghcr_repository(repository)
    directory, manifest = load_bundle(directory, require_image_archive=False)
    verify_receipts(directory, manifest)
    delivery = json.loads((directory / "ghcr.json").read_text())
    references = delivery.get("images")
    if delivery.get("manifest_sha256") != digest(directory / "manifest.json"):
        raise ValueError("Registry references belong to another deployment manifest")
    if not isinstance(references, dict) or set(references) != set(INPUTS) or not all(
        isinstance(ref, str) and re.fullmatch(re.escape(repository) + "@" + DIGEST, ref)
        for ref in references.values()
    ):
        raise ValueError("Expected a digest in the configured GHCR package for every image")
    pull_verified_images(manifest, references)
    verify_receipts(directory, manifest)
    print("All images verified. Use the manifest image IDs for the separate instance cutover.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    build = commands.add_parser("prepare")
    build.add_argument("--base", required=True)
    build.add_argument(
        "--platform", choices=["linux/amd64", "linux/arm64"], required=True
    )
    build.add_argument("--output", required=True)
    build.add_argument("--web-origin", required=True)
    build.add_argument("--web-title", default="Airalogy Platform")
    executor = build.add_mutually_exclusive_group()
    executor.add_argument("--reuse-executor")
    executor.add_argument("--executor-python-repository", help="Mirror of the pinned Python base image")
    build.add_argument(
        "--migration-plan",
        help="Reviewed private JSON plan for additive schema changes",
    )
    validate = commands.add_parser("check")
    validate.add_argument("--bundle", required=True)
    validate.add_argument(
        "--name", choices=sorted(REQUIRED_CHECKS | {"migration"}), required=True
    )
    validate.add_argument("command", nargs=argparse.REMAINDER)
    for name in ("verify", "ready"):
        command = commands.add_parser(name)
        command.add_argument("--bundle", required=True)
    for name in ("publish-ghcr", "pull-ghcr"):
        command = commands.add_parser(name)
        command.add_argument("--bundle", required=True)
        command.add_argument("--repository", default=DEFAULT_INTERNAL_REPOSITORY, type=ghcr_repository)
    args = parser.parse_args()
    os.umask(0o077)
    if args.action == "prepare":
        prepare(args)
    elif args.action == "check":
        check(args)
    elif args.action == "verify":
        _, manifest = load_bundle(args.bundle)
        verify_images(manifest)
        print("Artifact identities verified; this does not qualify deployment.")
    elif args.action == "publish-ghcr":
        publish_ghcr(args.bundle, args.repository)
    elif args.action == "pull-ghcr":
        pull_ghcr(args.bundle, args.repository)
    else:
        ready(args.bundle)
        print(
            "Internal bundle checks passed; instance cutover remains a separate operation."
        )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
