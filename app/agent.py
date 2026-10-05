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

import os
from dotenv import load_dotenv

from google.adk.agents import Agent
from google.adk.apps import App, ResumabilityConfig
from google.adk.models import Gemini
from google.genai import types

from app.tools import submit_workout_routine

load_dotenv()

MODEL = "gemini-3.8-flash"

INSTRUCTION = """You are a professional fitness coach and workout routine designer.
Your goal is to design the user's workout routine for the day depending on what they want to focus on (e.g., chest, legs, back, arms, core, cardio, hypertrophy, strength).

Instructions:
1. Identify the user's workout focus for the day.
2. Design a structured workout routine including warm-up, primary exercises (with sets, reps, and rest periods), and cool-down.
3. Call the `submit_workout_routine` tool with:
   - `exercises`: the list of exercise names in the routine (e.g., ['Push-ups', 'Dumbbell Incline Bench Press', 'Cable Crossover']).
   - `workout_plan`: the complete, nicely formatted workout plan markdown.
   - `focus_area`: the user's focus area for the day.
4. If the routine does NOT include bench press, squats, or deadlifts, the tool will instantly approve it.
5. If the routine requires bench press, squats, or deadlifts, the tool will trigger a human-in-the-loop pause to ask if the user wants to work with a coach.
6. After the tool returns the approval result, summarize and present the final approved workout routine to the user, including any coach guidance.
"""


root_agent = Agent(
    # Keep in sync with agents-cli-manifest.yaml: agents-cli derives this name
    # from the project `name:` recorded there, and telemetry reports it as
    # gen_ai.agent.name. Renaming the agent only here makes the two disagree,
    # and anything selecting traces by name stops finding this agent's.
    name="workout_agent_service",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=INSTRUCTION,
    tools=[submit_workout_routine],
)

app = App(
    root_agent=root_agent,
    name="app",
    resumability_config=ResumabilityConfig(is_resumable=True),
)
