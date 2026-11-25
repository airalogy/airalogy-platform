import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from app.config import config
from app.models.chat import ChatContext, ChatModel, ChatModelType, ChatUserMessage
from app.routers.chats.qa import QAChatMessageParams, send_qa_chat_message
from app.routers.chats.utils import check_model_usage
from app.services.chat_models import (
    ChatCapabilities,
    enabled_chat_model_types,
    is_chat_model_enabled,
    require_ai_enabled,
)
from fastapi import HTTPException


def test_gpt_is_excluded_when_not_enabled(monkeypatch):
    monkeypatch.setattr(config, "AI_ENABLED", None)
    monkeypatch.setattr(config, "DASHSCOPE_API_KEY", "test-dashscope-key")
    monkeypatch.setattr(config, "ENABLE_GPT_MODEL", False)

    assert enabled_chat_model_types() == (
        ChatModelType.BASIC,
        ChatModelType.PLUS,
        ChatModelType.PRO,
    )
    assert is_chat_model_enabled(ChatModelType.GPT) is False


def test_gpt_is_available_when_explicitly_enabled(monkeypatch):
    monkeypatch.setattr(config, "AI_ENABLED", None)
    monkeypatch.setattr(config, "DASHSCOPE_API_KEY", "")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setattr(config, "ENABLE_GPT_MODEL", True)

    assert enabled_chat_model_types() == (ChatModelType.GPT,)
    caps = ChatCapabilities(ai_enabled=True, enabled_chat_models=list(enabled_chat_model_types()))
    assert caps.model_dump(mode="json")["chat_model_names"] == {"4": "gpt-4.1"}
    assert is_chat_model_enabled(ChatModelType.GPT) is True


def test_all_chat_models_are_hidden_when_ai_is_disabled(monkeypatch):
    monkeypatch.setattr(config, "AI_ENABLED", False)
    monkeypatch.setattr(config, "DASHSCOPE_API_KEY", "test-dashscope-key")

    assert enabled_chat_model_types() == ()
    assert ChatCapabilities(ai_enabled=False, enabled_chat_models=[]).chat_model_names == {}
    assert is_chat_model_enabled(ChatModelType.BASIC) is False

    with pytest.raises(HTTPException, match="AI features are disabled") as error:
        require_ai_enabled()
    assert error.value.status_code == 503


def test_disabled_gpt_request_is_rejected_before_usage_lookup(monkeypatch):
    monkeypatch.setattr(config, "AI_ENABLED", None)
    monkeypatch.setattr(config, "DASHSCOPE_API_KEY", "test-dashscope-key")
    monkeypatch.setattr(config, "ENABLE_GPT_MODEL", False)

    with pytest.raises(HTTPException, match="Chat model is not enabled") as error:
        asyncio.run(
            check_model_usage(
                None,  # type: ignore[arg-type]
                None,  # type: ignore[arg-type]
                ChatModel(model_type=ChatModelType.GPT),
            )
        )

    assert error.value.status_code == 400


def test_new_qa_chat_has_model_before_first_flush(monkeypatch):
    model = ChatModel(model_type=ChatModelType.PLUS, enable_thinking=True)
    created_chats = []

    def add(chat):
        created_chats.append(chat)

    async def flush():
        assert created_chats[0].model == model.model_dump()

    db_session = SimpleNamespace(
        add=Mock(side_effect=add),
        flush=AsyncMock(side_effect=flush),
    )
    current_user = SimpleNamespace(id=uuid.uuid4())
    monkeypatch.setattr("app.routers.chats.qa.check_model_usage", AsyncMock())

    response = asyncio.run(
        send_qa_chat_message(
            db_session=db_session,
            current_user=current_user,
            params=QAChatMessageParams(
                context=ChatContext(),
                message=ChatUserMessage(content="Hello"),
                model=model,
            ),
        )
    )

    assert response.status_code == 200
    db_session.flush.assert_awaited_once()


def test_readonly_record_revision_reaches_the_analysis_context():
    from app.routers.chats.context_inject import build_current_recorder_record_context_message

    context = ChatContext.model_validate({
        "ephemeral_context": {"current_recorder_record": {
            "enabled": True, "readonly": True, "record_id": "synthetic-record",
            "record_revision": 2, "protocol_version": "0.3.0",
            "record_data": {"var": {"reading": 0}},
        }}
    })
    record = context.ephemeral_context.current_recorder_record.model_dump()
    message = build_current_recorder_record_context_message(record)
    assert "saved read-only Record revision" in message["content"]
    serialized = message["content"].split("```json\n", 1)[1].rsplit("\n```", 1)[0]
    payload = json.loads(serialized)
    assert payload["record_data"] == {"var": {"reading": 0}}
    for name in ("protocol_version", "record_revision", "record_id"):
        assert payload["metadata"][name] == record[name]
