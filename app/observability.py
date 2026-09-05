from __future__ import annotations

import json
import logging


class JsonFormatter(logging.Formatter):
    """Compact agent logs; credentials, prompts, questions, and evidence are excluded."""

    FIELDS = (
        "request_id",
        "endpoint",
        "workflow",
        "tool",
        "provider",
        "model",
        "duration_ms",
        "input_tokens",
        "output_tokens",
        "fallback_used",
        "validation_result",
        "error_category",
        "field_path",
        "rejected_value",
        "validation_rule",
        "nearest_supported_value",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        payload.update(
            {
                field: getattr(record, field)
                for field in self.FIELDS
                if hasattr(record, field)
            }
        )
        if record.exc_info:
            payload["exception"] = record.exc_info[0].__name__
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)
