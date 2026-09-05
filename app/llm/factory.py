from __future__ import annotations

import os

from app.llm.provider import (
    AnthropicProvider,
    FallbackProvider,
    LLMConfigurationError,
    LLMProvider,
    LLMProviderError,
    OpenAIProvider,
    SarvamProvider,
)


class UnavailableProvider(LLMProvider):
    provider_name = "unavailable"

    def generate_structured(self, **_: object):
        raise LLMProviderError("Demo mode requested deterministic fallback.")


def demo_mode_enabled() -> bool:
    return os.getenv("DEMO_MODE", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _timeout_seconds() -> float:
    raw = os.getenv("LLM_TIMEOUT_SECONDS", "18").strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise LLMConfigurationError("LLM_TIMEOUT_SECONDS must be numeric.") from exc
    if value <= 0 or value > 120:
        raise LLMConfigurationError("LLM_TIMEOUT_SECONDS must be between 0 and 120.")
    return value


def _build_provider(name: str, timeout_seconds: float) -> LLMProvider:
    if name == "sarvam":
        key = os.getenv("SARVAM_API_KEY", "").strip()
        if not key:
            raise LLMConfigurationError(
                "SARVAM_API_KEY is required when LLM_PROVIDER is sarvam."
            )
        model = os.getenv("SARVAM_MODEL", "sarvam-105b").strip()
        return SarvamProvider(key, model, timeout_seconds)

    if name == "openai":
        # Legacy LLM_* aliases remain accepted for existing local setups.
        key = (
            os.getenv("OPENAI_API_KEY", "").strip()
            or os.getenv("LLM_API_KEY", "").strip()
        )
        if not key:
            raise LLMConfigurationError(
                "OPENAI_API_KEY is required when an OpenAI provider is configured."
            )
        model = (
            os.getenv("OPENAI_MODEL", "").strip()
            or os.getenv("LLM_MODEL", "gpt-5-mini").strip()
        )
        return OpenAIProvider(key, model, timeout_seconds)

    if name == "anthropic":
        key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise LLMConfigurationError(
                "ANTHROPIC_API_KEY is required when Anthropic is configured."
            )
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5").strip()
        return AnthropicProvider(key, model, timeout_seconds)

    raise LLMConfigurationError(f"Unsupported LLM provider: {name}")


def create_llm_provider() -> LLMProvider:
    primary_name = os.getenv("LLM_PROVIDER", "").strip().lower()
    if not primary_name:
        if demo_mode_enabled():
            return UnavailableProvider()
        raise LLMConfigurationError(
            "LLM_PROVIDER is required. Use sarvam, openai, anthropic, or enable DEMO_MODE."
        )

    timeout_seconds = _timeout_seconds()
    try:
        primary = _build_provider(primary_name, timeout_seconds)
    except LLMConfigurationError:
        if demo_mode_enabled():
            return UnavailableProvider()
        raise

    fallback_name = os.getenv("LLM_FALLBACK_PROVIDER", "").strip().lower()
    if not fallback_name:
        return primary
    if fallback_name == primary_name:
        raise LLMConfigurationError(
            "LLM_FALLBACK_PROVIDER must differ from LLM_PROVIDER."
        )
    fallback = _build_provider(fallback_name, timeout_seconds)
    return FallbackProvider(primary, fallback)


def is_llm_configured() -> bool:
    primary_name = os.getenv("LLM_PROVIDER", "").strip().lower()
    if primary_name == "sarvam":
        return bool(os.getenv("SARVAM_API_KEY", "").strip())
    if primary_name == "openai":
        return bool(
            os.getenv("OPENAI_API_KEY", "").strip()
            or os.getenv("LLM_API_KEY", "").strip()
        )
    if primary_name == "anthropic":
        return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())
    return False
