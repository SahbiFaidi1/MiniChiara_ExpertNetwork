from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PersonBase(BaseModel):
    name: str = Field(min_length=1)
    current_role: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    expertise_tags: list[str] = Field(default_factory=list)
    who_knows_them: list[str] = Field(default_factory=list)
    background: Optional[str] = None
    notes: Optional[str] = None


class PersonCreate(PersonBase):
    pass


class PersonUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    current_role: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    expertise_tags: Optional[list[str]] = None
    who_knows_them: Optional[list[str]] = None
    background: Optional[str] = None
    notes: Optional[str] = None


class Person(PersonBase):
    id: UUID
    searchable_text: str
    created_at: datetime
    updated_at: datetime


class SearchCandidate(BaseModel):
    person: Person
    similarity: float = Field(description="Higher is more similar (1.0 is identical).")


class RankedResult(BaseModel):
    name: str
    current_role: Optional[str] = None
    company: Optional[str] = None
    who_knows_them: list[str] = Field(default_factory=list)
    why_relevant: str


class RankedResultsEnvelope(BaseModel):
    """
    Some LLMs are more reliable if we ask for an object wrapper.
    Slack rendering uses only validated fields from this envelope.
    """

    kind: Literal["expert_search_results"] = "expert_search_results"
    results: list[RankedResult]
    meta: dict[str, Any] = Field(default_factory=dict)

