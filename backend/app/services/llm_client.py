"""
OpenAI-compatible chat client used by the Brief processing pipeline.
"""
from openai import AsyncOpenAI

from ..settings import settings

_clients: dict[tuple[str, str], AsyncOpenAI] = {}


def get_chat_client(api_key: str | None = None, base_url: str | None = None) -> AsyncOpenAI:
    if api_key or base_url:
        key = api_key or chat_api_key()
        url = base_url or chat_base_url()
    else:
        key, url = chat_provider()
    cache_key = (key, url)
    if cache_key not in _clients:
        _clients[cache_key] = AsyncOpenAI(api_key=key, base_url=url)
    return _clients[cache_key]


def chat_model() -> str:
    return settings.LLM_MODEL or settings.MOONSHOT_MODEL


def chat_api_key() -> str:
    return chat_provider()[0]


def chat_base_url() -> str:
    return chat_provider()[1]


def chat_provider() -> tuple[str, str]:
    if settings.LLM_API_KEY:
        return settings.LLM_API_KEY, settings.LLM_BASE_URL or settings.TOKENHUB_BASE_URL
    if settings.TOKENHUB_API_KEY:
        return settings.TOKENHUB_API_KEY, settings.TOKENHUB_BASE_URL
    if settings.MOONSHOT_API_KEY:
        return settings.MOONSHOT_API_KEY, settings.MOONSHOT_BASE_URL
    return settings.OPENAI_API_KEY, settings.LLM_BASE_URL or settings.TOKENHUB_BASE_URL


def classification_models() -> list[str]:
    models = [settings.CLASSIFICATION_MODEL or chat_model()]
    fallback = settings.CLASSIFICATION_FALLBACK_MODEL.strip()
    if fallback and fallback not in models:
        models.append(fallback)
    return models
