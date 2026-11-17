"""Offline tests must never reach model providers or depend on developer keys."""

import socket

import pytest


@pytest.fixture(autouse=True)
def block_unmarked_network(request, monkeypatch):
    if any(request.node.get_closest_marker(name) for name in ("openai", "qwen", "e2e", "integration")):
        return
    original = socket.socket.connect

    def connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError("Offline test attempted network access; mock the provider or mark the live test.")
        return original(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)


@pytest.fixture
def mock_provider_credentials(monkeypatch):
    """Credential validation stays enabled while model responses are mocked."""
    from masterbrain import configs
    from masterbrain.utils import llm

    for module in (configs, llm):
        monkeypatch.setattr(module, "OPENAI_API_KEY", "offline-test-key")
        monkeypatch.setattr(module, "DASHSCOPE_API_KEY", "offline-test-key")
