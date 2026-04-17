"""
Post-transcription refinement using an LLM.

Fixes common speech-to-text errors: homophones, mis-segmented words,
garbled Chinese/English code-switching, and punctuation.
"""
import logging
from .llm_client import chat_model, get_chat_client

logger = logging.getLogger(__name__)

REFINE_PROMPT = """\
You are a transcript editor. The user will give you a raw speech-to-text transcript \
that may contain errors from automatic speech recognition.

Your job:
1. Fix obvious ASR errors: wrong homophones (谐音字), mis-segmented words, garbled text.
2. Fix punctuation and sentence boundaries.
3. Preserve the original meaning exactly — do NOT add, remove, or rephrase content.
4. Handle Chinese-English code-switching naturally. Keep English terms that the speaker \
   clearly intended (e.g. "meeting", "deploy", "PR review") in English.
5. If the transcript is already correct, return it unchanged.

Return ONLY the corrected transcript text, nothing else."""


async def refine_transcript(raw_text: str) -> str:
    """
    Clean up a raw ASR transcript using an LLM.
    Returns the original text on any failure (best-effort).
    """
    stripped = raw_text.strip()
    if not stripped:
        return stripped

    try:
        response = await get_chat_client().chat.completions.create(
            model=chat_model(),
            messages=[
                {"role": "system", "content": REFINE_PROMPT},
                {"role": "user", "content": stripped},
            ],
            temperature=0.2,
            max_tokens=len(stripped) * 3,  # generous but bounded
        )
        refined = (response.choices[0].message.content or "").strip()

        if not refined:
            logger.warning("Refiner returned empty text; keeping original")
            return stripped

        logger.info(
            f"Transcript refined: {len(stripped)} → {len(refined)} chars"
        )
        return refined

    except Exception as exc:
        logger.error(f"Transcript refinement failed ({exc}); keeping original")
        return stripped
