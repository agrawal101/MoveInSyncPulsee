from __future__ import annotations

import pytest

from app.llm.factory import create_llm_provider
from app.llm.provider import (
    FallbackProvider,
    LLMConfigurationError,
    OpenAIProvider,
    SarvamProvider,
)


ENV_NAMES = (
    "LLM_PROVIDER",
    "LLM_FALLBACK_PROVIDER",
    "LLM_TIMEOUT_SECONDS",
    "SARVAM_API_KEY",
    "SARVAM_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "LLM_API_KEY",
    "LLM_MODEL",
    "DEMO_MODE",
)


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_sarvam_primary_openai_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "sarvam")
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "openai")
    monkeypatch.setenv("SARVAM_API_KEY", "test-sarvam")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.setenv("SARVAM_MODEL", "sarvam-105b")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5-mini")
    provider = create_llm_provider()
    assert isinstance(provider, FallbackProvider)
    assert isinstance(provider.primary, SarvamProvider)
    assert isinstance(provider.fallback, OpenAIProvider)
    assert provider.primary.model == "sarvam-105b"
    assert provider.fallback.model == "gpt-5-mini"


def test_openai_can_be_selected_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5-mini")
    assert isinstance(create_llm_provider(), OpenAIProvider)


def test_missing_primary_configuration_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    with pytest.raises(LLMConfigurationError):
        create_llm_provider()


def test_same_provider_cannot_be_its_own_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "sarvam")
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "sarvam")
    monkeypatch.setenv("SARVAM_API_KEY", "test-sarvam")
    with pytest.raises(LLMConfigurationError):
        create_llm_provider()
