from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

# Ensure repo root is importable when running as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import get_settings
from src.models import PersonCreate
from src.repositories.people_repo import PeopleRepo
from src.services.embedder import Embedder
from src.services.profile_builder import build_searchable_text


def _split_semicolon_list(v: str) -> list[str]:
    items = []
    for part in (v or "").split(";"):
        s = part.strip()
        if s:
            items.append(s)
    return items


_OWNER_NAME_RE = re.compile(r"^\s*([^<]+?)\s*(?:<[^>]+>)?\s*$")


def _parse_owners(v: str) -> list[str]:
    out: list[str] = []
    for raw in _split_semicolon_list(v):
        m = _OWNER_NAME_RE.match(raw)
        name = (m.group(1) if m else raw).strip()
        if name:
            out.append(name)
    # de-dupe while preserving order
    seen = set()
    deduped = []
    for x in out:
        k = x.lower()
        if k not in seen:
            seen.add(k)
            deduped.append(x)
    return deduped


def _tags_from_row(row: dict[str, str]) -> list[str]:
    fields = [
        "Industry (obligatory)",
        "Free Tag",
        "Technology",
        "Business",
        "Stage Focus",
        "Geo Focus",
        "Expertise",
        "Category",
        "Relationship",
        "Co-Investment",
    ]
    tags: list[str] = []
    for f in fields:
        tags.extend([t.strip() for t in _split_semicolon_list(row.get(f, "")) if t.strip()])

    seen = set()
    out = []
    for t in tags:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            out.append(t)
    return out


def _pick_location(row: dict[str, str]) -> Optional[str]:
    parts = [
        row.get("Location (City)", "").strip(),
        row.get("Location (State)", "").strip(),
        row.get("Location (Country)", "").strip(),
    ]
    parts = [p for p in parts if p]
    if parts:
        return ", ".join(parts)
    addr = row.get("Location (Address)", "").strip()
    return addr or None


def _background_from_row(row: dict[str, str]) -> str:
    # Keep this fairly dense; it will go into searchable_text and embeddings.
    parts: list[str] = []
    add = lambda k, v: parts.append(f"{k}: {v}".strip()) if v else None

    add("organizations", row.get("Organizations", "").strip())
    add("job_titles", row.get("Job Titles", "").strip())
    add("linkedin", row.get("LinkedIn URL", "").strip())
    add("events_attended", row.get("10x Events attended", "").strip())
    add("source_of_intro", row.get("Source of Introduction (Full Name)", "").strip())
    add("industry", row.get("Industry (obligatory)", "").strip())
    add("expertise", row.get("Expertise", "").strip())
    add("engagement", row.get("Engagement", "").strip())

    # Include Affinity IDs for traceability (helpful for future syncing)
    add("affinity_row_id", row.get("Affinity Row ID", "").strip())
    add("affinity_person_id", row.get("Person Id", "").strip())

    return "\n".join([p for p in parts if p])


def _notes_from_row(row: dict[str, str]) -> str:
    # Keep sensitive fields out of the core UI, but still searchable if desired.
    # If you prefer to NOT store emails at all, remove the email lines below.
    parts: list[str] = []
    add = lambda k, v: parts.append(f"{k}: {v}".strip()) if v else None

    add("primary_email", row.get("Primary Email", "").strip())
    add("emails", row.get("Email Addresses", "").strip())
    add("last_email", row.get("Last Email", "").strip())
    add("last_meeting", row.get("Last Meeting", "").strip())
    add("next_meeting", row.get("Next Meeting", "").strip())
    add("reminders", row.get("Reminders", "").strip())
    add("source_of_intro_email", row.get("Source of Introduction (Email)", "").strip())
    add("language", row.get("Language", "").strip())

    return "\n".join([p for p in parts if p])


def import_csv(
    path: str,
    limit: Optional[int],
    dry_run: bool,
    skip_embeddings: bool,
) -> dict[str, Any]:
    # Dry-run should not require any env vars (Slack/DB/OpenAI).
    settings = get_settings() if not dry_run else None
    repo = PeopleRepo() if not dry_run else None
    embedder = Embedder() if (not dry_run and not skip_embeddings) else None

    imported = 0
    failed = 0

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=1):
            if limit is not None and imported >= limit:
                break

            name = (row.get("Full Name") or "").strip()
            if not name:
                continue

            data = PersonCreate(
                name=name,
                current_role=(row.get("Job Titles") or "").strip() or None,
                company=(row.get("Organizations") or "").strip() or None,
                location=_pick_location(row),
                expertise_tags=_tags_from_row(row),
                who_knows_them=_parse_owners(row.get("Owners", "")),
                background=_background_from_row(row) or None,
                notes=_notes_from_row(row) or None,
            )

            searchable_text = build_searchable_text(data)

            if dry_run:
                print(json.dumps({"row": idx, "person": data.model_dump(), "searchable_text": searchable_text}, indent=2))
                imported += 1
                continue

            try:
                assert repo is not None
                person = repo.create_person(data, searchable_text=searchable_text)
                if not skip_embeddings:
                    assert embedder is not None
                    emb = embedder.embed_text(searchable_text)
                    repo.upsert_embedding(person.id, emb, embedding_model=embedder.model)
                imported += 1
                if imported % 50 == 0:
                    print(f"Imported {imported} people...", file=sys.stderr)
            except Exception as e:
                failed += 1
                print(f"Failed row {idx} ({name}): {e}", file=sys.stderr)

    return {
        "ok": failed == 0,
        "imported": imported,
        "failed": failed,
        "use_pgvector": (settings.use_pgvector if settings else None),
        "embedding_model": (embedder.model if embedder else None),
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Import Affinity CSV into expert-network DB")
    p.add_argument("--path", required=True, help="Path to CSV export")
    p.add_argument("--limit", type=int, default=None, help="Max rows to import (for testing)")
    p.add_argument("--dry-run", action="store_true", help="Print parsed rows; do not write to DB")
    p.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Import people without generating embeddings (faster; search won't work well until embedded).",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()
    path = os.path.expanduser(args.path)
    result = import_csv(path=path, limit=args.limit, dry_run=args.dry_run, skip_embeddings=args.skip_embeddings)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

