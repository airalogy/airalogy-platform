"""Portable record of every regular object in a managed recovery point."""
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path


def inventory(root):
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Missing object directory")
    for directory, dirs, files in os.walk(root, onerror=raise_error):
        dirs.sort()
        for name in dirs:
            if (Path(directory) / name).is_symlink():
                raise ValueError("Unexpected object symlink")
        for name in sorted(files):
            path = Path(directory) / name
            if not stat.S_ISREG(path.lstat().st_mode):
                raise ValueError("Unexpected object file type")
            digest = hashlib.sha256()
            with path.open("rb") as file:
                for block in iter(lambda: file.read(1024 * 1024), b""):
                    digest.update(block)
            yield json.dumps([str(path.relative_to(root)), digest.hexdigest()]) + "\n"


def raise_error(error):
    raise error


def snapshot(root, verify):
    from itertools import zip_longest

    index = root / "objects.jsonl"
    rows = inventory(root / "objects")
    if verify:
        with index.open(encoding="utf-8") as file:
            if any(a != b for a, b in zip_longest(rows, file)):
                raise ValueError("Object inventory or content checksum mismatch")
    else:
        with index.open("x", encoding="utf-8") as file:
            file.writelines(rows)


def require_checksum_entries(root):
    # Legacy manifests also use sha256sum's exact two-space text delimiter.
    names = []
    for line in (root / "SHA256SUMS").read_text().splitlines():
        match = re.fullmatch(r"[0-9a-f]{64}  ([A-Za-z0-9_.-]+)", line)
        if not match:
            raise ValueError("Invalid recovery point checksum list")
        names.append(match[1])
    base = ["database.dump", "manifest.env", "secrets.env"]
    if not any(sorted(names) == sorted([*base, index]) for index in ("objects.tar.gz", "objects.jsonl")):
        raise ValueError("Incomplete recovery point checksum list")
    if any((root / name).is_symlink() or not (root / name).is_file() for name in [*names, "SHA256SUMS"]):
        raise ValueError("Invalid recovery point file")


if __name__ == "__main__":
    root = Path(sys.argv[2])
    if sys.argv[1] == "checksums":
        require_checksum_entries(root)
    else:
        snapshot(root, {"index": False, "verify": True}[sys.argv[1]])
