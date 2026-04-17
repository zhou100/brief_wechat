#!/usr/bin/env python3
"""
Pre-demo accuracy check for the multi-entry categorization service.

Run from the backend directory:
    python scripts/test_categorization.py

Requires OPENAI_API_KEY in the environment (or .env file).
Asserts that each transcript produces ≥1 entry and hits the expected category.
Exits 0 on pass, 1 on failure.
"""
import asyncio
import os
import sys

# Allow running from the backend/ directory without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from app.services.categorization import categorize_text

# ── Test cases ────────────────────────────────────────────────────────────────

CASES = [
    {
        "name": "deep work session",
        "transcript": (
            "This morning I spent about three hours refactoring the authentication module. "
            "Got the JWT refresh logic cleaned up and all the unit tests are passing now."
        ),
        "expected_category": "TIME_RECORD",
    },
    {
        "name": "todo item",
        "transcript": (
            "I need to follow up with the design team about the new onboarding flow mockups. "
            "Should send them the feedback doc by end of week."
        ),
        "expected_category": "TODO",
    },
    {
        "name": "idea capture",
        "transcript": (
            "Had an interesting thought — what if we added a voice replay feature to the audit page? "
            "Users could listen back to the original recording alongside the transcript. "
            "Could be really useful for reviewing long entries."
        ),
        "expected_category": "IDEA",
    },
    {
        "name": "mixed transcript — multiple entries expected",
        "transcript": (
            "Okay so this afternoon I was in meetings for most of it, probably four hours total. "
            "I need to write up the notes from the product sync. "
            "Oh and I had an idea for a smarter notification grouping system — "
            "something that batches alerts by project instead of by time. "
            "Feeling a bit drained, probably need to block more focus time tomorrow."
        ),
        "expected_category": "TIME_RECORD",  # at least one TIME_RECORD in the mix
        "expect_multiple": True,
    },
]

# ── Runner ────────────────────────────────────────────────────────────────────

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"


async def run_cases():
    failures = 0

    for case in CASES:
        name = case["name"]
        try:
            results = await categorize_text(case["transcript"])
        except Exception as exc:
            print(f"[{FAIL}] {name!r} — exception: {exc}")
            failures += 1
            continue

        # Must return ≥1 entry
        if not results:
            print(f"[{FAIL}] {name!r} — returned empty list")
            failures += 1
            continue

        categories_returned = [r["category"] for r in results]

        # Must hit the expected category
        if case["expected_category"] not in categories_returned:
            print(
                f"[{FAIL}] {name!r} — expected {case['expected_category']!r}, "
                f"got {categories_returned}"
            )
            failures += 1
            continue

        # If multiple entries expected, assert >1
        if case.get("expect_multiple") and len(results) < 2:
            print(
                f"[{FAIL}] {name!r} — expected multiple entries, "
                f"got {len(results)}: {results}"
            )
            failures += 1
            continue

        print(
            f"[{PASS}] {name!r} — {len(results)} entr{'y' if len(results)==1 else 'ies'}: "
            + ", ".join(f"[{r['category']}] {r['text'][:50]!r}" for r in results)
        )

    return failures


def main():
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or api_key.startswith("dummy"):
        print("ERROR: OPENAI_API_KEY is not set or is a dummy value.")
        print("Set a real key to run this script.")
        sys.exit(1)

    print("Running categorization accuracy check...\n")
    failures = asyncio.run(run_cases())
    print()

    if failures:
        print(f"RESULT: {failures}/{len(CASES)} test(s) FAILED")
        sys.exit(1)
    else:
        print(f"RESULT: All {len(CASES)} tests passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
