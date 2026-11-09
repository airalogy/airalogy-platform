"""Candidate archives are untrusted input; never extract unsafe paths."""

import base64
import io
import zipfile
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.services.external_research_contracts import ProtocolCandidate


def archive(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as package:
        for name, value in files:
            package.writestr(name, value)
    return base64.b64encode(stream.getvalue()).decode()


SOURCES = [
    ("protocol.aimd", "{{var|value: float}}"),
    ("protocol.toml", '[airalogy_protocol]\nid="synthetic"\nversion="1.0.0"'),
]


def test_candidate_archive_normalizes_one_root_and_preserves_binary_assets():
    from PIL import Image

    stream = io.BytesIO()
    Image.new("RGB", (1, 1), (60, 120, 180)).save(stream, format="PNG")
    png = stream.getvalue()
    candidate = ProtocolCandidate(
        request_key=uuid4().hex,
        archive_base64=archive(
            [(f"synthetic/{k}", v) for k, v in SOURCES]
            + [("synthetic/assets/image.png", png)]
        ),
    )
    assert candidate.archive_base64 is None
    assert candidate.files == dict(SOURCES)
    assert base64.b64decode(candidate.binary_files["assets/image.png"]) == png


@pytest.mark.parametrize(
    "extra",
    [
        [("../escape.py", "pass")],
        [(".env", "private")],
        [("protocol.aimd", "duplicate")],
        [("other/protocol.aimd", "second root")],
        [("huge.txt", "x" * 1_000_001)],
        [("assets/fake.png", "not a PNG")],
    ],
)
def test_candidate_archive_rejects_unsafe_ambiguous_and_disguised_members(extra):
    with pytest.raises((ValidationError, ValueError)):
        ProtocolCandidate(
            request_key=uuid4().hex, archive_base64=archive(SOURCES + extra)
        )


def test_bad_zip_and_text_disguised_as_binary_are_rejected():
    with pytest.raises(ValidationError):
        ProtocolCandidate(
            request_key=uuid4().hex,
            archive_base64=base64.b64encode(b"not a zip").decode(),
        )
    with pytest.raises(ValidationError):
        ProtocolCandidate(
            request_key=uuid4().hex, files={**dict(SOURCES), "fake.png": "not a PNG"}
        )


def test_official_aira_roundtrip_and_tampered_manifest(tmp_path):
    from app.services.protocol_exports import build_protocol_export

    source = tmp_path / "source.zip"
    source.write_bytes(base64.b64decode(archive(SOURCES)))
    output = build_protocol_export(source, tmp_path, "aira")
    candidate = ProtocolCandidate(
        request_key=uuid4().hex,
        archive_base64=base64.b64encode(output.read_bytes()).decode(),
    )
    assert candidate.files == dict(SOURCES)
    with zipfile.ZipFile(output) as package:
        members = [
            (name, package.read(name) if name != "protocol.aimd" else b"tampered")
            for name in package.namelist()
        ]
    with pytest.raises(ValidationError):
        ProtocolCandidate(request_key=uuid4().hex, archive_base64=archive(members))
