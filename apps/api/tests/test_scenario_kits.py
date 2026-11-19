"""Pure catalog contracts; every shipped component is parsed by the real executor."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from app.config import config
from app.libs.protocol_agent import protocol_exec
from app.services.scenario_catalog import (
    MODULES,
    availability,
    catalog,
    digest,
    template_files,
)


def test_catalog_is_closed_and_compatible():
    for entry in catalog():
        assert entry["external_services"] == []
        assert not availability(
            entry, enabled_modules=set(MODULES), platform_version="0.3.1"
        )
        assert availability(entry, enabled_modules=set(), platform_version="0.3.1")
        assert availability(
            entry, enabled_modules=set(MODULES), platform_version="development"
        )
        assert entry["digest"] == digest(
            {k: v for k, v in entry.items() if k != "digest"}
        )


@pytest.mark.parametrize(
    ("version", "compatible"),
    [
        ("0.5.0-alpha.3", False),
        ("0.5.0-beta.1", False),
        ("0.5.0-beta.2", True),
        ("0.5.0-beta.10", True),
        ("0.5.0-rc.1", True),
        ("0.5.0", True),
        ("0.6.0", False),
        ("0.5.0-beta", False),
    ],
)
def test_catalog_prerelease_boundaries(version, compatible):
    entry = {
        **next(iter(catalog())),
        "platform_min": "0.5.0-beta.2",
        "platform_max_exclusive": "0.6.0",
    }
    blockers = availability(entry, enabled_modules=set(MODULES), platform_version=version)
    assert ("platform_version" not in blockers) == compatible


@pytest.mark.parametrize(
    "component,version",
    [("sample", "1.0.0"), ("measurement", "1.0.0"), ("measurement", "1.1.0")],
)
def test_bundled_protocol_compiles(component, version):
    async def exercise():
        Path(config.PROTOCOL_DIR).mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=config.PROTOCOL_DIR) as directory:
            for name, content in template_files(
                component, "synthetic_kit", version
            ).items():
                (Path(directory) / name).write_text(content)
            result = await protocol_exec(
                "get_protocol_info", Path(directory).name, {"env_vars": {}}
            )
            assert result["success"], result
            schema = result["data"]["json_schema"]["vars"]
            assert schema["additionalProperties"] is False
            if component == "measurement":
                assert {
                    "sample",
                    "value",
                    "method",
                    "metric",
                    "unit",
                    "measured_at",
                } <= set(schema["required"])
                sample = next(
                    field
                    for field in result["data"]["fields"]["vars"]
                    if field["name"] == "sample"
                )
                assert sample["kwargs"]["resource_role"] == "reference"

    asyncio.run(exercise())
