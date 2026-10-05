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

"""Persistent Session State, Knowledge Retrieval, and Asynchronous Memory Operations.

Provides a persistent SQLite-backed database store for user workout history and profiles,
along with asynchronous background memory consolidation tasks that prevent UI blocking.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import os
import sqlite3
from typing import Any

from app.logger import get_structured_logger
from app.pii_scrubber import scrub_dict_pii

logger = get_structured_logger("workout_memory_store")

DEFAULT_DB_PATH = os.environ.get(
    "WORKOUT_DB_PATH",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "artifacts",
        "workout_history.sqlite",
    ),
)


def get_db_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Initialize SQLite database tables and return connection."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                preferred_focus TEXT,
                experience_level TEXT,
                equipment TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workout_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                user_id TEXT,
                focus_area TEXT,
                workout_plan TEXT,
                compound_lifts TEXT,
                worked_with_coach INTEGER,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS exercise_library (
                exercise_id TEXT PRIMARY KEY,
                name TEXT UNIQUE,
                target_muscle TEXT,
                is_compound INTEGER,
                cues TEXT,
                contraindications TEXT
            )
            """
        )
    return conn


# Initialize default exercises into persistent library
def _seed_exercise_library(conn: sqlite3.Connection) -> None:
    seeds = [
        (
            "barbell_squat",
            "Barbell Back Squat",
            "Quadriceps / Glutes",
            1,
            "Chest up, knees tracking over toes, hip crease below knee.",
            "Acute knee ligament injury, acute lower back herniation",
        ),
        (
            "bench_press",
            "Barbell Bench Press",
            "Pectoralis Major / Triceps",
            1,
            "Retract scapulae, five points of contact, bar touch sternum.",
            "Rotator cuff impingement, acute shoulder instability",
        ),
        (
            "deadlift",
            "Conventional Deadlift",
            "Hamstrings / Erector Spinae",
            1,
            "Bar against shins, lats engaged, push the floor away.",
            "Lumbar disc herniation, severe hamstring tear",
        ),
        (
            "push_ups",
            "Push-ups",
            "Chest / Anterior Deltoid",
            0,
            "Rigid plank line, elbows at 45 degrees, full lockout.",
            "Wrist arthritis (use push-up handles)",
        ),
        (
            "pull_ups",
            "Pull-ups",
            "Latissimus Dorsi / Biceps",
            1,
            "Full dead-hang, initiate with scapular depression, chin over bar.",
            "Golfer's elbow / medial epicondylitis",
        ),
        (
            "bicep_curls",
            "Dumbbell Bicep Curls",
            "Biceps Brachii",
            0,
            "Keep elbows pinned to sides, supinate at top, controlled eccentric.",
            "Distal bicep tendonitis",
        ),
        (
            "tricep_pushdowns",
            "Cable Tricep Pushdowns",
            "Triceps Brachii",
            0,
            "Upper arms stationary, flare rope at lockout, squeeze triceps.",
            "Triceps tendonitis",
        ),
    ]
    with conn:
        for eid, name, muscle, comp, cues, contra in seeds:
            conn.execute(
                """
                INSERT OR IGNORE INTO exercise_library (exercise_id, name, target_muscle, is_compound, cues, contraindications)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (eid, name, muscle, comp, cues, contra),
            )


# Initialize DB
try:
    _init_conn = get_db_connection()
    _seed_exercise_library(_init_conn)
    _init_conn.close()
except Exception as e:
    logger.warning(
        f"Could not initialize default SQLite database at {DEFAULT_DB_PATH}: {e}"
    )


def search_exercise_knowledge(
    query: str, db_path: str = DEFAULT_DB_PATH
) -> list[dict[str, Any]]:
    """Query persistent database for exercise safety cues and contraindicated conditions."""
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT exercise_id, name, target_muscle, is_compound, cues, contraindications
            FROM exercise_library
            WHERE name LIKE ? OR target_muscle LIKE ?
            """,
            (f"%{query}%", f"%{query}%"),
        )
        rows = cursor.fetchall()
        return [
            {
                "id": r[0],
                "name": r[1],
                "target_muscle": r[2],
                "is_compound": bool(r[3]),
                "cues": r[4],
                "contraindications": r[5],
            }
            for r in rows
        ]
    finally:
        conn.close()


def save_session_workout_sync(
    session_id: str,
    user_id: str,
    focus_area: str,
    workout_plan: str,
    compound_lifts: list[str],
    worked_with_coach: bool,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    """Synchronously record workout session into persistent database."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO workout_sessions (session_id, user_id, focus_area, workout_plan, compound_lifts, worked_with_coach, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    user_id,
                    focus_area,
                    workout_plan,
                    json.dumps(compound_lifts),
                    1 if worked_with_coach else 0,
                    datetime.datetime.now(datetime.UTC).isoformat(),
                ),
            )
            conn.execute(
                """
                INSERT INTO user_profiles (user_id, preferred_focus, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    preferred_focus=excluded.preferred_focus,
                    updated_at=excluded.updated_at
                """,
                (user_id, focus_area, datetime.datetime.now(datetime.UTC).isoformat()),
            )
    finally:
        conn.close()


async def async_consolidate_memory(
    session_id: str,
    user_id: str,
    focus_area: str,
    workout_plan: str,
    compound_lifts: list[str],
    worked_with_coach: bool,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    """Expensive memory consolidation executed asynchronously in the background.

    Runs as a non-blocking background task to prevent UI or streaming delays.
    """
    try:
        # Scrub PII before persisting to long-term memory store
        clean_plan = scrub_dict_pii(workout_plan)
        clean_compounds = scrub_dict_pii(compound_lifts)

        # Offload SQLite blocking I/O to a worker thread
        await asyncio.to_thread(
            save_session_workout_sync,
            session_id=session_id,
            user_id=user_id,
            focus_area=focus_area,
            workout_plan=clean_plan,
            compound_lifts=clean_compounds,
            worked_with_coach=worked_with_coach,
            db_path=db_path,
        )
        logger.info(
            f"Asynchronously consolidated session memory for user {user_id}",
            extra={
                "event_type": "async_memory_consolidation",
                "metadata": {
                    "session_id": session_id,
                    "user_id": user_id,
                    "focus_area": focus_area,
                    "compound_lifts": clean_compounds,
                },
            },
        )
    except Exception as e:
        logger.error(f"Error during async memory consolidation: {e}")


_background_tasks = set()


def schedule_async_memory_consolidation(
    session_id: str,
    user_id: str,
    focus_area: str,
    workout_plan: str,
    compound_lifts: list[str],
    worked_with_coach: bool,
) -> None:
    """Dispatches background task for memory consolidation without blocking caller."""
    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(
            async_consolidate_memory(
                session_id=session_id,
                user_id=user_id,
                focus_area=focus_area,
                workout_plan=workout_plan,
                compound_lifts=compound_lifts,
                worked_with_coach=worked_with_coach,
            )
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
    except RuntimeError:
        # No running event loop, dispatch in daemon thread to avoid blocking caller
        import threading

        t = threading.Thread(
            target=save_session_workout_sync,
            args=(
                session_id,
                user_id,
                focus_area,
                workout_plan,
                compound_lifts,
                worked_with_coach,
            ),
            daemon=True,
        )
        t.start()
