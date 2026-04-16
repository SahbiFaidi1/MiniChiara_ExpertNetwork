from __future__ import annotations

from typing import Any, Iterable

from src.models import Person, RankedResultsEnvelope


def help_blocks() -> list[dict[str, Any]]:
    return [
        {"type": "header", "text": {"type": "plain_text", "text": "Expert network (MVP)"}},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*Commands*\n"
                    "- `/expert-search <query>` – semantic search\n"
                    "- `/expert-add` – add a person\n"
                    "- `/expert-view <name>` – view a profile\n"
                    "- `/expert-delete <name>` – delete a profile\n"
                    "- `/expert-help` – show this help"
                ),
            },
        },
    ]


def _person_line(p: Person) -> str:
    role = f" — {p.current_role}" if p.current_role else ""
    company = f" @ {p.company}" if p.company else ""
    return f"*{p.name}*{role}{company}"


def ambiguous_matches_blocks(name: str, matches: Iterable[Person]) -> list[dict[str, Any]]:
    lines = "\n".join([f"- {_person_line(p)}" for p in matches])
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"I found multiple matches for *{name}*: \n{lines}"}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": "Try `/expert-view <full name>`."}]},
    ]


def person_profile_blocks(person: Person) -> list[dict[str, Any]]:
    who = ", ".join(person.who_knows_them) if person.who_knows_them else "—"
    tags = ", ".join(person.expertise_tags) if person.expertise_tags else "—"
    loc = person.location or "—"
    role = person.current_role or "—"
    company = person.company or "—"

    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": person.name}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Role*\n{role}"},
                {"type": "mrkdwn", "text": f"*Company*\n{company}"},
                {"type": "mrkdwn", "text": f"*Location*\n{loc}"},
                {"type": "mrkdwn", "text": f"*Who knows them*\n{who}"},
                {"type": "mrkdwn", "text": f"*Tags*\n{tags}"},
            ],
        },
    ]

    if person.background:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Background*\n{person.background}"}})
    if person.notes:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Notes*\n{person.notes}"}})

    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Edit"},
                    "action_id": "expert_edit_open",
                    "value": str(person.id),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Delete"},
                    "style": "danger",
                    "action_id": "expert_delete_open",
                    "value": str(person.id),
                },
            ],
        }
    )
    return blocks


def search_results_blocks(query: str, ranked: RankedResultsEnvelope) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": "Expert search results"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Query*: {query}"}},
    ]

    if not ranked.results:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "No matches found."}})
        return blocks

    for i, r in enumerate(ranked.results, start=1):
        who = ", ".join(r.who_knows_them) if r.who_knows_them else "—"
        role = r.current_role or "—"
        company = r.company or "—"
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{i}. {r.name}*\n"
                        f"{role} @ {company}\n"
                        f"*Who knows them*: {who}\n"
                        f"*Why relevant*: {r.why_relevant}"
                    ),
                },
            }
        )

    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "Use `/expert-view <name>` to open a profile."}]})
    return blocks

