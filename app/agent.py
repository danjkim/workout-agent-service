# ruff: noqa
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

"""Workout Agent Service - Multi-Agent Architecture with Strategic Model Routing."""

import os
from dotenv import load_dotenv

from google.adk.agents import Agent
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.apps import App, ResumabilityConfig
from google.adk.apps.app import EventsCompactionConfig
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
from google.adk.models import Gemini
from google.genai import types

from app.constitution import (
    ROUTINE_ARCHITECT_INSTRUCTION,
    SAFETY_COACH_INSTRUCTION,
    WORKOUT_COACH_CONSTITUTION,
)
from app.plugins import (
    ObservabilityAndIntentPlugin,
    WorkoutGuardrailsPlugin,
)
from app.tools import (
    calculate_workout_volume_and_intensity,
    retrieve_exercise_technique_guidelines,
    submit_workout_routine,
)

load_dotenv()

# Strategic Model Routing:
# - Flash for high-speed coordination, real-time tool execution, and safety validation
# - Pro for complex multi-factor periodization, volume balancing, and deep workout architecture
MODEL_FLASH = "gemini-3.8-flash"
MODEL_PRO = "gemini-2.5-pro"

# 1. Specialist Sub-Agent: Routine Architect (Strategic Model Routing: Pro for planning)
routine_architect_agent = Agent(
    name="routine_architect",
    model=Gemini(
        model=MODEL_PRO,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    description="Specialist in exercise physiology, periodization, and volume planning.",
    instruction=ROUTINE_ARCHITECT_INSTRUCTION,
    tools=[calculate_workout_volume_and_intensity],
)

# 2. Specialist Sub-Agent: Safety Coach (Strategic Model Routing: Flash for fast checks)
safety_coach_agent = Agent(
    name="safety_coach",
    model=Gemini(
        model=MODEL_FLASH,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    description="Specialist in biomechanics, form safety, joint integrity, and compound lift clearance.",
    instruction=SAFETY_COACH_INSTRUCTION,
    tools=[retrieve_exercise_technique_guidelines, submit_workout_routine],
)

# 3. Coordinator Root Agent: Manages user conversation and orchestrates specialists
root_agent = Agent(
    # Keep in sync with agents-cli-manifest.yaml: agents-cli derives this name
    # from the project `name:` recorded there, and telemetry reports it as
    # gen_ai.agent.name. Renaming the agent only here makes the two disagree,
    # and anything selecting traces by name stops finding this agent's.
    name="workout_agent_service",
    model=Gemini(
        model=MODEL_FLASH,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=WORKOUT_COACH_CONSTITUTION,
    tools=[
        submit_workout_routine,
        calculate_workout_volume_and_intensity,
        retrieve_exercise_technique_guidelines,
    ],
    sub_agents=[routine_architect_agent, safety_coach_agent],
)

# Application with History Compaction, Context Caching, Guardrails, and HITL Resumability
app = App(
    name="app",
    root_agent=root_agent,
    plugins=[
        WorkoutGuardrailsPlugin(),
        ObservabilityAndIntentPlugin(),
    ],
    # History Compaction: Token-based compaction preventing context bloat on long sessions
    events_compaction_config=EventsCompactionConfig(
        token_threshold=32000,
        event_retention_size=6,
        summarizer=LlmEventSummarizer(llm=Gemini(model=MODEL_FLASH)),
    ),
    # Context Caching: Transparently caches system prompt and constitution on Google Cloud
    context_cache_config=ContextCacheConfig(
        min_tokens=2048,
        ttl_seconds=1800,
        cache_intervals=10,
    ),
    # Human-in-the-Loop Resumability
    resumability_config=ResumabilityConfig(is_resumable=True),
)
