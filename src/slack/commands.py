from __future__ import annotations

import logging
import re

from slack_bolt import App as SlackApp

from src.repositories.people_repo import PeopleRepo
from src.services.ranker import Ranker
from src.services.retriever import Retriever, Category
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
    mention_re = re.compile(r"<@[^>]+>")
    category_cmd_re = re.compile(r"^search_(fellows|experts|vcs)\s+(.+)$", re.IGNORECASE)

    category_title: dict[Category, str] = {
        "fellows": "Fellows",
        "experts": "Experts",
        "vcs": "VCs",
    }

    def _clean_message_text(text: str) -> str:
        # Remove @mentions like <@U123ABC> and collapse whitespace.
        cleaned = mention_re.sub(" ", text or "")
        return " ".join(cleaned.strip().split())

    def _run_search(query: str, say, announce: bool = False, category: Category | None = None) -> None:
        display_query = query
        if category:
            display_query = f"[{category_title[category]}] {query}"
        if announce:
            say(text=f"Searching for: _{display_query}_ ...")
        if category:
            candidates = retriever.retrieve_by_category(query, category=category)
        else:
            candidates = retriever.retrieve(query)
        ranked = ranker.rank(query, candidates)
        say(
            blocks=search_results_blocks(display_query, ranked),
            text=f"Expert search results for: {display_query}",
        )

    def _handle_conversational_text(text: str, say, is_dm: bool) -> None:
        cleaned = _clean_message_text(text)
        if not cleaned:
            say(blocks=help_blocks(), text="Expert network guide")
            return

        lower = cleaned.lower()

        cmd_match = category_cmd_re.match(cleaned)
        if cmd_match:
            category = cmd_match.group(1).lower()
            query = cmd_match.group(2).strip()
            if query:
                if category == "fellows":
                    _run_search(query, say, announce=is_dm, category="fellows")
                elif category == "experts":
                    _run_search(query, say, announce=is_dm, category="experts")
                else:
                    _run_search(query, say, announce=is_dm, category="vcs")
            else:
                say(text=f"Usage: `search_{category} <query>`")
            return

        # Natural aliases for category searches.
        if lower.startswith("fellows "):
            _run_search(cleaned[8:].strip(), say, announce=is_dm, category="fellows")
            return
        if lower.startswith("experts "):
            _run_search(cleaned[8:].strip(), say, announce=is_dm, category="experts")
            return
        if lower.startswith("vcs "):
            _run_search(cleaned[4:].strip(), say, announce=is_dm, category="vcs")
            return

        if lower in ("help", "hi", "hello"):
            say(blocks=help_blocks(), text="Expert network help")
            return

        if lower.startswith("view "):
            name = cleaned[5:].strip()
            person = repo.find_by_name(name)
            if person:
                say(blocks=person_profile_blocks(person), text=f"Profile for {name}")
                return
            matches = repo.find_by_name_fuzzy(name)
            if not matches:
                say(text=f"No match found for: {name}")
                return
            if len(matches) == 1:
                say(blocks=person_profile_blocks(matches[0]), text=f"Profile for {matches[0].name}")
                return
            say(blocks=ambiguous_matches_blocks(name, matches), text=f"Multiple matches for {name}")
            return

        if lower.startswith(("add ", "delete ", "remove ", "edit ")):
            say(text="For profile changes, use `/expert-add`, `/expert-view <name>`, or `/expert-delete <name>`.")
            return

        # Default: treat any message as a semantic search query.
        _run_search(cleaned, say, announce=is_dm)

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

    @app.command("/search_fellows")
    def search_fellows(ack, respond, command):
        ack()
        query = (command.get("text") or "").strip()
        if not query:
            respond(text="Usage: `/search_fellows <query>`", response_type="ephemeral")
            return
        try:
            candidates = retriever.retrieve_by_category(query, category="fellows")
            ranked = ranker.rank(query, candidates)
            respond(
                blocks=search_results_blocks(f"[Fellows] {query}", ranked),
                response_type="ephemeral",
            )
        except Exception as e:
            log.exception("search_fellows failed")
            respond(text=f"Search failed: {e}", response_type="ephemeral")

    @app.command("/search_experts")
    def search_experts(ack, respond, command):
        ack()
        query = (command.get("text") or "").strip()
        if not query:
            respond(text="Usage: `/search_experts <query>`", response_type="ephemeral")
            return
        try:
            candidates = retriever.retrieve_by_category(query, category="experts")
            ranked = ranker.rank(query, candidates)
            respond(
                blocks=search_results_blocks(f"[Experts] {query}", ranked),
                response_type="ephemeral",
            )
        except Exception as e:
            log.exception("search_experts failed")
            respond(text=f"Search failed: {e}", response_type="ephemeral")

    @app.command("/search_vcs")
    def search_vcs(ack, respond, command):
        ack()
        query = (command.get("text") or "").strip()
        if not query:
            respond(text="Usage: `/search_vcs <query>`", response_type="ephemeral")
            return
        try:
            candidates = retriever.retrieve_by_category(query, category="vcs")
            ranked = ranker.rank(query, candidates)
            respond(
                blocks=search_results_blocks(f"[VCs] {query}", ranked),
                response_type="ephemeral",
            )
        except Exception as e:
            log.exception("search_vcs failed")
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

        try:
            _handle_conversational_text(event.get("text") or "", say, is_dm=True)
        except Exception as e:
            log.exception("DM search failed")
            say(text=f"Search failed: {e}")

    @app.event("app_mention")
    def handle_app_mention(event, say):
        # Natural UX in channels: "@Mini Chiara who knows X?"
        if event.get("bot_id") or event.get("subtype"):
            return
        try:
            _handle_conversational_text(event.get("text") or "", say, is_dm=False)
        except Exception as e:
            log.exception("app_mention search failed")
            say(text=f"Search failed: {e}")

    @app.event("app_home_opened")
    def handle_app_home_opened(event, client):
        # Show a persistent onboarding guide in the app home.
        try:
            client.views_publish(
                user_id=event.get("user"),
                view={
                    "type": "home",
                    "blocks": help_blocks(),
                },
            )
        except Exception:
            log.exception("app_home_opened publish failed")

    return None

