from __future__ import annotations

from config import get_settings
from src.models import SearchCandidate
from src.repositories.people_repo import PeopleRepo
from src.services.embedder import Embedder


class Retriever:
    def __init__(self, repo: PeopleRepo | None = None, embedder: Embedder | None = None) -> None:
        self._repo = repo or PeopleRepo()
        self._embedder = embedder or Embedder()

    def retrieve(self, query: str) -> list[SearchCandidate]:
        settings = get_settings()
        q_emb = self._embedder.embed_text(query)
        return self._repo.search_candidates(q_emb, k=settings.retrieval_top_k)

