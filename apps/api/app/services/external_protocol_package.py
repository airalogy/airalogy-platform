"""Bounded .aira/ZIP decoding. Airalogy validates its own archive manifest."""

import base64
import io
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def unpack_candidate(encoded):
    raw = base64.b64decode(encoded, validate=True)
    try:
        source_zip = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as error:
        raise ValueError("Invalid candidate ZIP archive") from error
    with source_zip as archive:
        members = archive.infolist()
        if len(members) > 100 or sum(m.file_size for m in members) > 1_000_000:
            raise ValueError("Candidate archive exceeds limits")
        names = [m.filename for m in members]
        if len(set(names)) != len(names):
            raise ValueError("Duplicate archive paths")
        for member in members:
            path = PurePosixPath(member.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in member.filename
                or stat.S_ISLNK(member.external_attr >> 16)
            ):
                raise ValueError("Unsafe archive path")
        marker = "_airalogy_archive/manifest.json"
        if marker in names:
            from airalogy.archive import read_archive_manifest, validate_archive

            with tempfile.TemporaryDirectory(prefix="external-candidate-") as temporary:
                source = Path(temporary) / "candidate.aira"
                source.write_bytes(raw)
                valid, _ = validate_archive(source)
                if not valid or read_archive_manifest(source).get("kind") != "protocol":
                    raise ValueError("Invalid Protocol .aira archive")
        roots = [
            PurePosixPath(n).parent
            for n in names
            if PurePosixPath(n).name == "protocol.aimd"
        ]
        if len(roots) != 1:
            raise ValueError("Expected exactly one Protocol root")
        files, binary = {}, {}
        for member in members:
            if member.is_dir() or member.filename == marker:
                continue
            path = PurePosixPath(member.filename)
            if not path.is_relative_to(roots[0]):
                raise ValueError("File outside Protocol root")
            name = path.relative_to(roots[0]).as_posix()
            try:
                data = archive.read(member)
            except (RuntimeError, zipfile.BadZipFile, NotImplementedError) as error:
                raise ValueError("Unreadable candidate archive member") from error
            if path.suffix.lower() in {
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".webp",
                ".pdf",
            }:
                binary[name] = base64.b64encode(data).decode()
            else:
                files[name] = data.decode("utf-8")
        return files, binary
