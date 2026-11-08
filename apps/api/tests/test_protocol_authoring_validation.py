import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from app.database import get_db_session
from app.models.chat import ChatModel
from app.routers import editor
from app.routers.depends import get_current_user
from app.services import protocol_authoring as authoring
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

VALID = "# Synthetic protocol\n\n{{var|sample_id: str}}\n{{ref_var|sample_id}}\n"
INVALID = VALID.replace("ref_var|sample_id", "ref_var|sample")


def source(content=VALID, path="protocol.aimd"):
    return authoring.SourceFile(path=path, content=content)


def changed(content=VALID, **overrides):
    return {
        "changed_files": [
            {
                "path": "protocol.aimd",
                "content": content,
                "type": "aimd",
                "status": "modified",
            }
        ],
        "warnings": [],
        "risk": {"level": "safe", "recommended_action": "auto_apply", "reasons": []},
        **overrides,
    }


def test_checker_uses_real_sdk_locations_and_accepts_full_length_protocols():
    report = authoring.validate_sources([source(INVALID)])
    assert report.status == "invalid"
    assert report.diagnostics[0].line == 4
    assert report.diagnostics[0].path == "protocol.aimd"
    assert "sample" in report.diagnostics[0].message
    assert (
        authoring.validate_sources([source(VALID + "notes " * 2000)]).status == "valid"
    )


@pytest.mark.parametrize(
    ("path", "content"),
    [
        ("model.py", "class VarModel(:\n"),
        ("protocol.toml", "[protocol"),
        ("protocol.aimd", "{{var|x: int}}\n{{var|x: int}}"),
        ("protocol.aimd", ""),
    ],
)
def test_invalid_sources_are_structured(path, content):
    report = authoring.validate_sources([source(content, path)])
    assert report.status == "invalid" and report.diagnostics[0].path == path


def test_checker_never_executes_python_or_inline_assigners(tmp_path):
    marker = tmp_path / "must-not-exist"
    code = f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
    assert authoring.validate_sources([source(code, "model.py")]).status == "valid"
    authoring.validate_sources([source(f"```assigner\n{code}```")])
    assert not marker.exists()


def test_checker_failure_is_not_a_syntax_error(monkeypatch):
    monkeypatch.setattr(
        authoring, "validate_aimd", Mock(side_effect=RuntimeError("internal"))
    )
    report = authoring.validate_sources([source()])
    assert report.status == "unavailable"
    assert report.diagnostics[0].code == "checker_unavailable"
    assert "internal" not in report.diagnostics[0].message


def test_cross_file_assigner_cycles_are_checked_without_execution():
    content = """from airalogy.assigner import assigner
@assigner(assigned_fields=["x"], dependent_fields=["y"], mode="auto")
def first(values): pass
@assigner(assigned_fields=["y"], dependent_fields=["x"], mode="auto")
def second(values): pass
"""
    assert (
        authoring.validate_sources([source(), source(content, "assigner.py")]).status
        == "invalid"
    )


def test_invalid_ai_edits_are_blocked_and_manual_repairs_require_review():
    assert (
        authoring.validate_edit_result(changed(INVALID), [source()])["risk"][
            "recommended_action"
        ]
        == "block"
    )
    assert (
        authoring.validate_edit_result(
            changed(), [source(INVALID)], require_review=True
        )["risk"]["recommended_action"]
        == "review"
    )
    assert (
        authoring.validate_edit_result(changed(), [source()])["risk"][
            "recommended_action"
        ]
        == "auto_apply"
    )


@pytest.fixture
def generation(monkeypatch):
    db = SimpleNamespace(add=Mock(), commit=AsyncMock())
    user = SimpleNamespace(id=uuid4())
    usage = AsyncMock()
    repair = AsyncMock(return_value=changed())
    monkeypatch.setattr(editor, "check_model_usage", usage)
    monkeypatch.setattr(editor, "protocol_code_edit", repair)

    def run(content=INVALID):
        async def stream(*args, **kwargs):
            yield content[:10]
            yield content[10:]

        monkeypatch.setattr(editor, "protocol_generate_aimd", stream)
        return asyncio.run(
            editor.generate_protocol_draft(
                db, user, "Synthetic example", ChatModel(model_type=1)
            )
        )

    return run, repair, usage, db


def test_valid_generation_does_not_spend_a_repair_call(generation):
    run, repair, usage, _ = generation
    response = run(VALID)
    assert response.validation.status == "valid"
    assert response.repair_status == "not_needed"
    repair.assert_not_awaited()
    assert usage.await_count == 1


