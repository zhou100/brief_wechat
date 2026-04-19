"""
Text categorization using GPT.
Returns a list of {text, category} dicts — one entry can produce multiple classifications
from a single transcript (multi-entry extraction).
"""
import json
import logging
from typing import Any, Dict, List
from .llm_client import chat_model, get_chat_client

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a time-logging assistant. Extract ALL distinct activities, \
tasks, ideas, and notes from the transcript and return them as a JSON array.

Categories — two dimensions:

Activity categories (how the user spent time):
- EARNING: things the user did or handled; work, errands, appointments, meetings, projects
- LEARNING: something learned, read, practiced, researched, or figured out
- MAITAISHAO: 买汰烧; grocery shopping, buying food, washing/prepping vegetables, cooking, kitchen chores
- RELAXING: exercise, rest, hobbies, entertainment, social outings, naps
- FAMILY: family time, caregiving, family errands, partner time

Capture categories (follow-up items):
- TODO: a task or action item that needs to be done
- EXPERIMENT: a change to try, hypothesis to test, possible improvement, or future direction
- REFLECTION: an observation, feeling, reaction, lesson, or pattern the user noticed

Disambiguation rules:
- Default assumption: if the user is narrating what happened today, classify it
  as an activity category, not TODO.
- Only classify TODO when the transcript clearly says the item is still undone,
  future, a reminder, or something to remember. Chinese examples include:
  "明天要", "等会要", "还没", "需要去", "记得", "别忘了", "提醒我".
- Past time expressions like "今天早上", "下午一点", or "五点半以后回来" are not
  TODO by themselves.
- Work lunch / business dinner = EARNING (primary intent is work)
- Gym / exercise = RELAXING (even if it feels productive)
- Reading for a work project = EARNING; reading for personal growth = LEARNING
- Buying vegetables, washing vegetables (汰菜), meal prep, and cooking = MAITAISHAO
- Commute to work = EARNING; running family errands = FAMILY
- When an activity serves multiple categories, classify by primary intent.
- If the user suggests a future change ("maybe we should", "what if", "it might help to"),
  classify as EXPERIMENT.
- If the user is mainly describing how it felt, a lesson, reaction, or pattern they
  noticed, classify as REFLECTION.
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
  {"text": "specific activity or note text", "category": "EARNING|LEARNING|MAITAISHAO|RELAXING|FAMILY|TODO|EXPERIMENT|REFLECTION", "estimated_minutes": <integer or null>},
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

Input: "早上去买菜，回来汰菜，烧了两个菜。下午学会了怎么设置小程序常驻实例。"
Output: [
  {"text": "去买菜、汰菜、烧了两个菜", "category": "MAITAISHAO", "estimated_minutes": null},
  {"text": "学会设置小程序常驻实例", "category": "LEARNING", "estimated_minutes": null}
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
        response = await get_chat_client().chat.completions.create(
            model=chat_model(),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": stripped},
            ],
            temperature=0.3,
        )
        raw = response.choices[0].message.content or ""
        results = json.loads(_extract_json_array(raw))

        # Validate: must be a non-empty list of dicts with text + category
        if not isinstance(results, list) or not results:
            raise ValueError("LLM returned empty or non-list result")

        _VALID_CATEGORIES = {
            "EARNING",
            "LEARNING",
            "MAITAISHAO",
            "RELAXING",
            "FAMILY",
            "TODO",
            "EXPERIMENT",
            "REFLECTION",
            "TIME_RECORD",
        }
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


def _extract_json_array(text: str) -> str:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("[")
    end = stripped.rfind("]")
    if start >= 0 and end > start:
        return stripped[start:end + 1]
    return stripped
