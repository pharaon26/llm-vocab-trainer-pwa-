from pathlib import Path

import httpx
from gigachat import Chat, GigaChat, GigaChatException, Messages, MessagesRole

from app.config import BASE_DIR
from app.llm.base import LLMError, LLMProvider


class GigaChatProvider(LLMProvider):
    def __init__(
        self,
        credentials: str,
        scope: str,
        model: str,
        ca_bundle_file: str,
        temperature: float,
        timeout: float,
    ):
        if not credentials:
            raise LLMError("GIGACHAT_CREDENTIALS is not set")
        ca_path = Path(ca_bundle_file)
        if not ca_path.is_absolute():
            ca_path = BASE_DIR / ca_path
        if not ca_path.is_file():
            raise LLMError(f"CA bundle not found: {ca_path}")

        self.name = f"gigachat:{model}"
        self.temperature = temperature
        self.client = GigaChat(
            credentials=credentials,
            scope=scope,
            model=model,
            ca_bundle_file=str(ca_path),
            verify_ssl_certs=True,
            timeout=timeout,
        )

    async def complete(self, system: str, user: str) -> str:
        payload = Chat(
            messages=[
                Messages(role=MessagesRole.SYSTEM, content=system),
                Messages(role=MessagesRole.USER, content=user),
            ],
            temperature=self.temperature,
        )
        try:
            response = await self.client.achat(payload)
        except (GigaChatException, httpx.HTTPError) as exc:
            raise LLMError(f"GigaChat request failed: {type(exc).__name__}") from exc
        if not response.choices or not response.choices[0].message.content:
            raise LLMError("GigaChat returned an empty response")
        return response.choices[0].message.content
