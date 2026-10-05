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

"""Tools for the workout agent service."""

from typing import Any

from google.adk.tools import ToolContext

COMPOUND_LIFT_KEYWORDS = ["bench press", "squat", "deadlift"]


def submit_workout_routine(
    exercises: list[str],
    workout_plan: str,
    focus_area: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Submits and evaluates the workout routine for approval.

    If the routine includes bench press, squats, or deadlifts, it triggers a
    human-in-the-loop pause asking the user whether they want to work with a coach.
    Otherwise, the routine is instantly approved.

    Args:
        exercises: List of exercise names included in the routine (e.g. ['Barbell Back Squat', 'Leg Press']).
        workout_plan: The detailed workout routine in markdown (warm-up, sets, reps, rest, cool-down).
        focus_area: The user's focus area for the day (e.g. 'legs', 'arms', 'chest', 'core').
        tool_context: Context provided by the ADK runtime.

    Returns:
        A dictionary with approval status and workout details.
    """
    found_compounds = [
        ex for ex in exercises if any(kw in ex.lower() for kw in COMPOUND_LIFT_KEYWORDS)
    ]

    if found_compounds:
        if not tool_context.tool_confirmation:
            tool_context.request_confirmation(
                hint=(
                    f"Your workout routine requires heavy compound lift(s): {', '.join(found_compounds)}. "
                    "Would you like to work with a coach for form and safety guidance?"
                ),
                payload={
                    "focus_area": focus_area,
                    "compound_lifts": found_compounds,
                    "exercises": exercises,
                    "workout_plan": workout_plan,
                    "prompt": "Would you like to work with a coach?",
                },
            )
            return {
                "status": "paused_for_coach_confirmation",
                "message": (
                    f"Routine requires {found_compounds}. "
                    "Paused for human-in-the-loop: prompting user whether they want to work with a coach."
                ),
            }
        else:
            confirmed = bool(tool_context.tool_confirmation.confirmed)
            coach_decision = (
                "Confirmed: User has opted to work with a coach for form and safety."
                if confirmed
                else "User opted to proceed independently without a coach."
            )
            return {
                "status": "approved_with_coach_review",
                "coach_decision": coach_decision,
                "worked_with_coach": confirmed,
                "workout_plan": workout_plan,
            }

    return {
        "status": "instantly_approved",
        "message": (
            "No bench press, squats, or deadlifts in this routine. "
            "Workout routine is instantly approved!"
        ),
        "workout_plan": workout_plan,
    }
