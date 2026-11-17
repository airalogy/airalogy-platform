"""Prevent a silent fallback to a published AI package after the migration."""

from pathlib import Path
import importlib.util
import json
import sys

import masterbrain


def test_api_uses_the_same_checkout_ai_source():
    root = Path(__file__).resolve().parents[3]
    assert Path(masterbrain.__file__).resolve().is_relative_to(
        root / "packages/masterbrain/src"
    )


def test_embedded_ai_does_not_expose_studio_or_local_filesystem_routes():
    from masterbrain.fastapi.main import app

    paths = {route.path for route in app.routes}
    assert "/api/endpoints/code_edit" in paths
    assert "/api/endpoints/chat/field_input/turn" in paths
    assert not any(path.startswith(("/api/endpoints/workspace", "/api/endpoints/library")) for path in paths)
    assert "/" not in paths
    assert "/{full_path:path}" not in paths


def test_contract_check_accepts_formatting_but_rejects_schema_changes(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "export_masterbrain_contract", root / "scripts/export-masterbrain-contract.py"
    )
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    target = tmp_path / "schema.json"
    monkeypatch.setattr(exporter, "TARGET", target)
    monkeypatch.setattr(exporter, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["export-masterbrain-contract.py", "--check"])

    payload = json.loads(exporter.render_contract())
    target.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    assert exporter.main() == 0

    payload["request"]["properties"].pop(next(iter(payload["request"]["properties"])))
    target.write_text(json.dumps(payload), encoding="utf-8")
    assert exporter.main() == 1

    target.write_text("invalid JSON", encoding="utf-8")
    assert exporter.main() == 1
