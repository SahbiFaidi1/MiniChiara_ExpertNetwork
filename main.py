from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from slack_bolt import App as SlackApp
from slack_bolt.adapter.fastapi import SlackRequestHandler

from config import get_settings
from src.models import PersonCreate, PersonUpdate
from src.repositories.people_repo import PeopleRepo
from src.services.embedder import Embedder
from src.services.profile_builder import build_searchable_text
from src.services.ranker import Ranker
from src.services.retriever import Retriever
from src.slack.commands import register_slash_commands
from src.slack.views import register_view_submissions


def build_slack_app() -> SlackApp:
    settings = get_settings()
    if not settings.slack_bot_token or not settings.slack_signing_secret:
        raise RuntimeError("Missing SLACK_BOT_TOKEN / SLACK_SIGNING_SECRET in .env")
    slack_app = SlackApp(token=settings.slack_bot_token, signing_secret=settings.slack_signing_secret)
    register_slash_commands(slack_app)
    register_view_submissions(slack_app)
    return slack_app


def build_api() -> FastAPI:
    settings = get_settings()
    slack_app = build_slack_app()
    slack_handler = SlackRequestHandler(slack_app)
    slack_events_url = f"{settings.public_base_url.rstrip('/')}/slack/events"

    @asynccontextmanager
    async def lifespan(api: FastAPI):
        socket_handler = None
        socket_thread = None
        if settings.slack_app_token:
            from slack_bolt.adapter.socket_mode import SocketModeHandler

            socket_handler = SocketModeHandler(slack_app, settings.slack_app_token)
            socket_thread = threading.Thread(target=socket_handler.start, daemon=True)
            socket_thread.start()
            logging.getLogger(__name__).info("Slack Socket Mode started (HTTP tunnel not required)")
        else:
            logging.getLogger(__name__).warning(
                "Slack HTTP mode: set every Slack Request URL to %s "
                "(or add SLACK_APP_TOKEN for Socket Mode)",
                slack_events_url,
            )
        yield
        if socket_handler is not None:
            socket_handler.close()

    api = FastAPI(title="Expert Network MVP", lifespan=lifespan)
    repo = PeopleRepo()
    embedder = Embedder()
    retriever = Retriever(repo=repo, embedder=embedder)
    ranker = Ranker()

    @api.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True}

    @api.get("/setup")
    async def setup() -> dict:
        """Open http://localhost:8000/setup while developing to copy the Slack Request URL."""
        return {
            "server": "running",
            "slack_events_url": slack_events_url,
            "socket_mode_active": bool(settings.slack_app_token),
            "steps": [
                "Slack app → Slash Commands → Edit each command → paste slack_events_url",
                "Slack app → Interactivity & Shortcuts → On → paste the same URL",
                "Or enable Socket Mode + add SLACK_APP_TOKEN to .env (no ngrok URLs needed)",
            ],
        }

    class SearchRequest(BaseModel):
        query: str = Field(min_length=1)

    @api.post("/api/search")
    async def api_search(req: SearchRequest):
        candidates = retriever.retrieve(req.query)
        ranked = ranker.rank(req.query, candidates)
        return ranked.model_dump()

    @api.get("/api/people")
    async def api_people_find(name: str):
        matches = repo.find_by_name_fuzzy(name)
        return [m.model_dump() for m in matches]

    @api.get("/api/people/{person_id}")
    async def api_people_get(person_id: UUID):
        try:
            p = repo.get_person(person_id)
            return p.model_dump()
        except Exception:
            raise HTTPException(status_code=404, detail="Not found")

    @api.post("/api/people")
    async def api_people_create(req: PersonCreate):
        searchable_text = build_searchable_text(req)
        person = repo.create_person(req, searchable_text=searchable_text)
        emb = embedder.embed_text(searchable_text)
        repo.upsert_embedding(person.id, emb, embedding_model=embedder.model)
        return person.model_dump()

    @api.patch("/api/people/{person_id}")
    async def api_people_update(person_id: UUID, req: PersonUpdate):
        try:
            existing = repo.get_person(person_id)
        except Exception:
            raise HTTPException(status_code=404, detail="Not found")

        merged = existing.model_copy(update=req.model_dump(exclude_unset=True))
        searchable_text = build_searchable_text(merged)
        updated = repo.update_person(person_id, patch=req, searchable_text=searchable_text)
        emb = embedder.embed_text(searchable_text)
        repo.upsert_embedding(updated.id, emb, embedding_model=embedder.model)
        return updated.model_dump()

    @api.delete("/api/people/{person_id}")
    async def api_people_delete(person_id: UUID):
        try:
            repo.delete_person(person_id)
        except Exception:
            raise HTTPException(status_code=404, detail="Not found")
        return {"ok": True}

    @api.post("/slack/events")
    async def slack_events(req: Request):
        log = logging.getLogger(__name__)
        if req.headers.get("x-slack-signature"):
            log.info("Slack HTTP request received")
        return await slack_handler.handle(req)

    logging.getLogger(__name__).info("Slack HTTP endpoint: POST %s", slack_events_url)
    return api


app = build_api()

