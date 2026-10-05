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

"""Tools for the workout agent service.

Provides strictly-typed, descriptive tools for workout routine submission,
volume/intensity calculations, and movement technique retrieval with guided error handling.
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext
from pydantic import ValidationError

from app.logger import get_structured_logger
from app.memory_store import (
    schedule_async_memory_consolidation,
    search_exercise_knowledge,
)
from app.schemas import (
    FocusAreaEnum,
    TechniqueGuidelineInput,
    VolumeCalculationInput,
    WorkoutRoutineInput,
)

logger = get_structured_logger("workout_tools")

COMPOUND_LIFT_KEYWORDS = ["bench press", "squat", "deadlift"]

ALLOWED_FOCUS_AREAS = [member.value for member in FocusAreaEnum.__members__.values()]


def submit_workout_routine(
    exercises: list[str],
    workout_plan: str,
    focus_area: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Submits and evaluates the workout routine for approval and safety clearance.

    If the routine includes heavy compound barbell movements (bench press, squats,
    or deadlifts), it triggers a Human-in-the-Loop (HITL) pause asking the user
    whether they wish to work with a certified coach for form and safety guidance.
    Otherwise, the routine is instantly approved.

    Args:
        exercises: List of exercise names included in the routine (e.g. ['Barbell Back Squat', 'Leg Press']).
        workout_plan: The detailed workout routine formatted in Markdown with warm-up, sets, reps, and cool-down.
        focus_area: The user's focus area for the day (e.g. 'legs', 'arms', 'chest', 'back', 'core').
        tool_context: Runtime execution context provided by the ADK framework.

    Returns:
        A dictionary with approval status, workout details, and coach guidance.
        If validation fails, returns a guided error dictionary with recovery instructions.
    """
    # Guided Error Handling: Validate inputs against strict Pydantic schema
    try:
        validated_input = WorkoutRoutineInput(
            exercises=exercises,
            workout_plan=workout_plan,
            focus_area=focus_area,
        )
    except (ValidationError, Exception) as exc:
        logger.warning(f"Validation failed in submit_workout_routine: {exc}")
        return {
            "status": "error",
            "error_code": "INVALID_WORKOUT_PAYLOAD",
            "message": f"Input validation failed: {exc}",
            "recovery_instruction": (
                "Please correct the routine parameters. Ensure 'exercises' is a non-empty list of valid exercise names, "
                f"'focus_area' is one of {ALLOWED_FOCUS_AREAS}, and 'workout_plan' contains complete Markdown instructions."
            ),
            "allowed_alternatives": ALLOWED_FOCUS_AREAS,
        }

    # Inspect for heavy compound movements requiring Human-in-the-Loop clearance
    found_compounds = [
        ex
        for ex in validated_input.exercises
        if any(kw in ex.lower() for kw in COMPOUND_LIFT_KEYWORDS)
    ]

    # Human-in-the-Loop Gate
    if found_compounds:
        if not tool_context.tool_confirmation:
            tool_context.request_confirmation(
                hint=(
                    f"Your workout routine requires heavy compound lift(s): {', '.join(found_compounds)}. "
                    "Would you like to work with a coach for form and safety guidance?"
                ),
                payload={
                    "focus_area": validated_input.focus_area,
                    "compound_lifts": found_compounds,
                    "exercises": validated_input.exercises,
                    "workout_plan": validated_input.workout_plan,
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

            # Asynchronous Memory Consolidation (Background non-blocking task)
            schedule_async_memory_consolidation(
                session_id=str(getattr(tool_context, "session_id", "session_default")),
                user_id=str(getattr(tool_context, "user_id", "user_default")),
                focus_area=validated_input.focus_area,
                workout_plan=validated_input.workout_plan,
                compound_lifts=found_compounds,
                worked_with_coach=confirmed,
            )

            return {
                "status": "approved_with_coach_review",
                "coach_decision": coach_decision,
                "worked_with_coach": confirmed,
                "workout_plan": validated_input.workout_plan,
            }

    # Instant approval for routines without high-risk compound lifts
    schedule_async_memory_consolidation(
        session_id=str(getattr(tool_context, "session_id", "session_default")),
        user_id=str(getattr(tool_context, "user_id", "user_default")),
        focus_area=validated_input.focus_area,
        workout_plan=validated_input.workout_plan,
        compound_lifts=[],
        worked_with_coach=False,
    )

    return {
        "status": "instantly_approved",
        "message": (
            "No bench press, squats, or deadlifts in this routine. "
            "Workout routine is instantly approved!"
        ),
        "workout_plan": validated_input.workout_plan,
    }


def calculate_workout_volume_and_intensity(
    exercises: list[str],
    estimated_sets_per_exercise: int = 3,
    estimated_reps_per_set: int = 10,
    average_load_kg: float = 20.0,
) -> dict[str, Any]:
    """Calculates cumulative training volume, tonnage, and exertion metrics.

    Provides physiological volume metrics to prevent overtraining and ensure
    optimal progressive overload stimulus.

    Args:
        exercises: List of exercise names in the prescribed routine.
        estimated_sets_per_exercise: Average working sets per exercise (default: 3).
        estimated_reps_per_set: Average repetitions completed per set (default: 10).
        average_load_kg: Estimated average external load in kilograms (default: 20.0).

    Returns:
        A dictionary containing total working sets, total reps, cumulative tonnage (kg),
        intensity category, metabolic burn estimate (kcal), and recovery window.
        Returns a guided error response if inputs are outside physiological bounds.
    """
    try:
        payload = VolumeCalculationInput(
            exercises=exercises,
            estimated_sets_per_exercise=estimated_sets_per_exercise,
            estimated_reps_per_set=estimated_reps_per_set,
            average_load_kg=average_load_kg,
        )
    except (ValidationError, Exception) as exc:
        return {
            "status": "error",
            "error_code": "VOLUME_CALCULATION_INVALID_INPUT",
            "message": f"Invalid volume parameters: {exc}",
            "recovery_instruction": (
                "Ensure sets are between 1 and 10, reps between 1 and 50, and load is non-negative."
            ),
        }

    total_exercises = len(payload.exercises)
    total_sets = total_exercises * payload.estimated_sets_per_exercise
    total_reps = total_sets * payload.estimated_reps_per_set
    load_kg = payload.average_load_kg if payload.average_load_kg is not None else 20.0
    total_tonnage = round(total_reps * load_kg, 2)

    # Classify intensity
    if total_sets <= 10:
        intensity = "Low"
        kcal = 150
        recovery_hours = 24
    elif total_sets <= 18:
        intensity = "Moderate"
        kcal = 300
        recovery_hours = 48
    elif total_sets <= 25:
        intensity = "High"
        kcal = 450
        recovery_hours = 72
    else:
        intensity = "Very High"
        kcal = 600
        recovery_hours = 96

    return {
        "status": "success",
        "total_exercises": total_exercises,
        "total_working_sets": total_sets,
        "total_reps": total_reps,
        "total_volume_tonnage_kg": total_tonnage,
        "intensity_category": intensity,
        "metabolic_burn_estimate_kcal": kcal,
        "recovery_window_hours": recovery_hours,
    }


def retrieve_exercise_technique_guidelines(
    exercise_name: str,
    user_experience: str = "intermediate",
) -> dict[str, Any]:
    """Retrieves standard execution standards, biomechanical cues, and contraindications.

    Queries the persistent exercise knowledge base to retrieve movement cues,
    joint safety considerations, and regressions for individuals with orthopedic limits.

    Args:
        exercise_name: Exact or partial name of the exercise (e.g., 'Squat', 'Bench Press', 'Deadlift').
        user_experience: Trainee experience level ('beginner', 'intermediate', 'advanced').

    Returns:
        A dictionary with technique cues, primary muscles, contraindications, and safe regressions.
        If the exercise is not found, provides guided recovery instructions with available movements.
    """
    try:
        validated = TechniqueGuidelineInput(
            exercise_name=exercise_name,
        )
    except (ValidationError, Exception) as exc:
        return {
            "status": "error",
            "error_code": "INVALID_TECHNIQUE_QUERY",
            "message": f"Invalid query: {exc}",
            "recovery_instruction": "Please provide a valid non-empty exercise name (min length 2).",
        }

    results = search_exercise_knowledge(validated.exercise_name)
    if not results:
        return {
            "status": "not_found",
            "error_code": "EXERCISE_NOT_FOUND",
            "message": f"No guideline entry found for '{validated.exercise_name}'.",
            "recovery_instruction": (
                f"The exercise '{validated.exercise_name}' is not in the verified movement library. "
                "You may query guidelines for: 'Barbell Back Squat', 'Barbell Bench Press', "
                "'Conventional Deadlift', 'Push-ups', 'Pull-ups', 'Dumbbell Bicep Curls', or 'Cable Tricep Pushdowns'."
            ),
            "allowed_alternatives": [
                "Barbell Back Squat",
                "Barbell Bench Press",
                "Conventional Deadlift",
                "Push-ups",
                "Pull-ups",
            ],
        }

    entry = results[0]
    return {
        "status": "success",
        "exercise_name": entry["name"],
        "is_compound": entry["is_compound"],
        "target_muscle": entry["target_muscle"],
        "cues": entry["cues"],
        "contraindications": entry["contraindications"],
        "user_experience_profile": user_experience,
    }
