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

"""ADK Plugins for Security Guardrails, Observability, and Intent/Outcome Logging."""

from __future__ import annotations

import re
import time
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.tools import BaseTool, ToolContext
from google.genai import types

from app.logger import get_structured_logger, log_intent, log_outcome
from app.pii_scrubber import scrub_pii
from app.tracer import get_tracer

logger = get_structured_logger("workout_plugins")
tracer = get_tracer("workout_guardrails_and_observability")

# Security and Safety Guardrail Patterns
_PROHIBITED_SUBSTANCES = re.compile(
    r"\b(anavar|dbol|dianabol|trenbolone|tren|winstrol|deca|clenbuterol|sarms|testosterone cypionate cycle)\b",
    re.IGNORECASE,
)
_ACUTE_MEDICAL_TRAUMA = re.compile(
    r"\b(bone\s+broken|fracture|compound\s+fracture|dislocated\s+shoulder|torn\s+pectoral|internal\s+bleeding)\b",
    re.IGNORECASE,
)


class WorkoutGuardrailsPlugin(BasePlugin):
    """Enforces safety, ethical, and self-evaluation guardrails on inputs and outputs."""

    def __init__(self, name: str = "workout_guardrails_plugin"):
        super().__init__(name=name)

    async def before_model_callback(
        self,
        *,
        callback_context: CallbackContext,
        llm_request: LlmRequest,
    ) -> LlmResponse | None:
        """Input Guardrail: Intercept hazardous or prohibited requests before model reasoning."""
        with tracer.start_as_current_span("guardrail:input_security_check") as span:
            # Inspect the latest user prompt text
            user_text = ""
            if llm_request.contents:
                for content in llm_request.contents:
                    if content.role == "user" and content.parts:
                        for part in content.parts:
                            if hasattr(part, "text") and part.text:
                                user_text += " " + part.text

            span.set_attribute("guardrail.inspected_length", len(user_text))

            # 1. Prohibited Pharmacological Substances Check
            if _PROHIBITED_SUBSTANCES.search(user_text):
                span.set_attribute("guardrail.violation", "prohibited_substances")
                logger.warning(
                    "Security guardrail triggered: Prohibited substances detected in user prompt.",
                    extra={
                        "event_type": "guardrail_violation",
                        "metadata": {"reason": "prohibited_substances"},
                    },
                )
                refusal_text = (
                    "I cannot assist with requests involving anabolic steroids, SARMs, or unprescribed "
                    "performance-enhancing pharmacological substances. As a certified fitness coach, I only "
                    "provide evidence-based natural training and nutrition guidance."
                )
                return LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=refusal_text)],
                    )
                )

            # 2. Acute Medical Trauma Check
            if _ACUTE_MEDICAL_TRAUMA.search(user_text):
                span.set_attribute("guardrail.violation", "acute_medical_trauma")
                logger.warning(
                    "Safety guardrail triggered: Acute medical trauma detected in user prompt.",
                    extra={
                        "event_type": "guardrail_violation",
                        "metadata": {"reason": "acute_medical_trauma"},
                    },
                )
                refusal_text = (
                    "It sounds like you may be experiencing an acute physical injury or medical emergency. "
                    "I cannot provide medical diagnosis or rehabilitation protocols. Please seek immediate "
                    "evaluation from a licensed physician or emergency medical professional."
                )
                return LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=refusal_text)],
                    )
                )

            return None

    async def after_model_callback(
        self,
        *,
        callback_context: CallbackContext,
        llm_response: LlmResponse,
    ) -> LlmResponse | None:
        """Self-Evaluation Guardrail: Verify model response adheres to coaching standards."""
        with tracer.start_as_current_span("guardrail:output_self_eval") as span:
            if not llm_response.content or not llm_response.content.parts:
                return None

            response_text = "".join(
                part.text
                for part in llm_response.content.parts
                if hasattr(part, "text") and part.text
            )

            # Self-Evaluation: Check if workout plan was generated without warm-up guidance
            has_exercise_table = (
                "sets" in response_text.lower() and "reps" in response_text.lower()
            )
            has_warmup = (
                "warm" in response_text.lower() or "mobility" in response_text.lower()
            )

            if has_exercise_table and not has_warmup:
                span.set_attribute(
                    "guardrail.evaluation_adjustment", "added_warmup_guideline"
                )
                logger.info("Self-eval guardrail: Attaching standard warm-up advisory.")
                warmup_addition = (
                    "\n\n> **Coach Safety Note**: Always precede working sets with 5-10 minutes of dynamic warm-up "
                    "(e.g., arm circles, leg swings, bodyweight squats) and progressive warm-up sets."
                )
                new_parts = list(llm_response.content.parts)
                new_parts.append(types.Part.from_text(text=warmup_addition))
                return LlmResponse(
                    content=types.Content(role="model", parts=new_parts),
                    usage_metadata=llm_response.usage_metadata,
                )

            return None


