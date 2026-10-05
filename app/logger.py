# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Structured JSON Logging with PII Scrubbing and Distributed Tracing Correlation."""

from __future__ import annotations

import datetime
import json
import logging
import sys
from typing import Any

from app.pii_scrubber import scrub_dict_pii, scrub_pii

SERVICE_NAME = "workout-agent-service"


def _get_current_trace_context() -> tuple[str | None, str | None]:
    """Retrieve active OpenTelemetry trace_id and span_id if available."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            ctx = span.get_span_context()
            trace_id = f"{ctx.trace_id:032x}"
            span_id = f"{ctx.span_id:016x}"
            return trace_id, span_id
    except Exception:
        pass
    return None, None


class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as structured, single-line JSON with PII scrubbing."""

    def format(self, record: logging.LogRecord) -> str:
        trace_id, span_id = _get_current_trace_context()

        # Build base structured dictionary
        payload: dict[str, Any] = {
            "timestamp": datetime.datetime.fromtimestamp(
                record.created, tz=datetime.UTC
            ).isoformat(),
            "severity": record.levelname,
            "service": SERVICE_NAME,
            "logger": record.name,
            "message": scrub_pii(record.getMessage()),
        }

        if trace_id:
            payload["trace_id"] = trace_id
        if span_id:
            payload["span_id"] = span_id

        # Attach custom metadata passed via extra
        if hasattr(record, "event_type"):
            payload["event_type"] = record.event_type
        if hasattr(record, "metadata") and isinstance(record.metadata, dict):
            payload["metadata"] = scrub_dict_pii(record.metadata)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def get_structured_logger(name: str = "workout_agent_service") -> logging.Logger:
    """Configures and returns a structured JSON logger."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredJsonFormatter())
        logger.addHandler(handler)
        logger.propagate = False

    return logger


_default_logger = get_structured_logger()


def log_intent(
    tool_name: str,
    args: dict[str, Any],
    intended_action: str,
    logger: logging.Logger | None = None,
) -> None:
    """Explicitly capture the agent's intent before executing a tool."""
    target_logger = logger or _default_logger
    target_logger.info(
        f"Tool execution intent: {tool_name}",
        extra={
            "event_type": "tool_intent",
            "metadata": {
                "tool_name": tool_name,
                "intended_action": intended_action,
                "input_args": args,
            },
        },
    )


def log_outcome(
    tool_name: str,
    status: str,
    duration_ms: float,
    result_summary: Any,
    logger: logging.Logger | None = None,
) -> None:
    """Explicitly capture the tool execution outcome after completion."""
    target_logger = logger or _default_logger
    target_logger.info(
        f"Tool execution outcome: {tool_name} [{status}]",
        extra={
            "event_type": "tool_outcome",
            "metadata": {
                "tool_name": tool_name,
                "status": status,
                "duration_ms": round(duration_ms, 2),
                "result_summary": result_summary,
            },
        },
    )