def test_generation_repairs_once_rechecks_and_retains_original(generation):
    run, repair, usage, db = generation
    response = run()
    assert response.content == VALID and response.original_content == INVALID
    assert response.validation.status == "valid" and response.repair_status == "applied"
    assert repair.await_count == 1 and usage.await_count == 2
    assert "Preserve all scientific meaning" in repair.await_args.args[0]["prompt"]
    assert db.add.call_args.args[0].messages[0]["content"] == INVALID


@pytest.mark.parametrize(
    "failure", ["invalid", "unavailable", "review", "delete", "empty", "multiple"]
)
def test_failed_or_unsafe_repair_keeps_original_no_retry(generation, failure):
    run, repair, _, db = generation
    if failure == "invalid":
        repair.return_value = changed(INVALID)
    elif failure == "unavailable":
        repair.side_effect = HTTPException(503, "Runtime unavailable")
    elif failure == "review":
        repair.return_value = changed(warnings=["Scientific decision required"])
    elif failure == "delete":
        repair.return_value = changed()
        repair.return_value["changed_files"][0]["status"] = "deleted"
    elif failure == "empty":
        repair.return_value = changed("")
    else:
        repair.return_value = changed()
        repair.return_value["changed_files"].append(
            {"path": "model.py", "content": "", "type": "py", "status": "created"}
        )
    response = run()
    assert response.content == INVALID and response.validation.status == "invalid"
    assert repair.await_count == 1 and db.commit.await_count == 1


def test_no_ai_repair_when_the_checker_is_unavailable(generation, monkeypatch):
    run, repair, _, _ = generation
    monkeypatch.setattr(authoring, "validate_aimd", Mock(side_effect=RuntimeError()))
    response = run()
    assert response.validation.status == "unavailable"
    assert response.content == INVALID
    repair.assert_not_awaited()


def test_manual_repair_rechecks_current_source_and_requires_review(monkeypatch):
    repair = AsyncMock(return_value=changed())
    monkeypatch.setattr(editor, "check_model_usage", AsyncMock())
    monkeypatch.setattr(editor, "protocol_code_edit", repair)
    params = editor.CodeEditParams(
        prompt="repair",
        files=[source(INVALID)],
        model=ChatModel(model_type=1),
        syntax_repair=True,
    )
    result = asyncio.run(
        editor.code_edit_protocol(None, SimpleNamespace(id=uuid4()), params)
    )
    assert result["risk"]["recommended_action"] == "review"
    assert "protocol.aimd:4:1" in repair.await_args.args[0]["prompt"]
    assert params.files[0].content == INVALID
    params.files = [source()]
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            editor.code_edit_protocol(None, SimpleNamespace(id=uuid4()), params)
        )
    assert error.value.status_code == 409
    assert repair.await_count == 1


def test_repair_cannot_delete_fields_by_deleting_files():
    result = changed()
    result["changed_files"][0]["status"] = "deleted"
    assert (
        authoring.validate_edit_result(result, [source(INVALID)], require_review=True)[
            "risk"
        ]["recommended_action"]
        == "block"
    )


def test_model_response_limits_block_application_instead_of_hiding_the_draft():
    result = authoring.validate_edit_result(
        changed("x" * (authoring.MAX_SOURCE_CHARS + 1)), [source()]
    )
    assert result["risk"]["recommended_action"] == "block"


def test_validation_api_auth_limits_and_ai_independence():
    app = FastAPI()
    app.include_router(editor.router)
    app.dependency_overrides[get_db_session] = lambda: None
    client = TestClient(app)
    assert (
        client.post(
            "/editor/validate_sources", json={"files": [source().model_dump()]}
        ).status_code
        == 401
    )
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    response = client.post(
        "/editor/syntax_check",
        json={"file_type": "aimd", "file_content": VALID + "notes " * 2000},
    )
    assert response.status_code == 200 and response.json()["result"]
    assert (
        client.post(
            "/editor/validate_sources", json={"files": [source(INVALID).model_dump()]}
        ).json()["status"]
        == "invalid"
    )
    for files in [
        [],
        [source().model_dump()] * 2,
        [{"path": "../protocol.aimd", "content": VALID}],
        [{"path": "protocol.aimd", "content": "x" * (authoring.MAX_SOURCE_CHARS + 1)}],
    ]:
        assert (
            client.post("/editor/validate_sources", json={"files": files}).status_code
            == 422
        )
