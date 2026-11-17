"""Prevent a silent fallback to a published AI package after the migration."""

from pathlib import Path

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
