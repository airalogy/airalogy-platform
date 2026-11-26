from typing import Literal, Optional

from masterbrain.providers.registry import QwenFlashModel
from pydantic import BaseModel


class SupportedModels(BaseModel):
    """Supported model configurations"""

    name: Literal[
        QwenFlashModel,
        "qwen3.5-plus",
        "qwen3-max",
        "gpt-4.1",
        "gpt-4o-mini",
    ]
    enable_thinking: bool = False
    enable_search: bool = False


DEFAULT_MODEL = SupportedModels(
    name="qwen3.5-flash",
    enable_thinking=False,
    enable_search=False,
)


class AssignerProtocolMessage(BaseModel):
    use_model: SupportedModels = DEFAULT_MODEL
    protocol_aimd: Optional[str] = None
    protocol_model: Optional[str] = None
