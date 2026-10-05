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

"""Automated evaluation harness testing agent scenarios against the golden dataset."""

import json
import os
from unittest.mock import MagicMock

from google.adk.tools import ToolContext

from app.tools import submit_workout_routine

DATASET_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "eval",
    "datasets",
    "basic-dataset.json",
)


def test_golden_dataset_format_and_coverage() -> None:
    """Validate that the golden dataset file exists, is valid JSON, and has test cases."""
    assert os.path.isfile(DATASET_PATH), f"Dataset file missing at {DATASET_PATH}"
    with open(DATASET_PATH, encoding="utf-8") as f:
        data = json.load(f)

    assert "eval_cases" in data, "Golden dataset must contain 'eval_cases'"
    eval_cases = data["eval_cases"]
    assert len(eval_cases) >= 2, "Golden dataset must have at least 2 eval cases"

    for case in eval_cases:
        assert "eval_case_id" in case
        assert "prompt" in case
        prompt_parts = case["prompt"].get("parts", [])
        assert len(prompt_parts) > 0
        assert "text" in prompt_parts[0]
        assert len(prompt_parts[0]["text"]) > 10


def test_eval_dataset_instant_approval_scenario() -> None:
    """Run simulated agent execution against arms_routine_instant_approval dataset case."""
    mock_context = MagicMock(spec=ToolContext)
    mock_context.tool_confirmation = None

    # Scenario: Dumbbell curls & tricep pushdowns (no compound lifts)
    exercises = ["Dumbbell Bicep Curls", "Cable Tricep Pushdowns", "Hammer Curls"]
    workout_plan = "### Arms Hypertrophy Routine\n1. Dumbbell Curls: 3x12\n2. Tricep Pushdowns: 3x12"

    result = submit_workout_routine(
        exercises=exercises,
        workout_plan=workout_plan,
        focus_area="arms",
        tool_context=mock_context,
    )

    assert result["status"] == "instantly_approved"
    assert "instantly approved" in result["message"]
    mock_context.request_confirmation.assert_not_called()


def test_eval_dataset_hitl_pause_scenario() -> None:
    """Run simulated agent execution against heavy compound lift scenario requiring coach pause."""
    mock_context = MagicMock(spec=ToolContext)
    mock_context.tool_confirmation = None

    exercises = ["Barbell Back Squat", "Leg Press", "Calf Raises"]
    workout_plan = "### Heavy Leg Day\n1. Barbell Back Squat: 5x5"

    result = submit_workout_routine(
        exercises=exercises,
        workout_plan=workout_plan,
        focus_area="legs",
        tool_context=mock_context,
    )

    assert result["status"] == "paused_for_coach_confirmation"
    assert "Barbell Back Squat" in result["message"]
    mock_context.request_confirmation.assert_called_once()
