from __future__ import annotations

import logging
from uuid import UUID

from slack_bolt import App as SlackApp

from src.models import PersonCreate, PersonUpdate
from src.repositories.people_repo import PeopleRepo
from src.services.embedder import Embedder
from src.services.profile_builder import build_searchable_text
from src.services.slack_blocks import person_profile_blocks
from src.slack.modals import (
    ADD_MODAL_CALLBACK_ID,
    DELETE_MODAL_CALLBACK_ID,
    EDIT_MODAL_CALLBACK_ID,
    build_delete_person_modal,
    build_edit_person_modal,
)

log = logging.getLogger(__name__)


def _get_state_value(view: dict, key: str) -> str:
    try:
        return (view["state"]["values"][key][key].get("value") or "").strip()
    except Exception:
        return ""


def _csv_list(v: str) -> list[str]:
    return [s.strip() for s in (v or "").split(",") if s.strip()]


def register_view_submissions(app: SlackApp) -> None:
    repo = PeopleRepo()
    embedder = Embedder()

    @app.action("expert_edit_open")
    def action_open_edit(ack, body, client):
        ack()
        person_id = body.get("actions", [{}])[0].get("value")
        if not person_id:
            return
        person = repo.get_person(UUID(person_id))
        client.views_open(trigger_id=body["trigger_id"], view=build_edit_person_modal(person))

    @app.action("expert_delete_open")
    def action_open_delete(ack, body, client):
        ack()
        person_id = body.get("actions", [{}])[0].get("value")
        if not person_id:
            return
        person = repo.get_person(UUID(person_id))
        client.views_open(trigger_id=body["trigger_id"], view=build_delete_person_modal(person))

    @app.view(ADD_MODAL_CALLBACK_ID)
    def view_add_submit(ack, body, client, view):
        name = _get_state_value(view, "name")
        if not name:
            ack(response_action="errors", errors={"name": "Name is required."})
            return
        ack()

        data = PersonCreate(
            name=name,
            current_role=_get_state_value(view, "current_role") or None,
            company=_get_state_value(view, "company") or None,
            location=_get_state_value(view, "location") or None,
            expertise_tags=_csv_list(_get_state_value(view, "expertise_tags")),
            who_knows_them=_csv_list(_get_state_value(view, "who_knows_them")),
            background=_get_state_value(view, "background") or None,
            notes=_get_state_value(view, "notes") or None,
        )

        try:
            searchable_text = build_searchable_text(data)
            person = repo.create_person(data, searchable_text=searchable_text)
            emb = embedder.embed_text(searchable_text)
            repo.upsert_embedding(person.id, emb, embedding_model=embedder.model)
            client.chat_postMessage(channel=body["user"]["id"], blocks=person_profile_blocks(person))
        except Exception:
            log.exception("Add person failed")
            client.chat_postMessage(channel=body["user"]["id"], text="Failed to add expert. Check server logs.")

    @app.view(EDIT_MODAL_CALLBACK_ID)
    def view_edit_submit(ack, body, client, view):
        person_id = (view.get("private_metadata") or "").strip()
        if not person_id:
            ack()
            return

        name = _get_state_value(view, "name")
        if not name:
            ack(response_action="errors", errors={"name": "Name is required."})
            return
        ack()

        patch = PersonUpdate(
            name=name,
            current_role=_get_state_value(view, "current_role") or None,
            company=_get_state_value(view, "company") or None,
            location=_get_state_value(view, "location") or None,
            expertise_tags=_csv_list(_get_state_value(view, "expertise_tags")),
            who_knows_them=_csv_list(_get_state_value(view, "who_knows_them")),
            background=_get_state_value(view, "background") or None,
            notes=_get_state_value(view, "notes") or None,
        )

        try:
            # Build searchable text from the full "post-update" shape.
            existing = repo.get_person(UUID(person_id))
            merged = existing.model_copy(update=patch.model_dump(exclude_unset=True))
            searchable_text = build_searchable_text(merged)

            updated = repo.update_person(UUID(person_id), patch=patch, searchable_text=searchable_text)
            emb = embedder.embed_text(searchable_text)
            repo.upsert_embedding(updated.id, emb, embedding_model=embedder.model)
            client.chat_postMessage(channel=body["user"]["id"], blocks=person_profile_blocks(updated))
        except Exception:
            log.exception("Edit person failed")
            client.chat_postMessage(channel=body["user"]["id"], text="Failed to update expert. Check server logs.")

    @app.view(DELETE_MODAL_CALLBACK_ID)
    def view_delete_submit(ack, body, client, view):
        ack()
        person_id = (view.get("private_metadata") or "").strip()
        if not person_id:
            return
        try:
            person = repo.get_person(UUID(person_id))
            repo.delete_person(UUID(person_id))
            client.chat_postMessage(channel=body["user"]["id"], text=f"Deleted *{person.name}* from the expert database.")
        except Exception:
            log.exception("Delete person failed")
            client.chat_postMessage(channel=body["user"]["id"], text="Failed to delete expert. Check server logs.")

    return None

