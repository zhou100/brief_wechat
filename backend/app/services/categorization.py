"""
Text categorization using GPT.
Returns a list of {text, category} dicts — one entry can produce multiple classifications
from a single transcript (multi-entry extraction).
"""
import json
import logging
from typing import Any, Dict, List
from openai import AsyncOpenAI
from ..settings import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


SYSTEM_PROMPT = """You are a time-logging assistant. Extract ALL distinct activities, \
tasks, ideas, and notes from the transcript and return them as a JSON array.

Categories — two dimensions:

Activity categories (how the user spent time):
- EARNING: work, meetings, deep work, side projects, clients, commute to work
- LEARNING: reading, courses, research, practice, skill-building
- RELAXING: exercise, rest, hobbies, entertainment, social outings, naps
- FAMILY: family time, caregiving, family errands, partner time

Capture categories (follow-up items):
- TODO: a task or action item that needs to be done
- EXPERIMENT: a change to try, hypothesis to test, possible improvement, or future direction
- REFLECTION: an observation, feeling, reaction, lesson, or pattern the user noticed

Disambiguation rules:
- Work lunch / business dinner = EARNING (primary intent is work)
- Gym / exercise = RELAXING (even if it feels productive)
- Reading for a work project = EARNING; reading for personal growth = LEARNING
- Commute to work = EARNING; running family errands = FAMILY
- When an activity serves multiple categories, classify by primary intent.
- If the user suggests a future change ("maybe we should", "what if", "it might help to"),
  classify as EXPERIMENT.
- If the user is mainly describing what happened, how it felt, or what they learned,
  classify as REFLECTION.
- If something could be both EXPERIMENT and REFLECTION, prefer EXPERIMENT when it suggests
  a future change.
- If something could be both TODO and EXPERIMENT, prefer TODO when it is specific and
  actionable now.

IMPORTANT rules:
- Extract MULTIPLE entries from a single transcript. A 90-second monologue typically \
contains 3-6 distinct items.
- Each entry gets its own object with the specific text for that activity.
- Do NOT invent activities. Only extract what is explicitly mentioned.
- Reference ONLY the activities listed in the transcript.
- Include "estimated_minutes" — your best guess at how many minutes this activity took. \
Use null if the user didn't mention a duration and you can't reasonably infer one. \
Only provide a number when the transcript explicitly states or strongly implies a duration.

Return valid JSON array only, with this shape:
[
  {"text": "specific activity or note text", "category": "EARNING|LEARNING|RELAXING|FAMILY|TODO|EXPERIMENT|REFLECTION", "estimated_minutes": <integer or null>},
  ...
]

Examples:

Input: "I need to fix the login bug tomorrow."
Output: [{"text": "Fix the login bug", "category": "TODO", "estimated_minutes": null}]

Input: "This morning I worked on the dashboard for about 2 hours. Then had three \
back-to-back meetings that felt unproductive. Had an idea to add voice replay to \
the audit feature. Still need to write tests for the auth module."
Output: [
  {"text": "Worked on the dashboard for about 2 hours", "category": "EARNING", "estimated_minutes": 120},
  {"text": "Three back-to-back meetings that felt unproductive", "category": "EARNING", "estimated_minutes": 90},
  {"text": "Add voice replay to the audit feature", "category": "EXPERIMENT", "estimated_minutes": null},
  {"text": "Write tests for the auth module", "category": "TODO", "estimated_minutes": null}
]

Input: "Spent an hour reading about distributed systems. Then picked up the kids from \
school and helped with homework. Realized we should document environment setup better."
Output: [
  {"text": "Reading about distributed systems for an hour", "category": "LEARNING", "estimated_minutes": 60},
  {"text": "Picked up kids from school and helped with homework", "category": "FAMILY", "estimated_minutes": 90},
  {"text": "Document environment setup better", "category": "EXPERIMENT", "estimated_minutes": null}
]

Input: "The afternoon felt scattered and reactive. It might help to start recordings \
right after meetings."
Output: [
  {"text": "The afternoon felt scattered and reactive", "category": "REFLECTION", "estimated_minutes": null},
  {"text": "Start recordings right after meetings", "category": "EXPERIMENT", "estimated_minutes": null}
]"""


async def categorize_text(text: str) -> List[Dict[str, Any]]:
    """
    Extract and classify all activities from transcript text using GPT.

    Returns a list of dicts: [{"text": str, "category": str}, ...]

    Fallback behaviour:
    - Empty transcript → raises ValueError("No speech detected")
    - Empty array from LLM → returns [{"text": full_transcript, "category": "REFLECTION"}]
    - Malformed/non-JSON response → returns [{"text": full_transcript, "category": "REFLECTION"}]
    """
    stripped = text.strip() if text else ""
    if not stripped:
        raise ValueError("No speech detected")

    try:
        response = await _get_client().chat.completions.create(
            model="gpt-5.4-nano",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": stripped},
            ],
            temperature=0.3,
        )
        raw = response.choices[0].message.content or ""
        results = json.loads(raw)

        # Validate: must be a non-empty list of dicts with text + category
        if not isinstance(results, list) or not results:
            raise ValueError("LLM returned empty or non-list result")

        _VALID_CATEGORIES = {"EARNING", "LEARNING", "RELAXING", "FAMILY", "TODO", "EXPERIMENT", "REFLECTION", "TIME_RECORD"}
        valid = [
            r for r in results
            if isinstance(r, dict) and r.get("text") and r.get("category") in _VALID_CATEGORIES
        ]
        # Remap legacy TIME_RECORD → EARNING (LLM may hallucinate it)
        for r in valid:
            if r["category"] == "TIME_RECORD":
                r["category"] = "EARNING"
        if not valid:
            raise ValueError("No valid entries in LLM result")

        logger.info(
            f"Categorized transcript ({len(stripped)} chars) → {len(valid)} entries: "
            f"{[r['category'] for r in valid]}"
        )
        return valid

    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        logger.warning(
            f"Categorization parse/validation failed ({exc}); falling back to REFLECTION"
        )
        return [{"text": stripped, "category": "REFLECTION"}]
    except Exception as exc:
        logger.error(f"Categorization API call failed: {exc}")
        return [{"text": stripped, "category": "REFLECTION"}]
