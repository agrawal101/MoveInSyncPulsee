from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from time import perf_counter
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError


class LLMConfigurationError(RuntimeError):
    pass


class LLMProviderError(RuntimeError):
    pass


class LLMAuthenticationError(LLMProviderError):
    pass


class LLMRateLimitError(LLMProviderError):
    pass


class LLMTimeoutError(LLMProviderError):
    pass


class LLMResponseError(LLMProviderError):
    pass


class LLMProviderChainError(LLMProviderError):
    pass


@dataclass(frozen=True)
class LLMResult:
    output: BaseModel
    model: str
    latency_ms: float
    provider: str = "unknown"
    input_tokens: int | None = None
    output_tokens: int | None = None
    fallback_used: bool = False
    error_category: str | None = None
    validation_result: str = "passed"


class LLMProvider(ABC):
    provider_name = "unknown"

    @abstractmethod
    def generate_structured(
        self,
        *,
        system_prompt: str,
        task: str,
        evidence: dict[str, Any],
        response_model: type[BaseModel],
        workflow: str,
    ) -> LLMResult:
        """Generate schema-valid narrative from deterministic evidence."""


class SarvamProvider(LLMProvider):
    """Sarvam v1 Chat Completions with strict JSON Schema output."""

    provider_name = "sarvam"
    OUTPUT_LIMITS = {"query": 1400, "investigate": 1700, "report": 2400}
    TRANSIENT_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}

    def __init__(
        self,
        api_key: str,
        model: str = "sarvam-105b",
        timeout_seconds: float = 18.0,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self.client = client or httpx.Client(
            base_url="https://api.sarvam.ai",
            timeout=timeout_seconds,
            headers={
                "api-subscription-key": api_key,
                "Content-Type": "application/json",
            },
        )

    @staticmethod
    def _error_for_status(status_code: int) -> LLMProviderError:
        if status_code == 403:
            return LLMAuthenticationError("Sarvam rejected the configured API key.")
        if status_code == 429:
            return LLMRateLimitError("Sarvam rate limit or quota was exceeded.")
        return LLMProviderError(f"Sarvam returned HTTP {status_code}.")

    @staticmethod
    def _repair_instruction(error: Exception) -> str:
        detail = str(error).replace("\n", " ")[:600]
        return (
            "A prior response failed schema validation. Repair the response once. "
            "Use only supplied evidence, preserve exact evidence values, and return strict JSON. "
            "Be terse. Evidence descriptions must contain no values and stay under twelve words. "
            f"Validation issue: {detail}"
        )

    def generate_structured(
        self,
        *,
        system_prompt: str,
        task: str,
        evidence: dict[str, Any],
        response_model: type[BaseModel],
        workflow: str,
    ) -> LLMResult:
        evidence_json = json.dumps(evidence, separators=(",", ":"), default=str)
        user_content = f"Task:\n{task}\n\nApproved deterministic evidence:\n{evidence_json}"
        started = perf_counter()
        last_transport_error: httpx.RequestError | None = None

        for attempt in range(2):
            request = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.2,
                "reasoning_effort": None,
                "max_tokens": self.OUTPUT_LIMITS.get(workflow, 900),
                "stream": False,
                "n": 1,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "moveinsync_agent_response",
                        "description": "Grounded enterprise mobility analysis",
                        "schema": response_model.model_json_schema(),
                        "strict": True,
                    },
                },
            }
            try:
                response = self.client.post("/v1/chat/completions", json=request)
            except httpx.TimeoutException as exc:
                last_transport_error = exc
                if attempt == 0:
                    continue
                raise LLMTimeoutError("Sarvam request exceeded configured timeout.") from exc
            except httpx.RequestError as exc:
                last_transport_error = exc
                if attempt == 0:
                    continue
                raise LLMProviderError("Unable to connect to Sarvam.") from exc

            if response.status_code >= 400:
                error = self._error_for_status(response.status_code)
                if response.status_code in self.TRANSIENT_STATUS_CODES and attempt == 0:
                    continue
                raise error

            try:
                body = response.json()
                content = body["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("Sarvam returned empty structured content.")
                parsed = response_model.model_validate_json(content)
                usage = body.get("usage") or {}
                return LLMResult(
                    output=parsed,
                    provider=self.provider_name,
                    model=str(body.get("model") or self.model),
                    latency_ms=round((perf_counter() - started) * 1000, 2),
                    input_tokens=usage.get("prompt_tokens"),
                    output_tokens=usage.get("completion_tokens"),
                    validation_result="repaired" if attempt else "passed",
                )
            except (KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
                if attempt == 0:
                    user_content += "\n\n" + self._repair_instruction(exc)
                    continue
                raise LLMResponseError(
                    "Sarvam structured output failed validation after one repair attempt."
                ) from exc

        if isinstance(last_transport_error, httpx.TimeoutException):
            raise LLMTimeoutError("Sarvam request exceeded configured timeout.")
        raise LLMProviderError("Sarvam request failed after one bounded retry.")


class OpenAIProvider(LLMProvider):
    provider_name = "openai"
    OUTPUT_LIMITS = {"query": 900, "investigate": 1300, "report": 1500}

    def __init__(self, api_key: str, model: str, timeout_seconds: float = 18.0) -> None:
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=1)
        self.model = model

    def generate_structured(
        self,
        *,
        system_prompt: str,
        task: str,
        evidence: dict[str, Any],
        response_model: type[BaseModel],
        workflow: str,
    ) -> LLMResult:
        from openai import APIConnectionError, APIStatusError, APITimeoutError

        payload = json.dumps(evidence, separators=(",", ":"), default=str)
        prompt = f"Task:\n{task}\n\nApproved deterministic evidence:\n{payload}"
        started = perf_counter()
        for attempt in range(2):
            try:
                completion = self.client.responses.parse(
                    model=self.model,
                    instructions=system_prompt,
                    input=prompt,
                    text_format=response_model,
                    max_output_tokens=self.OUTPUT_LIMITS.get(workflow, 900),
                    store=False,
                )
                if completion.output_parsed is None:
                    if attempt == 0:
                        prompt += (
                            "\n\nPrevious response was invalid. Return schema-valid output "
                            "using only supplied evidence."
                        )
                        continue
                    raise LLMResponseError(
                        "OpenAI returned no valid structured output after one repair attempt."
                    )
                usage = completion.usage
                return LLMResult(
                    output=completion.output_parsed,
                    provider=self.provider_name,
                    model=self.model,
                    latency_ms=round((perf_counter() - started) * 1000, 2),
                    input_tokens=getattr(usage, "input_tokens", None),
                    output_tokens=getattr(usage, "output_tokens", None),
                    validation_result="repaired" if attempt else "passed",
                )
            except APITimeoutError as exc:
                raise LLMTimeoutError("OpenAI request exceeded configured timeout.") from exc
            except (ValidationError, LLMResponseError) as exc:
                if attempt == 0:
                    prompt += (
                        "\n\nPrevious response failed schema validation. Repair it once "
                        "without adding facts or numbers."
                    )
                    continue
                raise LLMResponseError(
                    "OpenAI structured output failed validation after one repair attempt."
                ) from exc
            except APIConnectionError as exc:
                raise LLMProviderError("Unable to connect to OpenAI.") from exc
            except APIStatusError as exc:
                if exc.status_code in {401, 403}:
                    raise LLMAuthenticationError(
                        "OpenAI rejected the configured API key."
                    ) from exc
                if exc.status_code == 429:
                    raise LLMRateLimitError(
                        "OpenAI rate limit or quota was exceeded."
                    ) from exc
                raise LLMProviderError(
                    f"OpenAI returned HTTP {exc.status_code}."
                ) from exc
        raise LLMResponseError("OpenAI structured output generation failed.")


class AnthropicProvider(LLMProvider):
    """Anthropic Messages API with SDK-native Pydantic structured output."""

    provider_name = "anthropic"
    OUTPUT_LIMITS = {"query": 1400, "investigate": 1700, "report": 2400}

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-5",
        timeout_seconds: float = 18.0,
    ) -> None:
        from anthropic import Anthropic

        # Repairs are bounded here; disable hidden SDK retries.
        self.client = Anthropic(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=0,
        )
        self.model = model

    def generate_structured(
        self,
        *,
        system_prompt: str,
        task: str,
        evidence: dict[str, Any],
        response_model: type[BaseModel],
        workflow: str,
    ) -> LLMResult:
        from anthropic import APIConnectionError, APIStatusError, APITimeoutError

        # The graph supplies the same compact, ID-annotated aggregate evidence used
        # for Sarvam. This provider never loads mobility files or raw records.
        payload = json.dumps(evidence, separators=(",", ":"), default=str)
        prompt = f"Task:\n{task}\n\nApproved deterministic evidence:\n{payload}"
        started = perf_counter()
        for attempt in range(2):
            try:
                message = self.client.messages.parse(
                    model=self.model,
                    max_tokens=self.OUTPUT_LIMITS.get(workflow, 1400),
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}],
                    output_format=response_model,
                )
                parsed = getattr(message, "parsed_output", None)
                if parsed is None:
                    raise LLMResponseError(
                        "Anthropic returned no schema-valid structured output."
                    )
                usage = getattr(message, "usage", None)
                return LLMResult(
                    output=parsed,
                    provider=self.provider_name,
                    model=str(getattr(message, "model", None) or self.model),
                    latency_ms=round((perf_counter() - started) * 1000, 2),
                    input_tokens=getattr(usage, "input_tokens", None),
                    output_tokens=getattr(usage, "output_tokens", None),
                    validation_result="repaired" if attempt else "passed",
                )
            except APITimeoutError as exc:
                raise LLMTimeoutError(
                    "Anthropic request exceeded configured timeout."
                ) from exc
            except APIConnectionError as exc:
                raise LLMProviderError("Unable to connect to Anthropic.") from exc
            except APIStatusError as exc:
                if exc.status_code in {401, 403}:
                    raise LLMAuthenticationError(
                        "Anthropic rejected the configured API key."
                    ) from exc
                if exc.status_code == 429:
                    raise LLMRateLimitError(
                        "Anthropic rate limit or quota was exceeded."
                    ) from exc
                raise LLMProviderError(
                    f"Anthropic returned HTTP {exc.status_code}."
                ) from exc
            except (ValidationError, LLMResponseError) as exc:
                if attempt == 0:
                    detail = str(exc).replace("\n", " ")[:500]
                    prompt += (
                        "\n\nRepair the previous response once. Return the exact schema, "
                        "copy evidence_id, metric, and values from one evidence object, "
                        "and add no numeric prose. Validation issue: "
                        + detail
                    )
                    continue
                raise LLMResponseError(
                    "Anthropic structured output failed after one repair attempt."
                ) from exc
        raise LLMResponseError("Anthropic structured output generation failed.")


class FallbackProvider(LLMProvider):
    """Try one provider, then one configured fallback without duplicating agent logic."""

    provider_name = "provider_chain"

    def __init__(self, primary: LLMProvider, fallback: LLMProvider) -> None:
        self.primary = primary
        self.fallback = fallback

    def generate_structured(self, **kwargs: Any) -> LLMResult:
        started = perf_counter()
        try:
            return self.primary.generate_structured(**kwargs)
        except LLMProviderError as primary_error:
            try:
                result = self.fallback.generate_structured(**kwargs)
            except LLMProviderError as fallback_error:
                raise LLMProviderChainError(
                    f"Both {self.primary.provider_name} and "
                    f"{self.fallback.provider_name} synthesis failed."
                ) from fallback_error
            return replace(
                result,
                latency_ms=round((perf_counter() - started) * 1000, 2),
                fallback_used=True,
                error_category=type(primary_error).__name__,
            )
