from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

import numpy as np

from config import get_settings
from src.db import get_conn
from src.models import Person, PersonCreate, PersonUpdate, SearchCandidate


def _row_to_person(row: dict[str, Any]) -> Person:
    return Person.model_validate(row)


class PeopleRepo:
    def create_person(self, data: PersonCreate, searchable_text: str) -> Person:
        with get_conn() as conn:
            row = conn.execute(
                """
                insert into public.people
                  (name, "current_role", company, location, expertise_tags, who_knows_them, background, notes, searchable_text)
                values
                  (%(name)s, %(current_role)s, %(company)s, %(location)s, %(expertise_tags)s, %(who_knows_them)s,
                   %(background)s, %(notes)s, %(searchable_text)s)
                returning *
                """,
                {
                    **data.model_dump(),
                    "searchable_text": searchable_text,
                },
            ).fetchone()
            return _row_to_person(row)

    def update_person(self, person_id: UUID, patch: PersonUpdate, searchable_text: str) -> Person:
        fields = patch.model_dump(exclude_unset=True)
        fields["searchable_text"] = searchable_text
        fields["id"] = person_id

        set_parts = []
        for k in fields.keys():
            if k == "id":
                continue
            col = f'"{k}"' if k == "current_role" else k
            set_parts.append(f"{col} = %({k})s")

        if not set_parts:
            return self.get_person(person_id)

        with get_conn() as conn:
            row = conn.execute(
                f"""
                update public.people
                set {", ".join(set_parts)}
                where id = %(id)s
                returning *
                """,
                fields,
            ).fetchone()
            return _row_to_person(row)

    def delete_person(self, person_id: UUID) -> None:
        with get_conn() as conn:
            conn.execute("delete from public.people where id = %s", (person_id,))

    def get_person(self, person_id: UUID) -> Person:
        with get_conn() as conn:
            row = conn.execute("select * from public.people where id = %s", (person_id,)).fetchone()
            return _row_to_person(row)

    def find_by_name(self, name: str) -> Optional[Person]:
        with get_conn() as conn:
            row = conn.execute(
                "select * from public.people where lower(name) = lower(%s) limit 1",
                (name,),
            ).fetchone()
            return _row_to_person(row) if row else None

    def find_by_name_fuzzy(self, name: str) -> list[Person]:
        with get_conn() as conn:
            rows = conn.execute(
                "select * from public.people where lower(name) like lower(%s) order by name asc limit 10",
                (f"%{name}%",),
            ).fetchall()
            return [_row_to_person(r) for r in rows]

    def upsert_embedding(self, person_id: UUID, embedding: list[float], embedding_model: str) -> None:
        settings = get_settings()
        with get_conn() as conn:
            if settings.use_pgvector:
                from pgvector import Vector

                conn.execute(
                    """
                    insert into public.person_embeddings (person_id, embedding, embedding_model)
                    values (%s, %s, %s)
                    on conflict (person_id) do update
                      set embedding = excluded.embedding,
                          embedding_model = excluded.embedding_model,
                          created_at = now()
                    """,
                    (person_id, Vector(embedding), embedding_model),
                )
            else:
                conn.execute(
                    """
                    insert into public.person_embeddings (person_id, embedding, embedding_model)
                    values (%s, %s, %s)
                    on conflict (person_id) do update
                      set embedding = excluded.embedding,
                          embedding_model = excluded.embedding_model,
                          created_at = now()
                    """,
                    (person_id, embedding, embedding_model),
                )

    def search_candidates(self, query_embedding: list[float], k: int) -> list[SearchCandidate]:
        settings = get_settings()

        if settings.use_pgvector:
            with get_conn() as conn:
                from pgvector import Vector

                qv = Vector(query_embedding)
                rows = conn.execute(
                    """
                    select p.*, (1 - (e.embedding <=> %s)) as similarity
                    from public.people p
                    join public.person_embeddings e on e.person_id = p.id
                    order by e.embedding <=> %s
                    limit %s
                    """,
                    (qv, qv, k),
                ).fetchall()

            out: list[SearchCandidate] = []
            for r in rows:
                r = dict(r)
                similarity = float(r.pop("similarity"))
                out.append(SearchCandidate(person=_row_to_person(r), similarity=similarity))
            return out

        # Fallback: pull all embeddings and compute cosine similarity in Python
        with get_conn() as conn:
            rows = conn.execute(
                """
                select p.*, e.embedding as embedding
                from public.people p
                join public.person_embeddings e on e.person_id = p.id
                """,
            ).fetchall()

        if not rows:
            return []

        q = np.array(query_embedding, dtype=np.float32)
        q_norm = np.linalg.norm(q) + 1e-8

        scored: list[tuple[float, dict[str, Any]]] = []
        for r in rows:
            r = dict(r)
            emb = r.pop("embedding", None)
            if not emb:
                continue
            v = np.array(list(emb), dtype=np.float32)
            sim = float(np.dot(q, v) / (q_norm * (np.linalg.norm(v) + 1e-8)))
            scored.append((sim, r))

        scored.sort(key=lambda t: t[0], reverse=True)
        top = scored[:k]
        return [SearchCandidate(person=_row_to_person(r), similarity=float(sim)) for sim, r in top]

