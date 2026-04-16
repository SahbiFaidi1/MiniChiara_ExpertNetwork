from __future__ import annotations

import json
import logging

from openai import OpenAI
from pydantic import ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from config import get_settings
from src.models import RankedResult, RankedResultsEnvelope, SearchCandidate

log = logging.getLogger(__name__)


class Ranker:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_ranking_model

    @retry(wait=wait_exponential_jitter(initial=1, max=10), stop=stop_after_attempt(2))
    def _call_llm(self, query: str, candidates_payload: list[dict]) -> str:
        system = (
            "You rank expert-network search candidates.\n"
            "Rules:\n"
            "- Use ONLY the provided candidate data. Do not invent facts.\n"
            "- Output MUST be strict JSON (no markdown) matching this shape:\n"
            '{ "kind":"expert_search_results", "results":[{'
            '"name":"...", "current_role":"...", "company":"...", "who_knows_them":["..."], "why_relevant":"..."'
            "}], \"meta\":{...} }\n"
            "- Include at most 10 results.\n"
            "- If a field is unknown in candidate data, use null (or [] for who_knows_them).\n"
        )

        user = json.dumps(
            {
                "query": query,
                "candidates": candidates_payload,
            },
            ensure_ascii=False,
        )

        resp = self._client.chat.completions.create(
            model=self._model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""

    def rank(self, query: str, candidates: list[SearchCandidate]) -> RankedResultsEnvelope:
        if not candidates:
            return RankedResultsEnvelope(results=[], meta={"reason": "no_candidates"})

        # Provide a compact candidate payload (only real DB fields).
        candidates_payload = [
            {
                "name": c.person.name,
                "current_role": c.person.current_role,
                "company": c.person.company,
                "location": c.person.location,
                "who_knows_them": c.person.who_knows_them,
                "expertise_tags": c.person.expertise_tags,
                "background": c.person.background,
                "notes": c.person.notes,
                "searchable_text": c.person.searchable_text,
                "similarity": c.similarity,
            }
            for c in candidates
        ]

        try:
            raw = self._call_llm(query, candidates_payload)
            parsed = json.loads(raw)
            env = RankedResultsEnvelope.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError, Exception) as e:
            log.warning("Ranker fell back to similarity sort: %s", e)
            # Safe fallback: just take top candidates by similarity.
            sorted_candidates = sorted(candidates, key=lambda c: c.similarity, reverse=True)[:10]
            return RankedResultsEnvelope(
                results=[
                    RankedResult(
                        name=c.person.name,
                        current_role=c.person.current_role,
                        company=c.person.company,
                        who_knows_them=c.person.who_knows_them,
                        why_relevant="Retrieved by semantic similarity from our internal expert database.",
                    )
                    for c in sorted_candidates
                ],
                meta={"fallback": "similarity_sort"},
            )

        # Post-validate against DB truth: only allow candidate names and override structured fields.
        by_name = {c.person.name.lower(): c.person for c in candidates}
        cleaned: list[RankedResult] = []
        for r in env.results[:10]:
            p = by_name.get(r.name.lower())
            if not p:
                continue
            cleaned.append(
                RankedResult(
                    name=p.name,
                    current_role=p.current_role,
                    company=p.company,
                    who_knows_them=p.who_knows_them,
                    why_relevant=r.why_relevant,
                )
            )

        return RankedResultsEnvelope(results=cleaned, meta=env.meta or {})

