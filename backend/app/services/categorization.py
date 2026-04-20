"""
Text categorization using GPT.
Returns a list of {text, category} dicts — one entry can produce multiple classifications
from a single transcript (multi-entry extraction).
"""
import json
import logging
import asyncio
from typing import Any, Dict, List
from .llm_client import classification_models, get_chat_client
from ..settings import settings

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
  Wu dialect / Shanghainese equivalents: "明朝要", "等歇要", "还没做好",
  "要去", "记牢", "勿要忘记", "侬提醒我", "到时候要", "下趟".
- Past time expressions like "今天早上", "下午一点", or "五点半以后回来" are not
  TODO by themselves.
- The transcript may contain Wu dialect (吴语/上海话/苏州话) or other regional
  dialects. Treat them the same as Mandarin: narrating something already done →
  activity category; still-undone / future → TODO; emotional reaction → REFLECTION.
  Common dialect past-completion markers: "做好了", "搞定了", "弄好了格", "做好额",
  "搞好了", "去过了", "买好了", "吃过了", "讲好了". These all indicate a completed
  activity, NOT a TODO or REFLECTION.
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
]

Input: "今朝去买好菜了，回来汰好了，烧了三个菜。下午陪小孩做作业，做了差不多两个钟头。明朝要去医院拿报告，记牢勿要忘记。"
Output: [
  {"text": "去买菜、汰菜、烧了三个菜", "category": "MAITAISHAO", "estimated_minutes": null},
  {"text": "陪小孩做作业，约两个小时", "category": "FAMILY", "estimated_minutes": 120},
  {"text": "明天去医院拿报告", "category": "TODO", "estimated_minutes": null}
]

Input: "今天早上7点起床，7:00~9:00带娃，9:00~11:00做项目，11:00~12:00做家务，12点以后出门运动了两个小时，然后又回家做饭做到5:30，晚上7:00~9:00看电视，9:00~11:00打游戏。"
Output: [
  {"text": "7:00~9:00 带娃", "category": "FAMILY", "estimated_minutes": 120},
  {"text": "9:00~11:00 做项目", "category": "EARNING", "estimated_minutes": 120},
  {"text": "11:00~12:00 做家务", "category": "EARNING", "estimated_minutes": 60},
  {"text": "12:00 以后出门运动两个小时", "category": "RELAXING", "estimated_minutes": 120},
  {"text": "回家做饭到 5:30", "category": "MAITAISHAO", "estimated_minutes": null},
  {"text": "晚上 7:00~9:00 看电视", "category": "RELAXING", "estimated_minutes": 120},
  {"text": "9:00~11:00 打游戏", "category": "RELAXING", "estimated_minutes": 120}
]

Input: "今天早上10点出门买菜做饭，下午1点去接小孩。两点回家。"
Output: [
  {"text": "出门买菜做饭", "category": "MAITAISHAO", "estimated_minutes": null},
  {"text": "下午1点去接小孩，两点回家", "category": "FAMILY", "estimated_minutes": 60}
]

Input: "跟朋友去饭店吃饭，回来之后在家休息了一下。"
Output: [
  {"text": "跟朋友去饭店吃饭", "category": "RELAXING", "estimated_minutes": null},
  {"text": "回家休息", "category": "RELAXING", "estimated_minutes": null}
]"""


async def categorize_text(text: str) -> List[Dict[str, Any]]:
    """
    Extract and classify all activities from transcript text using GPT.

    Returns a list of dicts: [{"text": str, "category": str}, ...]

    Fallback behaviour:
    - Empty transcript → raises ValueError("No speech detected")
    - Empty array from LLM → returns [{"text": full_transcript, "category": "REFLECTION"}]
    - Malformed/non-JSON response → returns [{"text": full_transcript, "category": "REFLECTION"}]
    - API/network errors → try configured fallback models, then raise so the job can
      fail instead of storing a fake REFLECTION
    """
    stripped = text.strip() if text else ""
    if not stripped:
        raise ValueError("No speech detected")

    parse_error: Exception | None = None
    api_error: Exception | None = None
    for model in classification_models():
        try:
            response = await asyncio.wait_for(
                get_chat_client().chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": stripped},
                    ],
                    temperature=_temperature_for_model(model),
                ),
                timeout=settings.CLASSIFICATION_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            api_error = exc
            logger.warning(f"Categorization API call failed for {model}: {exc}")
            continue

        try:
            valid = _valid_classification_results(
                response.choices[0].message.content or "",
                model,
            )
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            parse_error = exc
            logger.warning(
                f"Categorization parse/validation failed for {model} ({exc}); trying fallback"
            )
            continue

        logger.info(
            f"Categorized transcript ({len(stripped)} chars) with {model} → "
            f"{len(valid)} entries: {[r['category'] for r in valid]}"
        )
        return valid

    if parse_error is not None:
        logger.warning(
            f"All categorization responses failed validation ({parse_error}); "
            "falling back to REFLECTION"
        )
        return [{"text": stripped, "category": "REFLECTION"}]

    logger.error(f"All categorization API calls failed: {api_error}")
    raise RuntimeError(f"classification_api_failed: {api_error}") from api_error


def _valid_classification_results(raw: str, model: str) -> List[Dict[str, Any]]:
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
        r["model"] = model
    if not valid:
        raise ValueError("No valid entries in LLM result")
    return valid


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


def _temperature_for_model(model: str) -> float:
    # Moonshot requires kimi-k2.5 requests to use temperature=1.
    if model == "kimi-k2.5":
        return 1.0
    return settings.CLASSIFICATION_TEMPERATURE
