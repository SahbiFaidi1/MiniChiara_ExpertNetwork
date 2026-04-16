from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

# Ensure repo root is importable when running as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models import PersonCreate, PersonUpdate
from src.repositories.people_repo import PeopleRepo
from src.services.embedder import Embedder
from src.services.profile_builder import build_searchable_text
from src.services.ranker import Ranker
from src.services.retriever import Retriever


def cmd_add(args: argparse.Namespace) -> int:
    repo = PeopleRepo()
    embedder = Embedder()

    data = PersonCreate(
        name=args.name,
        current_role=args.current_role,
        company=args.company,
        location=args.location,
        expertise_tags=args.expertise_tags or [],
        who_knows_them=args.who_knows_them or [],
        background=args.background,
        notes=args.notes,
    )
    searchable_text = build_searchable_text(data)
    person = repo.create_person(data, searchable_text=searchable_text)
    emb = embedder.embed_text(searchable_text)
    repo.upsert_embedding(person.id, emb, embedding_model=embedder.model)
    print(json.dumps(person.model_dump(), indent=2, default=str))
    return 0


def cmd_view(args: argparse.Namespace) -> int:
    repo = PeopleRepo()
    if args.id:
        p = repo.get_person(UUID(args.id))
        print(json.dumps(p.model_dump(), indent=2, default=str))
        return 0
    if not args.name:
        print("Provide --name or --id", file=sys.stderr)
        return 2
    p = repo.find_by_name(args.name)
    if not p:
        matches = repo.find_by_name_fuzzy(args.name)
        if not matches:
            print("Not found", file=sys.stderr)
            return 1
        print(json.dumps([m.model_dump() for m in matches], indent=2, default=str))
        return 0
    print(json.dumps(p.model_dump(), indent=2, default=str))
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    repo = PeopleRepo()
    if args.id:
        repo.delete_person(UUID(args.id))
        print(json.dumps({"ok": True, "deleted_id": args.id}))
        return 0
    if not args.name:
        print("Provide --name or --id", file=sys.stderr)
        return 2
    p = repo.find_by_name(args.name)
    if not p:
        print("Not found", file=sys.stderr)
        return 1
    repo.delete_person(p.id)
    print(json.dumps({"ok": True, "deleted_id": str(p.id), "name": p.name}))
    return 0


def cmd_edit(args: argparse.Namespace) -> int:
    repo = PeopleRepo()
    embedder = Embedder()

    if not args.id:
        print("Provide --id", file=sys.stderr)
        return 2

    patch = PersonUpdate(
        name=args.name,
        current_role=args.current_role,
        company=args.company,
        location=args.location,
        expertise_tags=args.expertise_tags,
        who_knows_them=args.who_knows_them,
        background=args.background,
        notes=args.notes,
    )

    existing = repo.get_person(UUID(args.id))
    merged = existing.model_copy(update=patch.model_dump(exclude_unset=True))
    searchable_text = build_searchable_text(merged)

    updated = repo.update_person(UUID(args.id), patch=patch, searchable_text=searchable_text)
    emb = embedder.embed_text(searchable_text)
    repo.upsert_embedding(updated.id, emb, embedding_model=embedder.model)

    print(json.dumps(updated.model_dump(), indent=2, default=str))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    repo = PeopleRepo()
    retriever = Retriever(repo=repo)
    ranker = Ranker()

    candidates = retriever.retrieve(args.query)
    ranked = ranker.rank(args.query, candidates)
    print(json.dumps(ranked.model_dump(), indent=2, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="expert-cli", description="Expert network MVP CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("add", help="Add a person (generates embedding)")
    add.add_argument("--name", required=True)
    add.add_argument("--current-role", default=None)
    add.add_argument("--company", default=None)
    add.add_argument("--location", default=None)
    add.add_argument("--expertise-tags", nargs="*", default=[])
    add.add_argument("--who-knows-them", nargs="*", default=[])
    add.add_argument("--background", default=None)
    add.add_argument("--notes", default=None)
    add.set_defaults(func=cmd_add)

    view = sub.add_parser("view", help="View a person by name or id")
    view.add_argument("--name", default=None)
    view.add_argument("--id", default=None)
    view.set_defaults(func=cmd_view)

    delete = sub.add_parser("delete", help="Delete a person by name or id")
    delete.add_argument("--name", default=None)
    delete.add_argument("--id", default=None)
    delete.set_defaults(func=cmd_delete)

    edit = sub.add_parser("edit", help="Edit a person by id (regenerates embedding)")
    edit.add_argument("--id", required=True)
    edit.add_argument("--name", default=None)
    edit.add_argument("--current-role", default=None)
    edit.add_argument("--company", default=None)
    edit.add_argument("--location", default=None)
    edit.add_argument("--expertise-tags", nargs="*", default=None)
    edit.add_argument("--who-knows-them", nargs="*", default=None)
    edit.add_argument("--background", default=None)
    edit.add_argument("--notes", default=None)
    edit.set_defaults(func=cmd_edit)

    search = sub.add_parser("search", help="Semantic search (retrieve + LLM rank)")
    search.add_argument("query")
    search.set_defaults(func=cmd_search)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

