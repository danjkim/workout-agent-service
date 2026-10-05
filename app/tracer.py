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

"""Distributed Tracing utilities using OpenTelemetry."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

TRACER_NAME = "workout_agent_service"


def get_tracer(name: str = TRACER_NAME) -> trace.Tracer:
    """Return an OpenTelemetry tracer instance."""
    return trace.get_tracer(name)


@contextlib.contextmanager
def trace_span(
    span_name: str,
    attributes: dict[str, Any] | None = None,
    tracer: trace.Tracer | None = None,
) -> Iterator[trace.Span]:
    """Context manager for creating a linked OpenTelemetry span.

    Args:
        span_name: Identifier for the traced operation.
        attributes: Key-value attributes to attach to the span.
        tracer: Optional tracer; defaults to TRACER_NAME.

    Yields:
        The active OpenTelemetry Span.
    """
    active_tracer = tracer or get_tracer()
    with active_tracer.start_as_current_span(span_name) as span:
        if attributes:
            for k, v in attributes.items():
                if v is not None:
                    span.set_attribute(
                        k, str(v) if not isinstance(v, (bool, int, float, str)) else v
                    )
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise
