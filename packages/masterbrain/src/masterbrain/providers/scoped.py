"""Provider credentials for one embedded host operation, isolated across async tasks."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from .registry import DEFAULT_PROVIDER_BASE_URL, ProviderName, detect_model_provider


@dataclass(frozen=True)
class ProviderCredential:
    provider: ProviderName
    key: str = field(repr=False)
    endpoint: str | None = None
    chat_model: str | None = None

    @property
    def base_url(self) -> str:
        return self.endpoint or DEFAULT_PROVIDER_BASE_URL[self.provider]


_credential: ContextVar[ProviderCredential | None] = ContextVar(
    "masterbrain_provider_credential", default=None
)


def current_credential(model: str | None = None) -> ProviderCredential | None:
    value = _credential.get()
    if value and model and detect_model_provider(model) != value.provider:
        raise ValueError("Selected organization provider does not support this model")
    return value


@contextmanager
def bind_credential(value: ProviderCredential | None) -> Iterator[None]:
    token = _credential.set(value)
    try:
        yield
    finally:
        _credential.reset(token)
