"""Evaluation metric for workout routine agent (instant approval & HITL pause)."""

import threading
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel

_local = threading.local()


class _Verdict(BaseModel):
    score: int  # 1-5
    explanation: str


def _client() -> genai.Client:
    """One client per grading thread."""
    client = getattr(_local, "client", None)
    if client is None:
        client = _local.client = genai.Client()
    return client


def evaluate(instance: dict[str, Any]) -> dict[str, Any]:
    """Evaluate whether the workout routine was properly approved or paused for a coach."""
    agent_data = instance.get("agent_data") or {}
    turns = agent_data.get("turns", [])

    requested_confirmation = False
    confirmation_hint = ""
    tool_status = None

    for turn in turns:
        for event in turn.get("events", []):
            content = event.get("content") or {}
            for part in content.get("parts") or []:
                fc = part.get("function_call")
                if fc and fc.get("name") == "adk_request_confirmation":
                    requested_confirmation = True
                    args = fc.get("args") or {}
                    tc = args.get("toolConfirmation") or {}
                    confirmation_hint = tc.get("hint", "")

                fr = part.get("function_response")
                if fr and fr.get("name") == "submit_workout_routine":
                    resp = fr.get("response") or {}
                    tool_status = resp.get("status")

    case_id = instance.get("eval_case_id", "")
    response = instance.get("response")

    # Cases requiring coach pause (bench press, squats, deadlifts)
    if "pause" in case_id or "coach" in case_id:
        if (
            requested_confirmation
            and tool_status == "paused_for_coach_confirmation"
            and "coach" in confirmation_hint.lower()
        ):
            return {
                "score": 5,
                "explanation": (
                    f"Successfully triggered human-in-the-loop pause prompting the user "
                    f"whether they want to work with a coach ({confirmation_hint})."
                ),
            }
        return {
            "score": 1,
            "explanation": (
                f"Failed to trigger human-in-the-loop coach pause. "
                f"Requested confirmation: {requested_confirmation}, status: {tool_status}."
            ),
        }

    # Instant approval cases (no bench press, squats, deadlifts)
    if requested_confirmation:
        return {
            "score": 1,
            "explanation": "Routine incorrectly triggered coach confirmation despite having no compound lifts.",
        }

    if tool_status != "instantly_approved":
        return {
            "score": 2,
            "explanation": f"Routine was not instantly approved. Tool status: {tool_status}.",
        }

    # Grade the final approved response
    prompt = (
        "You are an expert fitness evaluator. Grade the approved workout routine on a 1-5 scale "
        "for clarity, structure, and adherence to the user's request.\n"
        f"User Prompt: {instance.get('prompt', '')}\n"
        f"Final Response: {response or ''}\n"
    )

    eval_response = _client().models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=_Verdict,
        ),
    )
    verdict = eval_response.parsed
    if verdict is None:
        return {"score": 5, "explanation": "Instantly approved without issue."}
    return {
        "score": max(1, min(5, verdict.score)),
        "explanation": verdict.explanation,
    }
