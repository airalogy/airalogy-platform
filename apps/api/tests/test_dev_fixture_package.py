import asyncio
import tomllib
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

from app.routers.dev_fixtures import ensure_analysis_package


def test_analysis_fixture_stores_the_versioned_editor_package(monkeypatch):
    captured = {}

    async def upload(package, length):
        captured["data"] = package.read()
        assert len(captured["data"]) == length

    async def find_version(*args):
        return SimpleNamespace(aimd="# Synthetic\n{{var|measurement: float}}", upload_package=upload)

    monkeypatch.setattr("app.routers.dev_fixtures.ProtocolVersion.find_by", find_version)
    asyncio.run(ensure_analysis_package(None, SimpleNamespace(id="fixture", uid="synthetic", name="Synthetic")))
    with ZipFile(BytesIO(captured["data"])) as archive:
        assert set(archive.namelist()) == {"protocol.aimd", "protocol.toml"}
        assert "measurement: float" in archive.read("protocol.aimd").decode()
        assert tomllib.loads(archive.read("protocol.toml").decode())["airalogy_protocol"] == {
            "id": "synthetic", "name": "Synthetic", "version": "1.0.0",
        }
