from __future__ import annotations

from typing import Any, Iterable

from src.models import Person, RankedResultsEnvelope

_MAX_WHO_DISPLAY = 3
_MAX_REASON_LEN = 180


def _truncate(text: str, max_len: int) -> str:
    s = (text or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"


def _format_who_knows(who_knows_them: list[str]) -> str:
    if not who_knows_them:
        return "—"
    shown = [w.strip() for w in who_knows_them if w.strip()]
    if not shown:
        return "—"
    head = shown[:_MAX_WHO_DISPLAY]
    extra = len(shown) - len(head)
    if extra > 0:
        return f"{', '.join(head)} (+{extra} more)"
    return ", ".join(head)


def help_blocks() -> list[dict[str, Any]]:
    return [
        {"type": "header", "text": {"type": "plain_text", "text": "Expert network guide"}},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "Ask naturally to find people in our network.\n"
                    "Example: `Who do we know in energy trading?`"
                ),
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*1) Search experts*\n"
                    "- DM me your question directly\n"
                    "- In channels: mention me, e.g. `@Mini Chiara who knows AI infra operators?`\n"
                    "- Slash command: `/expert-search <query>`"
                ),
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*2) Filter by category*\n"
                    "- Fellows only: `/search_fellows <query>`\n"
                    "- Experts only: `/search_experts <query>`\n"
                    "- VC profiles only: `/search_vcs <query>`\n"
                    "- Chat shortcuts: `fellows <query>`, `experts <query>`, `vcs <query>`"
                ),
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*3) Manage profiles*\n"
                    "- Add: `/expert-add`\n"
                    "- View details: `/expert-view <name>`\n"
                    "- Delete: `/expert-delete <name>`"
                ),
            },
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": "Tip: type `help` anytime in DM to show this guide again."}
            ],
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
    total = len(ranked.results)
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": "Expert search results"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Query:* {query}"}},
    ]

    if not ranked.results:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "No matches found."}})
        return blocks

    blocks.append(
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Showing top {total} matches"}],
        }
    )

    for i, r in enumerate(ranked.results, start=1):
        who = _format_who_knows(r.who_knows_them)
        role = r.current_role or "—"
        company = r.company or "—"
        why = _truncate(r.why_relevant, _MAX_REASON_LEN)
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{i}. {r.name}*\n"
                        f"{role} @ {company}\n"
                        f"*Who knows them:* {who}\n"
                        f"*Why relevant:* {why}"
                    ),
                },
            }
        )
        if i < total:
            blocks.append({"type": "divider"})

    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "Use `/expert-view <name>` to open a profile."}]})
    return blocks