class ObservabilityAndIntentPlugin(BasePlugin):
    """Tracks intent vs. outcome for tool executions, OpenTelemetry spans, and structured logging."""

    def __init__(self, name: str = "observability_intent_plugin"):
        super().__init__(name=name)
        self._tool_spans: dict[str, Any] = {}
        self._tool_start_times: dict[str, float] = {}

    async def before_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
    ) -> dict[str, Any] | None:
        """Log explicit tool execution intent and start OpenTelemetry span."""
        tool_name = getattr(tool, "name", str(tool))
        call_key = f"{tool_name}_{id(tool_context)}"

        # Start child span
        span = tracer.start_span(
            f"tool:{tool_name}",
            attributes={"adk.tool.name": tool_name},
        )
        self._tool_spans[call_key] = span
        self._tool_start_times[call_key] = time.perf_counter()

        # Capture intentional action in structured JSON logs
        intended_action = (
            f"Executing {tool_name} with arguments: {list(tool_args.keys())}"
        )
        log_intent(
            tool_name=tool_name,
            args=tool_args,
            intended_action=intended_action,
            logger=logger,
        )
        return None

    async def after_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
        result: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Log explicit tool execution outcome and finish OpenTelemetry span."""
        tool_name = getattr(tool, "name", str(tool))
        call_key = f"{tool_name}_{id(tool_context)}"

        start_time = self._tool_start_times.pop(call_key, time.perf_counter())
        duration_ms = (time.perf_counter() - start_time) * 1000

        span = self._tool_spans.pop(call_key, None)
        if span:
            span.set_attribute("adk.tool.duration_ms", duration_ms)
            status_val = (
                result.get("status", "success")
                if isinstance(result, dict)
                else "completed"
            )
            span.set_attribute("adk.tool.status", status_val)
            span.end()

        status = (
            result.get("status", "success") if isinstance(result, dict) else "completed"
        )
        summary = (
            result.get("message")
            or result.get("status")
            or f"Result contains {len(result)} keys"
            if isinstance(result, dict)
            else str(result)[:100]
        )
        log_outcome(
            tool_name=tool_name,
            status=status,
            duration_ms=duration_ms,
            result_summary=summary,
            logger=logger,
        )
        return None

    async def on_tool_error_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
        error: Exception,
    ) -> dict[str, Any] | None:
        """Capture tool execution error in logs and trace spans."""
        tool_name = getattr(tool, "name", str(tool))
        call_key = f"{tool_name}_{id(tool_context)}"

        span = self._tool_spans.pop(call_key, None)
        if span:
            span.record_exception(error)
            span.end()

        logger.error(
            f"Tool execution failed for {tool_name}: {error}",
            extra={
                "event_type": "tool_error",
                "metadata": {
                    "tool_name": tool_name,
                    "error_type": type(error).__name__,
                    "error_message": scrub_pii(str(error)),
                },
            },
        )
        return None
