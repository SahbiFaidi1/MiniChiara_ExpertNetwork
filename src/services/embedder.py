from __future__ import annotations

from typing import Iterable

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from config import get_settings


class Embedder:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_embedding_model

    @property
    def model(self) -> str:
        return self._model

    @retry(wait=wait_exponential_jitter(initial=1, max=10), stop=stop_after_attempt(3))
    def embed_text(self, text: str) -> list[float]:
        resp = self._client.embeddings.create(model=self._model, input=text)
        return list(resp.data[0].embedding)

    def embed_texts(self, texts: Iterable[str]) -> list[list[float]]:
        # Simple batching; can be optimized later
        return [self.embed_text(t) for t in texts]

