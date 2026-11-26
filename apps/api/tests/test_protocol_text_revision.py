import tomllib
import zipfile

import pytest

from app.services.protocol_text_revision import revised_package


def package(tmp_path):
    path = tmp_path / "original.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "p/protocol.toml",
            '[airalogy_protocol]\nid="sample"\nversion="0.1.0"\n[extra]\nversion="9"\n',
        )
        archive.writestr("p/protocol.aimd", "# Worksheet\n{{var|label: str}}\n")
        archive.writestr("p/files/image.png", b"unchanged")
    return path


def test_revision_retains_original_package_metadata_and_assets(tmp_path):
    source = package(tmp_path)
    content = "# Revised worksheet\n\nSome notes.\n{{var|label: str}}\n"
    with zipfile.ZipFile(
        revised_package(source, tmp_path, content, "0.1.1")
    ) as archive:
        assert archive.read("protocol.aimd").decode() == content
        assert archive.read("files/image.png") == b"unchanged"
        manifest = tomllib.loads(archive.read("protocol.toml").decode())
        assert manifest["airalogy_protocol"]["version"] == "0.1.1"
        assert manifest["extra"]["version"] == "9"
    with zipfile.ZipFile(source) as original:
        assert b"Revised" not in original.read("p/protocol.aimd")


def test_revision_rejects_field_definition_changes(tmp_path):
    with pytest.raises(ValueError, match="preserve field"):
        revised_package(
            package(tmp_path), tmp_path, "# Worksheet\n{{var|label: int}}", "0.1.1"
        )
