from __future__ import annotations

from src.models import PersonBase


def build_searchable_text(person: PersonBase) -> str:
    parts: list[str] = []

    def add(label: str, value: str | None):
        if value:
            parts.append(f"{label}: {value}".strip())

    add("name", person.name)
    add("current_role", person.current_role)
    add("company", person.company)
    add("location", person.location)
    if person.expertise_tags:
        parts.append("expertise_tags: " + ", ".join(person.expertise_tags))
    if person.who_knows_them:
        parts.append("who_knows_them: " + ", ".join(person.who_knows_them))
    add("background", person.background)
    add("notes", person.notes)

    # A stable, compact string tends to embed well.
    return "\n".join([p for p in parts if p.strip()])

