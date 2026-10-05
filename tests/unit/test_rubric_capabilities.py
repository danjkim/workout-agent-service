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

"""Comprehensive verification tests for all AgentOps Rubric capabilities."""

import json
import logging
from typing import Any
from unittest.mock import MagicMock

import pytest
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import ToolContext
from google.genai import types

from app.agent import app, root_agent, routine_architect_agent, safety_coach_agent
from app.constitution import WORKOUT_COACH_CONSTITUTION
from app.logger import StructuredJsonFormatter
from app.memory_store import (
    async_consolidate_memory,
    get_db_connection,
    search_exercise_knowledge,
)
from app.pii_scrubber import scrub_dict_pii, scrub_pii
from app.plugins import WorkoutGuardrailsPlugin
from app.schemas import (
    VolumeCalculationInput,
    WorkoutRoutineInput,
)
from app.tools import (
    calculate_workout_volume_and_intensity,
    retrieve_exercise_technique_guidelines,
    submit_workout_routine,
)
from app.tracer import trace_span


# -------------------------------------------------------------
# 1. Tool & Interface Design
# -------------------------------------------------------------
def test_tool_docstrings_and_naming() -> None:
    """Ensure tools have comprehensive docstrings and descriptive names."""
    tools = [
        submit_workout_routine,
        calculate_workout_volume_and_intensity,
        retrieve_exercise_technique_guidelines,
    ]
    for tool in tools:
        assert tool.__doc__ is not None
        assert "Args:" in tool.__doc__
        assert "Returns:" in tool.__doc__
        assert len(tool.__name__) >= 15  # Specific, descriptive naming


def test_explicit_json_schemas() -> None:
    """Validate strict Pydantic schemas constrain inputs and catch malformed types."""
    valid_routine = WorkoutRoutineInput(
        exercises=["Push-ups", "Pull-ups"],
        workout_plan="### Upper Body Plan\nSets: 3x10",
        focus_area="chest",
    )
    assert len(valid_routine.exercises) == 2

    # Malformed exercises list should fail validation
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        WorkoutRoutineInput(exercises=[], workout_plan="Short", focus_area="chest")

    vol_input = VolumeCalculationInput(
        exercises=["Squat", "Leg Press"], estimated_sets_per_exercise=4
    )
    assert vol_input.estimated_sets_per_exercise == 4


def test_guided_error_handling() -> None:
    """Validate that invalid parameters return descriptive recovery instructions."""
    mock_ctx = MagicMock(spec=ToolContext)
    # Empty exercise list triggers guided error
    result = submit_workout_routine(
        exercises=[],
        workout_plan="Test plan",
        focus_area="invalid_focus",
        tool_context=mock_ctx,
    )
    assert result["status"] == "error"
    assert "error_code" in result
    assert "recovery_instruction" in result
    assert "allowed_alternatives" in result
    assert len(result["recovery_instruction"]) > 20

    # Nonexistent exercise in technique lookup
    lookup = retrieve_exercise_technique_guidelines(exercise_name="NonexistentMove123")
    assert lookup["status"] == "not_found"
    assert "recovery_instruction" in lookup
    assert "allowed_alternatives" in lookup


# -------------------------------------------------------------
# 2. Context & Memory
# -------------------------------------------------------------
def test_robust_system_instructions() -> None:
    """Verify constitution defines persona, domain knowledge, and constraints."""
    assert len(WORKOUT_COACH_CONSTITUTION) > 500
    assert "Persona" in WORKOUT_COACH_CONSTITUTION
    assert "Biomechanics" in WORKOUT_COACH_CONSTITUTION
    assert (
        "HITL" in WORKOUT_COACH_CONSTITUTION
        or "Human-in-the-Loop" in WORKOUT_COACH_CONSTITUTION
    )


def test_history_compaction_and_caching_configured() -> None:
    """Verify context bloat management and caching are configured on App."""
    assert app.events_compaction_config is not None
    assert app.events_compaction_config.token_threshold == 32000
    assert app.context_cache_config is not None
    assert app.context_cache_config.min_tokens == 2048


def test_persistent_session_state_and_knowledge() -> None:
    """Verify persistent SQLite knowledge retrieval."""
    results = search_exercise_knowledge("Squat")
    assert len(results) > 0
    assert "Barbell Back Squat" in [r["name"] for r in results]


