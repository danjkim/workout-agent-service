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

from unittest.mock import MagicMock

from google.adk.tools import ToolContext
from google.adk.tools.tool_confirmation import ToolConfirmation

from app.tools import submit_workout_routine


def test_submit_workout_routine_instant_approval() -> None:
    """Test that a routine without bench press, squats, or deadlifts is instantly approved."""
    mock_context = MagicMock(spec=ToolContext)
    mock_context.tool_confirmation = None

    exercises = ["Bicep Curls", "Tricep Pushdowns", "Lateral Raises"]
    workout_plan = "### Arms & Shoulders\n- Bicep Curls: 3x12\n- Tricep Pushdowns: 3x12"

    result = submit_workout_routine(
        exercises=exercises,
        workout_plan=workout_plan,
        focus_area="arms",
        tool_context=mock_context,
    )

    assert result["status"] == "instantly_approved"
    assert "instantly approved" in result["message"]
    assert result["workout_plan"] == workout_plan
    mock_context.request_confirmation.assert_not_called()


def test_submit_workout_routine_requires_coach_pause_squat() -> None:
    """Test that a routine with squats triggers HITL pause to prompt for a coach."""
    mock_context = MagicMock(spec=ToolContext)
    mock_context.tool_confirmation = None

    exercises = ["Barbell Back Squat", "Leg Press", "Calf Raises"]
    workout_plan = "### Leg Day\n- Barbell Back Squat: 4x5"

    result = submit_workout_routine(
        exercises=exercises,
        workout_plan=workout_plan,
        focus_area="legs",
        tool_context=mock_context,
    )

    assert result["status"] == "paused_for_coach_confirmation"
    mock_context.request_confirmation.assert_called_once()
    call_kwargs = mock_context.request_confirmation.call_args[1]
    assert "coach" in call_kwargs["hint"].lower()
    assert "Barbell Back Squat" in call_kwargs["hint"]
    assert call_kwargs["payload"]["compound_lifts"] == ["Barbell Back Squat"]


def test_submit_workout_routine_requires_coach_pause_bench_press() -> None:
    """Test that a routine with bench press triggers HITL pause."""
    mock_context = MagicMock(spec=ToolContext)
    mock_context.tool_confirmation = None

    exercises = ["Barbell Bench Press", "Incline Dumbbell Flies", "Push-ups"]
    workout_plan = "### Chest Day\n- Bench Press: 4x6"

    result = submit_workout_routine(
        exercises=exercises,
        workout_plan=workout_plan,
        focus_area="chest",
        tool_context=mock_context,
    )

    assert result["status"] == "paused_for_coach_confirmation"
    mock_context.request_confirmation.assert_called_once()
    call_kwargs = mock_context.request_confirmation.call_args[1]
    assert "Bench Press" in call_kwargs["hint"]


def test_submit_workout_routine_requires_coach_pause_deadlift() -> None:
    """Test that a routine with deadlifts triggers HITL pause."""
    mock_context = MagicMock(spec=ToolContext)
    mock_context.tool_confirmation = None

    exercises = ["Conventional Deadlift", "Pull-ups", "Barbell Rows"]
    workout_plan = "### Back Day\n- Deadlift: 3x5"

    result = submit_workout_routine(
        exercises=exercises,
        workout_plan=workout_plan,
        focus_area="back",
        tool_context=mock_context,
    )

    assert result["status"] == "paused_for_coach_confirmation"
    mock_context.request_confirmation.assert_called_once()
    call_kwargs = mock_context.request_confirmation.call_args[1]
    assert "Deadlift" in call_kwargs["hint"]


def test_submit_workout_routine_resumes_with_coach_confirmed() -> None:
    """Test resuming with coach confirmed = True."""
    mock_context = MagicMock(spec=ToolContext)
    mock_context.tool_confirmation = ToolConfirmation(hint="Prompt", confirmed=True)

    exercises = ["Barbell Squat", "Leg Extensions"]
    workout_plan = "### Leg Day Plan"

    result = submit_workout_routine(
        exercises=exercises,
        workout_plan=workout_plan,
        focus_area="legs",
        tool_context=mock_context,
    )

    assert result["status"] == "approved_with_coach_review"
    assert result["worked_with_coach"] is True
    assert "opted to work with a coach" in result["coach_decision"]


def test_submit_workout_routine_resumes_with_coach_declined() -> None:
    """Test resuming with coach confirmed = False (user declined)."""
    mock_context = MagicMock(spec=ToolContext)
    mock_context.tool_confirmation = ToolConfirmation(hint="Prompt", confirmed=False)

    exercises = ["Deadlifts", "Pull-ups"]
    workout_plan = "### Back Day Plan"

    result = submit_workout_routine(
        exercises=exercises,
        workout_plan=workout_plan,
        focus_area="back",
        tool_context=mock_context,
    )

    assert result["status"] == "approved_with_coach_review"
    assert result["worked_with_coach"] is False
    assert "proceed independently" in result["coach_decision"]
