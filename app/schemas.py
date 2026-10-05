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

"""Explicit JSON schemas and Pydantic validation models for tool interfaces."""

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class FocusAreaEnum(StrEnum):
    """Valid workout focus categories."""

    CHEST = "chest"
    LEGS = "legs"
    BACK = "back"
    ARMS = "arms"
    SHOULDERS = "shoulders"
    CORE = "core"
    FULL_BODY = "full_body"
    CARDIO = "cardio"


class ExperienceLevel(StrEnum):
    """Trainee experience levels."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class ExercisePrescription(BaseModel):
    """Detailed prescription for a single exercise."""

    name: str = Field(
        ...,
        min_length=2,
        description="Name of the exercise (e.g., 'Barbell Back Squat')",
    )
    sets: int = Field(..., ge=1, le=20, description="Prescribed number of working sets")
    reps: int = Field(
        ..., ge=1, le=100, description="Prescribed target repetitions per set"
    )
    rest_seconds: int = Field(
        default=90, ge=15, le=360, description="Rest period in seconds between sets"
    )
    target_muscle_group: str | None = Field(
        default=None, description="Primary targeted muscle group"
    )
    notes: str | None = Field(
        default=None, description="Execution cues or form guidance"
    )


class WorkoutRoutineInput(BaseModel):
    """Strict input schema for submitting a workout routine."""

    exercises: list[str] = Field(
        ...,
        min_length=1,
        description="List of exercise names included in the routine (e.g., ['Push-ups', 'Leg Press']). Must not be empty.",
    )
    workout_plan: str = Field(
        ...,
        min_length=10,
        description="Comprehensive workout routine formatted in Markdown with warm-up, main sets, and cool-down.",
    )
    focus_area: str = Field(
        ...,
        min_length=2,
        description="Primary focus area or muscle group for the workout (e.g., 'legs', 'arms', 'chest').",
    )
    experience_level: ExperienceLevel | None = Field(
        default=ExperienceLevel.INTERMEDIATE,
        description="Target trainee fitness experience level.",
    )

    @field_validator("exercises")
    @classmethod
    def validate_non_empty_names(cls, v: list[str]) -> list[str]:
        cleaned = [ex.strip() for ex in v if ex and ex.strip()]
        if not cleaned:
            raise ValueError(
                "Exercises list must contain at least one non-empty exercise name."
            )
        return cleaned


class WorkoutSubmissionOutput(BaseModel):
    """Strict output schema returned by the workout submission tool."""

    status: str = Field(
        ...,
        description="Status of the submission: 'instantly_approved', 'paused_for_coach_confirmation', 'approved_with_coach_review', or 'error'",
    )
    message: str | None = Field(
        default=None, description="Human-readable status summary or explanation"
    )
    workout_plan: str | None = Field(
        default=None, description="The validated workout routine markdown"
    )
    compound_lifts: list[str] = Field(
        default_factory=list, description="Heavy compound lifts detected in the routine"
    )
    coach_decision: str | None = Field(
        default=None, description="Coach guidance or user confirmation outcome"
    )
    worked_with_coach: bool | None = Field(
        default=None,
        description="True if the user opted to work with a coach, False otherwise",
    )
    error_code: str | None = Field(
        default=None,
        description="Machine-readable error code if validation or execution failed",
    )
    recovery_instruction: str | None = Field(
        default=None,
        description="Actionable instructions for the LLM to recover from an error",
    )
    allowed_alternatives: list[str] | None = Field(
        default=None,
        description="Suggested valid alternatives if invalid parameters were provided",
    )


class VolumeCalculationInput(BaseModel):
    """Strict input schema for calculating workout training volume and intensity."""

    exercises: list[str] = Field(
        ..., min_length=1, description="List of exercise names in the routine"
    )
    estimated_sets_per_exercise: int = Field(
        default=3, ge=1, le=10, description="Average sets per exercise"
    )
    estimated_reps_per_set: int = Field(
        default=10, ge=1, le=50, description="Average repetitions per set"
    )
    average_load_kg: float | None = Field(
        default=20.0,
        ge=0.0,
        description="Estimated average external load in kg (0 for bodyweight)",
    )


class VolumeCalculationOutput(BaseModel):
    """Strict output schema for workout volume analysis."""

    total_exercises: int = Field(..., description="Count of exercises in the session")
    total_working_sets: int = Field(..., description="Total aggregate working sets")
    total_reps: int = Field(
        ..., description="Estimated aggregate repetitions completed"
    )
    total_volume_tonnage_kg: float = Field(
        ..., description="Estimated total volume load (sets x reps x weight)"
    )
    intensity_category: str = Field(
        ...,
        description="Intensity classification: 'Low', 'Moderate', 'High', or 'Very High'",
    )
    metabolic_burn_estimate_kcal: int = Field(
        ..., description="Estimated caloric expenditure range midpoint"
    )
    recovery_window_hours: int = Field(
        ..., description="Recommended recovery window before training same muscle group"
    )


class TechniqueGuidelineInput(BaseModel):
    """Strict input schema for retrieving exercise technique and safety guidelines."""

    exercise_name: str = Field(
        ...,
        min_length=2,
        description="Specific name of the exercise to look up (e.g., 'Deadlift')",
    )
    user_experience: ExperienceLevel | None = Field(
        default=ExperienceLevel.INTERMEDIATE, description="User's training background"
    )


class TechniqueGuidelineOutput(BaseModel):
    """Strict output schema for exercise technique and safety guidelines."""

    exercise_name: str = Field(..., description="Standardized exercise name")
    is_compound: bool = Field(
        ..., description="Whether the movement is a multi-joint compound lift"
    )
    primary_muscles: list[str] = Field(..., description="Primary agonist muscle groups")
    setup_cues: list[str] = Field(..., description="Critical setup and alignment cues")
    execution_cues: list[str] = Field(
        ..., description="Active concentric and eccentric cues"
    )
    common_mistakes: list[str] = Field(
        ..., description="Frequent form breakdowns to avoid"
    )
    contraindications: list[str] = Field(
        ...,
        description="Pre-existing conditions or injuries that require caution or alternatives",
    )
    safe_alternatives: list[str] = Field(
        ...,
        description="Regressions or safer alternatives for injured or beginner lifters",
    )