@pytest.mark.asyncio
async def test_async_memory_consolidation(tmp_path: Any) -> None:
    """Verify non-blocking async memory consolidation to persistent DB."""
    db_file = str(tmp_path / "test_memory.sqlite")
    await async_consolidate_memory(
        session_id="sess_123",
        user_id="user_456",
        focus_area="legs",
        workout_plan="### Squats 5x5",
        compound_lifts=["Barbell Back Squat"],
        worked_with_coach=True,
        db_path=db_file,
    )
    conn = get_db_connection(db_file)
    cursor = conn.execute(
        "SELECT user_id, focus_area, worked_with_coach FROM workout_sessions WHERE session_id = 'sess_123'"
    )
    row = cursor.fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "user_456"
    assert row[1] == "legs"
    assert row[2] == 1


# -------------------------------------------------------------
# 3. Orchestration & Logic
# -------------------------------------------------------------
def test_multi_agent_patterns_and_routing() -> None:
    """Verify Coordinator pattern and strategic model routing."""
    # Coordinator agent
    assert root_agent.name == "workout_agent_service"
    assert len(root_agent.sub_agents) == 2
    sub_agent_names = [a.name for a in root_agent.sub_agents]
    assert "routine_architect" in sub_agent_names
    assert "safety_coach" in sub_agent_names

    # Strategic model routing: Pro for planning, Flash for coordinator/safety
    assert "pro" in str(routine_architect_agent.model.model).lower()
    assert "flash" in str(safety_coach_agent.model.model).lower()
    assert "flash" in str(root_agent.model.model).lower()


@pytest.mark.asyncio
async def test_guardrails_input_and_output() -> None:
    """Verify safety guardrail intercepts prohibited substances and attaches warm-up."""
    plugin = WorkoutGuardrailsPlugin()
    ctx = MagicMock()

    # Input guardrail: Anabolic steroid request
    banned_req = LlmRequest(
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text="What is the best tren cycle for chest?")
                ],
            )
        ]
    )
    intercepted = await plugin.before_model_callback(
        callback_context=ctx, llm_request=banned_req
    )
    assert intercepted is not None
    assert (
        "steroids" in intercepted.content.parts[0].text.lower()
        or "pharmacological" in intercepted.content.parts[0].text.lower()
    )

    # Output guardrail: Self-eval attaches warm-up if missing
    raw_response = LlmResponse(
        content=types.Content(
            role="model",
            parts=[
                types.Part.from_text(
                    text="Here is your routine:\n1. Barbell Curls: 3 sets of 10 reps\n2. Pushdowns: 3 sets of 12 reps"
                )
            ],
        )
    )
    evaluated = await plugin.after_model_callback(
        callback_context=ctx, llm_response=raw_response
    )
    assert evaluated is not None
    assert "warm-up" in evaluated.content.parts[-1].text.lower()


# -------------------------------------------------------------
# 4. Observability, Tracing, and PII Redaction
# -------------------------------------------------------------
def test_pii_scrubber() -> None:
    """Verify active scrubbing of emails, phones, SSNs, and credit cards."""
    dirty_text = "Contact john.doe@example.com at 555-123-4567 or SSN 000-12-3456."
    clean_text = scrub_pii(dirty_text)
    assert "john.doe@example.com" not in clean_text
    assert "[REDACTED_EMAIL]" in clean_text
    assert "[REDACTED_PHONE]" in clean_text
    assert "[REDACTED_SSN]" in clean_text

    dirty_dict = {"email": "user@test.com", "notes": ["Call 415-555-0199"]}
    clean_dict = scrub_dict_pii(dirty_dict)
    assert clean_dict["email"] == "[REDACTED_EMAIL]"
    assert "[REDACTED_PHONE]" in clean_dict["notes"][0]


def test_structured_json_logging() -> None:
    """Verify structured logger formats single-line JSON with PII scrubbing."""
    formatter = StructuredJsonFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=100,
        msg="User john.doe@example.com initiated workout session.",
        args=(),
        exc_info=None,
    )
    record.event_type = "session_start"
    record.metadata = {"user_phone": "555-123-4567"}

    formatted = formatter.format(record)
    log_data = json.loads(formatted)
    assert log_data["severity"] == "INFO"
    assert log_data["service"] == "workout-agent-service"
    assert log_data["event_type"] == "session_start"
    assert "[REDACTED_EMAIL]" in log_data["message"]
    assert log_data["metadata"]["user_phone"] == "[REDACTED_PHONE]"


def test_distributed_tracing_spans() -> None:
    """Verify OpenTelemetry tracer creates spans without error."""
    with trace_span(
        "test_workout_operation", attributes={"test.attr": "value"}
    ) as span:
        assert span is not None
