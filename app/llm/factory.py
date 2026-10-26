from app.config import Settings, settings
from app.llm.base import LLMProvider
from app.llm.fake import FakeProvider
from app.llm.gigachat import GigaChatProvider


def get_provider(config: Settings = settings) -> LLMProvider:
    if config.llm_provider == "gigachat":
        return GigaChatProvider(
            credentials=config.gigachat_credentials,
            scope=config.gigachat_scope,
            model=config.gigachat_model,
            ca_bundle_file=config.gigachat_ca_bundle,
            temperature=config.llm_temperature,
            timeout=config.llm_timeout,
        )
    return FakeProvider()
