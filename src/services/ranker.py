from __future__ import annotations

import json
import logging
import re

from openai import OpenAI
from pydantic import ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from config import get_settings
from src.models import RankedResult, RankedResultsEnvelope, SearchCandidate

log = logging.getLogger(__name__)


class Ranker:
    _MAX_RESULTS = 10
    _LLM_SHORTLIST_SIZE = 6
    _TOKEN_RE = re.compile(r"[a-z0-9]+")

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
            "- Only include candidates from the provided list, by exact name.\n"
            "- Prioritize candidates with high base_score and clear domain overlap.\n"
            "- Output MUST be strict JSON (no markdown) matching this shape:\n"
            '{ "kind":"expert_search_results", "results":[{'
            '"name":"...", "current_role":"...", "company":"...", "who_knows_them":["..."], "why_relevant":"..."'
            "}], \"meta\":{...} }\n"
            "- Include at most 10 results, sorted best-first.\n"
            "- Keep why_relevant concise and factual (max ~150 chars).\n"
            "- Do not mention internal fields like base_score, similarity, or match_hints.\n"
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

    def _tokenize(self, text: str | None) -> set[str]:
        if not text:
            return set()
        return set(self._TOKEN_RE.findall(text.lower()))

    def _text_overlap_score(self, query_terms: set[str], text: str | None) -> float:
        terms = self._tokenize(text)
        if not query_terms or not terms:
            return 0.0
        overlap = query_terms.intersection(terms)
        if not overlap:
            return 0.0
        # Normalize by query length so scores remain comparable across queries.
        return min(1.0, len(overlap) / max(1, len(query_terms)))

    def _deterministic_score(self, query_terms: set[str], c: SearchCandidate) -> tuple[float, list[str]]:
        p = c.person
        similarity = max(0.0, min(1.0, c.similarity))

        role_company = " ".join([x for x in [p.current_role, p.company, p.location] if x])
        tags_text = " ".join(p.expertise_tags or [])
        context_text = " ".join([x for x in [p.background, p.notes, p.searchable_text] if x])

        role_company_overlap = self._text_overlap_score(query_terms, role_company)
        tags_overlap = self._text_overlap_score(query_terms, tags_text)
        context_overlap = self._text_overlap_score(query_terms, context_text)

        # Strongly favor vector similarity, then lexical signals for precision boosts.
        score = (
            0.7 * similarity
            + 0.15 * tags_overlap
            + 0.10 * role_company_overlap
            + 0.05 * context_overlap
        )

        reason_parts: list[str] = []
        if tags_overlap > 0:
            reason_parts.append("tag overlap")
        if role_company_overlap > 0:
            reason_parts.append("role/company overlap")
        if similarity >= 0.75:
            reason_parts.append("high semantic similarity")

        return score, reason_parts

    def _build_compact_candidate_payload(
        self,
        c: SearchCandidate,
        base_score: float,
        reason_parts: list[str],
    ) -> dict:
        p = c.person
        searchable_excerpt = (p.searchable_text or "")[:280]
        return {
            "name": p.name,
            "current_role": p.current_role,
            "company": p.company,
            "location": p.location,
            "who_knows_them": p.who_knows_them,
            "expertise_tags": p.expertise_tags,
            "background": p.background,
            "searchable_excerpt": searchable_excerpt,
            "similarity": c.similarity,
            "base_score": round(base_score, 4),
            "match_hints": reason_parts,
        }

    def _fallback_reason(self, reason_parts: list[str]) -> str:
        if reason_parts:
            return f"Retrieved by semantic similarity with {', '.join(reason_parts)}."
        return "Retrieved by semantic similarity from our internal expert database."

    def rank(self, query: str, candidates: list[SearchCandidate]) -> RankedResultsEnvelope:
        if not candidates:
            return RankedResultsEnvelope(results=[], meta={"reason": "no_candidates"})

        query_terms = self._tokenize(query)

        scored: list[tuple[float, list[str], SearchCandidate]] = []
        for c in candidates:
            score, reason_parts = self._deterministic_score(query_terms, c)
            scored.append((score, reason_parts, c))

        # Remove duplicate names while keeping the best-scored row.
        best_by_name: dict[str, tuple[float, list[str], SearchCandidate]] = {}
        for score, reason_parts, c in scored:
            key = c.person.name.strip().lower()
            prev = best_by_name.get(key)
            if prev is None or score > prev[0]:
                best_by_name[key] = (score, reason_parts, c)

        ranked_base = sorted(best_by_name.values(), key=lambda x: (x[0], x[2].similarity), reverse=True)
        shortlist = ranked_base[: self._LLM_SHORTLIST_SIZE]

        candidates_payload = [
            self._build_compact_candidate_payload(c, score, reason_parts)
            for score, reason_parts, c in shortlist
        ]

        by_name = {c.person.name.lower(): c.person for _, _, c in ranked_base}
        hints_by_name = {c.person.name.lower(): reason_parts for _, reason_parts, c in ranked_base}

        cleaned: list[RankedResult] = []
        seen: set[str] = set()
        try:
            raw = self._call_llm(query, candidates_payload)
            parsed = json.loads(raw)
            env = RankedResultsEnvelope.model_validate(parsed)
            for r in env.results[: self._MAX_RESULTS]:
                key = r.name.lower()
                p = by_name.get(key)
                if not p or key in seen:
                    continue
                cleaned.append(
                    RankedResult(
                        name=p.name,
                        current_role=p.current_role,
                        company=p.company,
                        who_knows_them=p.who_knows_them,
                        why_relevant=(r.why_relevant or "").strip() or self._fallback_reason(hints_by_name.get(key, [])),
                    )
                )
                seen.add(key)
        except (json.JSONDecodeError, ValidationError, Exception) as e:
            log.warning("Ranker LLM failed; using deterministic ranking: %s", e)

        # Fill any missing spots from deterministic ranking for stable top-k behavior.
        for _, reason_parts, c in ranked_base:
            if len(cleaned) >= self._MAX_RESULTS:
                break
            key = c.person.name.lower()
            if key in seen:
                continue
            cleaned.append(
                RankedResult(
                    name=c.person.name,
                    current_role=c.person.current_role,
                    company=c.person.company,
                    who_knows_them=c.person.who_knows_them,
                    why_relevant=self._fallback_reason(reason_parts),
                )
            )
            seen.add(key)

        return RankedResultsEnvelope(
            results=cleaned,
            meta={
                "strategy": "hybrid_shortlist_ranking",
                "candidates_in": len(candidates),
                "candidates_deduped": len(ranked_base),
                "llm_shortlist_size": len(shortlist),
            },
        )

