from __future__ import annotations

import logging

from slack_bolt import App as SlackApp

from src.repositories.people_repo import PeopleRepo
from src.services.ranker import Ranker
from src.services.retriever import Retriever
from src.services.slack_blocks import (
    ambiguous_matches_blocks,
    help_blocks,
    person_profile_blocks,
    search_results_blocks,
)
from src.slack.modals import build_add_person_modal, build_delete_person_modal, ADD_MODAL_CALLBACK_ID

log = logging.getLogger(__name__)


def register_slash_commands(app: SlackApp) -> None:
    repo = PeopleRepo()
    retriever = Retriever(repo=repo)
    ranker = Ranker()

    @app.command("/expert-help")
    def expert_help(ack, respond, command):
        ack()
        respond(blocks=help_blocks(), response_type="ephemeral")

    @app.command("/expert-search")
    def expert_search(ack, respond, command):
        ack()
        query = (command.get("text") or "").strip()
        if not query:
            respond(text="Usage: `/expert-search <query>`", response_type="ephemeral")
            return

        try:
            candidates = retriever.retrieve(query)
            ranked = ranker.rank(query, candidates)
            respond(blocks=search_results_blocks(query, ranked), response_type="ephemeral")
        except Exception as e:
            log.exception("expert-search failed")
            respond(text=f"Search failed: {e}", response_type="ephemeral")

    @app.command("/expert-add")
    def expert_add(ack, client, command):
        ack()
        trigger_id = command.get("trigger_id")
        client.views_open(trigger_id=trigger_id, view=build_add_person_modal())

    @app.command("/expert-view")
    def expert_view(ack, respond, command):
        ack()
        name = (command.get("text") or "").strip()
        if not name:
            respond(text="Usage: `/expert-view <name>`", response_type="ephemeral")
            return

        person = repo.find_by_name(name)
        if person:
            respond(blocks=person_profile_blocks(person), response_type="ephemeral")
            return

        matches = repo.find_by_name_fuzzy(name)
        if not matches:
            respond(text=f"No match found for: {name}", response_type="ephemeral")
            return

        if len(matches) == 1:
            respond(blocks=person_profile_blocks(matches[0]), response_type="ephemeral")
            return

        respond(blocks=ambiguous_matches_blocks(name, matches), response_type="ephemeral")

    @app.command("/expert-delete")
    def expert_delete(ack, client, respond, command):
        ack()
        name = (command.get("text") or "").strip()
        if not name:
            respond(text="Usage: `/expert-delete <name>`", response_type="ephemeral")
            return

        person = repo.find_by_name(name)
        if not person:
            matches = repo.find_by_name_fuzzy(name)
            if not matches:
                respond(text=f"No match found for: {name}", response_type="ephemeral")
                return
            if len(matches) > 1:
                respond(blocks=ambiguous_matches_blocks(name, matches), response_type="ephemeral")
                return
            person = matches[0]

        client.views_open(trigger_id=command.get("trigger_id"), view=build_delete_person_modal(person))

    # --- Direct message handler (conversational search) ---
    @app.event("message")
    def handle_dm(event, say, client):
        # Only respond to real user messages in DMs (im), ignore bot messages / edits.
        if event.get("channel_type") != "im":
            return
        if event.get("bot_id") or event.get("subtype"):
            return

        text = (event.get("text") or "").strip()
        if not text:
            return

        # Simple keyword routing for add/view/delete/help.
        lower = text.lower()
        if lower in ("help", "hi", "hello"):
            say(blocks=help_blocks())
            return

        if lower.startswith("view "):
            name = text[5:].strip()
            person = repo.find_by_name(name)
            if person:
                say(blocks=person_profile_blocks(person))
                return
            matches = repo.find_by_name_fuzzy(name)
            if not matches:
                say(text=f"No match found for: {name}")
                return
            if len(matches) == 1:
                say(blocks=person_profile_blocks(matches[0]))
                return
            say(blocks=ambiguous_matches_blocks(name, matches))
            return

        # Default: treat any message as a search query.
        try:
            say(text=f"Searching for: _{text}_ ...")
            candidates = retriever.retrieve(text)
            ranked = ranker.rank(text, candidates)
            say(blocks=search_results_blocks(text, ranked))
        except Exception as e:
            log.exception("DM search failed")
            say(text=f"Search failed: {e}")

    return None

