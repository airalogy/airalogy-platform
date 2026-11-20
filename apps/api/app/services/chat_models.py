from fastapi import HTTPException
from pydantic import BaseModel, computed_field

from app.config import config
from app.libs.ai_scope import active_ai_scope
from app.models.chat import ChatModel, ChatModelType

DEFAULT_CHAT_MODEL_TYPES = (
    ChatModelType.BASIC,
    ChatModelType.PLUS,
    ChatModelType.PRO,
)


class ChatCapabilities(BaseModel):
    ai_enabled: bool
    enabled_chat_models: list[ChatModelType]

    @computed_field
    @property
    def chat_model_names(self) -> dict[ChatModelType, str]:
        return {kind: ChatModel(model_type=kind).name for kind in self.enabled_chat_models}


def enabled_chat_model_types() -> tuple[ChatModelType, ...]:
    if not config.effective_ai_enabled:
        return ()

    scope = active_ai_scope.get()
    if scope:
        return tuple(kind for kind in ChatModelType if ChatModel(model_type=kind).name == scope.model)

    enabled_models: tuple[ChatModelType, ...] = ()
    if config.qwen_chat_configured:
        enabled_models = DEFAULT_CHAT_MODEL_TYPES
    if config.gpt_chat_configured:
        enabled_models = (*enabled_models, ChatModelType.GPT)
    return enabled_models


def is_chat_model_enabled(model_type: ChatModelType) -> bool:
    return model_type in enabled_chat_model_types()


def require_ai_enabled() -> None:
    if not config.effective_ai_enabled:
        raise HTTPException(status_code=503, detail="AI features are disabled")
