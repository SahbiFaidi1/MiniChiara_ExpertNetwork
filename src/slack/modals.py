from __future__ import annotations

from typing import Any, Optional

from src.models import Person


ADD_MODAL_CALLBACK_ID = "expert_add_modal"
EDIT_MODAL_CALLBACK_ID = "expert_edit_modal"
DELETE_MODAL_CALLBACK_ID = "expert_delete_modal"


def _text_input(
    label: str,
    action_id: str,
    initial_value: Optional[str] = None,
    multiline: bool = False,
    optional: bool = True,
) -> dict[str, Any]:
    el: dict[str, Any] = {
        "type": "plain_text_input",
        "action_id": action_id,
        "multiline": multiline,
    }
    if initial_value is not None:
        el["initial_value"] = initial_value

    return {
        "type": "input",
        "block_id": action_id,
        "label": {"type": "plain_text", "text": label},
        "element": el,
        "optional": optional,
    }


def build_add_person_modal() -> dict[str, Any]:
    return {
        "type": "modal",
        "callback_id": ADD_MODAL_CALLBACK_ID,
        "title": {"type": "plain_text", "text": "Add expert"},
        "submit": {"type": "plain_text", "text": "Save"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            _text_input("Name *", "name", optional=False),
            _text_input("Current role", "current_role"),
            _text_input("Company", "company"),
            _text_input("Location", "location"),
            _text_input("Expertise tags (comma-separated)", "expertise_tags"),
            _text_input("Who on our team knows them (comma-separated)", "who_knows_them"),
            _text_input("Background", "background", multiline=True),
            _text_input("Notes", "notes", multiline=True),
        ],
    }


def build_edit_person_modal(person: Person) -> dict[str, Any]:
    return {
        "type": "modal",
        "callback_id": EDIT_MODAL_CALLBACK_ID,
        "private_metadata": str(person.id),
        "title": {"type": "plain_text", "text": "Edit expert"},
        "submit": {"type": "plain_text", "text": "Update"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            _text_input("Name *", "name", initial_value=person.name, optional=False),
            _text_input("Current role", "current_role", initial_value=person.current_role or ""),
            _text_input("Company", "company", initial_value=person.company or ""),
            _text_input("Location", "location", initial_value=person.location or ""),
            _text_input(
                "Expertise tags (comma-separated)",
                "expertise_tags",
                initial_value=", ".join(person.expertise_tags or []),
            ),
            _text_input(
                "Who on our team knows them (comma-separated)",
                "who_knows_them",
                initial_value=", ".join(person.who_knows_them or []),
            ),
            _text_input("Background", "background", initial_value=person.background or "", multiline=True),
            _text_input("Notes", "notes", initial_value=person.notes or "", multiline=True),
        ],
    }


def build_delete_person_modal(person: Person) -> dict[str, Any]:
    return {
        "type": "modal",
        "callback_id": DELETE_MODAL_CALLBACK_ID,
        "private_metadata": str(person.id),
        "title": {"type": "plain_text", "text": "Delete expert"},
        "submit": {"type": "plain_text", "text": "Delete"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Delete {person.name}?*\nThis removes them from the internal expert database.",
                },
            }
        ],
    }

