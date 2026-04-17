"""
OpenAI-compatible chat client used by the Brief processing pipeline.
"""
from openai import AsyncOpenAI

from ..settings import settings

_client: AsyncOpenAI | None = None


def get_chat_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = settings.MOONSHOT_API_KEY or settings.OPENAI_API_KEY
        _client = AsyncOpenAI(api_key=api_key, base_url=settings.MOONSHOT_BASE_URL)
    return _client


def chat_model() -> str:
    return settings.MOONSHOT_MODEL
