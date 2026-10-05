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

"""Integration test for Human-in-the-Loop pause and resume."""

import pytest
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agent import app


@pytest.mark.asyncio
async def test_hitl_pause_and_resume() -> None:
    """Test that a routine with heavy compound lifts pauses for a coach and resumes on confirmation."""
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name=app.name, user_id="test_user"
    )
    runner = Runner(
        app=app,
        session_service=session_service,
        auto_create_session=True,
    )

    # Turn 1: User requests routine with barbell squats
    message = types.Content(
        role="user",
        parts=[
            types.Part.from_text(
                text="Design a leg day workout for me today focusing on heavy barbell back squats."
            )
        ],
    )

    requested_confirmations = {}
    function_call_id = None
    confirmation_fc_id = None

    async for event in runner.run_async(
        session_id=session.id, user_id="test_user", new_message=message
    ):
        if event.actions and event.actions.requested_tool_confirmations:
            requested_confirmations = event.actions.requested_tool_confirmations
        if event.content:
            for part in event.content.parts or []:
                if (
                    part.function_call
                    and part.function_call.name == "submit_workout_routine"
                ):
                    function_call_id = part.function_call.id
                if (
                    part.function_call
                    and part.function_call.name == "adk_request_confirmation"
                ):
                    confirmation_fc_id = part.function_call.id

    assert len(requested_confirmations) > 0, (
        "Expected human-in-the-loop tool confirmation to be requested"
    )
    confirmation_key = next(iter(requested_confirmations))
    conf = requested_confirmations[confirmation_key]
    assert "coach" in conf.hint.lower()

    # Turn 2: User confirms they want to work with a coach
    call_id = confirmation_fc_id or function_call_id or confirmation_key
    response_name = (
        "adk_request_confirmation" if confirmation_fc_id else "submit_workout_routine"
    )
    resume_part = types.Part(
        function_response=types.FunctionResponse(
            name=response_name,
            id=call_id,
            response={"confirmed": True},
        )
    )
    resume_message = types.Content(role="user", parts=[resume_part])

    has_final_response = False
    final_text = ""
    async for event in runner.run_async(
        session_id=session.id, user_id="test_user", new_message=resume_message
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    has_final_response = True
                    final_text += part.text

    assert has_final_response, (
        "Expected final response after resuming the paused session"
    )
    assert len(final_text) > 0
